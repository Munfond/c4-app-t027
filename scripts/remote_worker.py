"""GPU worker: outbound HTTPS only, no database/storage/LLM key on this machine.

python -m scripts.remote_worker --env-file .env.worker --check
python -m scripts.remote_worker --env-file .env.worker
"""

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import load_dotenv


class ProtocolError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class Api:
    def __init__(self, url, worker, token):
        parts = urlsplit(url)
        if parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in ("127.0.0.1", "localhost")):
            raise ValueError("Worker API requires HTTPS (localhost HTTP is allowed for tests)")
        if parts.username or parts.password or parts.query or parts.fragment or parts.path not in ("", "/"):
            raise ValueError("Use a backend origin without path/credentials/query/fragment")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", worker) or len(token) < 32:
            raise ValueError("Configure WORKER_ID and a WORKER_TOKEN of at least 32 characters")
        self.client = httpx.Client(base_url=url.rstrip("/") + "/api/v1/remote-workers/",
                                   headers={"Authorization": "Bearer " + token, "X-Worker-ID": worker},
                                   timeout=httpx.Timeout(360, connect=15))

    def post(self, path, body=None, *, timeout=None):
        try:
            options = {"timeout": timeout} if timeout is not None else {}
            response = self.client.post(path, json=body or {}, **options)
        except httpx.HTTPError as exc:
            raise ProtocolError("Backend connection failed; lease cannot be assumed valid") from exc
        if not response.is_success:
            # Do not log request headers, signed URLs, provider diagnostics or credentials.
            raise ProtocolError(f"Worker API HTTP {response.status_code} at {path.split('/')[-1]}", response.status_code)
        return response.json()

    def close(self):
        self.client.close()


def preflight():
    from src.config import get_settings
    from src.inference.native_input import fingerprint
    from src.services.experiment_registry import verified_hash
    from src.simulation.carla_bridge import client_available, probe

    settings = get_settings()
    digest = verified_hash("occupancy_lidar")
    adapter = None
    try:
        adapter = fingerprint("intensity_mean_experimental")
    except ValueError:
        pass  # Raw jobs remain supported; aligned jobs require an exact fingerprint.
    ready, notice = True, "Local prerequisites checked; first capture still requires a smoke test"
    try:
        if not client_available(settings):
            raise RuntimeError("Matching CARLA Python client is missing")
        if settings.carla_server_executable:
            from src.simulation.carla_server import require_memory_headroom, require_nvidia_health

            if sys.platform != "linux" or not settings.carla_server_executable.is_file():
                raise RuntimeError("Managed runtime requires an existing CARLA Linux executable")
            require_memory_headroom(settings.carla_min_available_memory_gib)
            require_nvidia_health()
        else:
            versions = probe(settings)
            if versions.get("client_version") != versions.get("server_version"):
                raise RuntimeError("CARLA client/server versions differ")
    except Exception as exc:
        ready = False
        notice = f"Local CARLA preflight failed ({type(exc).__name__}); check runtime, driver, RAM and ports"
    return {"protocol": 1, "checkpoint_sha256": digest, "adapter": adapter, "ready": ready, "notice": notice}


def manifest(directory, assignment):
    from src.services.capture_reference import read_reference
    from src.services.remote_jobs import required_paths

    count = assignment["spec"]["request"]["scenario"]["frames"]
    references = directory / "references"
    references.mkdir(exist_ok=True)
    for index in range(count):
        path = references / f"{index:04d}.json"
        path.write_text(json.dumps(read_reference(directory / "capture" / f"frame_{index:04d}.npz"), allow_nan=False),
                        encoding="utf-8")
    records = []
    for name in sorted(required_paths(count)):
        path = directory / name
        if not path.is_file() or path.is_symlink():
            raise ValueError("Missing/unsafe output artifact")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        records.append({"path": name, "bytes": path.stat().st_size, "sha256": digest})
    return records


def upload(api, assignment, directory, result, abort):
    records = manifest(directory, assignment)
    prefix = f"jobs/{assignment['id']}"
    expected = {r["path"] for r in records}
    sizes = {r["path"]: r["bytes"] for r in records}

    def renew():
        items = api.post(prefix + "/uploads", {"lease": assignment["lease"], "artifacts": records})["uploads"]
        if {ticket["path"] for ticket in items} != expected or len(items) != len(expected):
            raise ValueError("Upload tickets do not match local artifacts")
        return {ticket["path"]: ticket for ticket in items}

    tickets = renew()
    # A separate client ensures bearer credentials never reach object storage.
    with httpx.Client(timeout=httpx.Timeout(180, connect=15)) as client:
        for path in sorted(expected):
            for attempt in range(3):
                if abort.is_set():
                    raise InterruptedError("Upload stopped because lease/cancellation changed")
                ticket = tickets[path]
                if urlsplit(ticket["url"]).scheme != "https":
                    raise ValueError("Artifact upload requires HTTPS")
                try:
                    with (directory / path).open("rb") as stream:
                        response = client.put(ticket["url"], headers={**ticket["headers"],
                                              "Content-Length": str(sizes[path])}, content=stream)
                except httpx.HTTPError as exc:
                    if attempt == 2:
                        raise ProtocolError("Artifact upload connection failed; output preserved locally") from exc
                    abort.wait(attempt + 1)
                    continue
                if response.is_success:
                    break
                if response.status_code == 403 and attempt < 2:
                    tickets = renew()  # Signed URLs may expire during a large upload.
                    continue
                if response.status_code >= 500 and attempt < 2:
                    abort.wait(attempt + 1)
                    continue
                raise ProtocolError(f"Artifact upload HTTP {response.status_code}; output preserved locally", response.status_code)
    if abort.is_set():
        raise InterruptedError("Lease/cancellation changed before completion")
    for attempt in range(3):
        if abort.is_set():
            raise InterruptedError("Completion stopped because lease/cancellation changed")
        try:
            return api.post(prefix + "/complete", {"lease": assignment["lease"], "result": result})
        except ProtocolError as exc:
            if attempt == 2 or exc.status is not None and exc.status < 500:
                raise
            abort.wait(attempt + 1)


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        process.send_signal(signal.CTRL_BREAK_EVENT)
    else:
        process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=25)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def execute(api, assignment, work, *, resume=False):
    from src.services import experiment_store as store

    ident, lease = assignment["id"], assignment["lease"]
    if not re.fullmatch(r"[a-f0-9]{32}", ident) or not re.fullmatch(r"[a-f0-9]{32}", lease):
        raise ValueError("Invalid assignment identity")
    if assignment.get("protocol") != 1 or assignment["spec"].get("pipeline_version") != "bev-v2":
        raise ValueError("Worker protocol/pipeline mismatch")
    if not resume:
        work.mkdir(parents=True, exist_ok=False)
        (work / "assignment.json").write_text(json.dumps(assignment), encoding="utf-8")
    abort, done = threading.Event(), threading.Event()
    interval = max(2, min(15, assignment["lease_seconds"] / 4))
    stage = {"value": "preparing"}
    failure = []

    def heartbeat():
        while not done.is_set():
            try:
                completed = None
                if (work / "jobs.sqlite3").is_file():
                    with store.scope(work):
                        job = store.get(ident)
                    if stage["value"] != "uploading":
                        stage["value"] = job["stage"]
                    if job.get("capture_progress"):
                        completed = job["capture_progress"]["completed"]
                answer = api.post(f"jobs/{ident}/heartbeat", {"lease": lease, "stage": stage["value"],
                                                              "completed_frames": completed}, timeout=interval)
                if answer["cancel_requested"]:
                    abort.set()
                    return
            except Exception:
                failure.append("Heartbeat/lease failed; stopped safely")
                abort.set()
                return
            done.wait(interval)

    thread = threading.Thread(target=heartbeat, daemon=True)
    process = None
    thread.start()
    try:
        if resume:
            state = api.post(f"jobs/{ident}/status", {"lease": lease})
            if state["status"] == "succeeded":
                return state
            if state["status"] != "running" or state["cancel_requested"]:
                raise ProtocolError("Job is no longer uploadable; no automatic recapture")
        else:
            with (work / "trial.log").open("w", encoding="utf-8") as log:
                options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
                process = subprocess.Popen([sys.executable, "-u", "-m", "scripts.remote_trial",
                                             "--assignment", str(work / "assignment.json"), "--directory", str(work)],
                                            stdout=log, stderr=subprocess.STDOUT, **options)
                while process.poll() is None:
                    if abort.wait(0.5):
                        stop_process(process)
                        raise InterruptedError(failure[0] if failure else "Cancellation requested")
        with store.scope(work):
            job = store.get(ident)
        if job["status"] != "succeeded":
            raise RuntimeError("Local trial failed; inspect trial.log on worker")
        stage["value"] = "uploading"
        return upload(api, assignment, work / ident, job["result"], abort)
    except (Exception, KeyboardInterrupt) as exc:
        stop_process(process)
        # Keep logs/raw/output. A later explicit --resume only uploads, never recaptures.
        if not isinstance(exc, ProtocolError):
            try:
                api.post(f"jobs/{ident}/fail", {"lease": lease,
                         "status": "cancelled" if isinstance(exc, (InterruptedError, KeyboardInterrupt)) else "failed",
                         "error": f"Remote worker stopped ({type(exc).__name__}); inspect local job logs"})
            except ProtocolError:
                pass
        raise
    finally:
        done.set()
        thread.join(timeout=20)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env.worker"))
    parser.add_argument("--check", action="store_true", help="Local checks only; no job/simulator launch")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--resume", type=Path, help="Upload a preserved completed trial; never rerun CARLA")
    args = parser.parse_args()
    load_dotenv(args.env_file)
    os.environ["EXPERIMENT_EXECUTION_MODE"] = "local"
    directory = Path(os.environ.get("WORKER_WORK_DIR", "data/remote-worker")).resolve()
    capabilities = preflight()
    if args.check:
        print(json.dumps(capabilities))
        raise SystemExit(0 if capabilities["ready"] else 1)
    api = Api(os.environ.get("REMOTE_API_URL", ""), os.environ.get("WORKER_ID", ""), os.environ.get("WORKER_TOKEN", ""))
    try:
        if args.resume:
            work = args.resume.resolve()
            assignment = json.loads((work / "assignment.json").read_text())
            print(json.dumps(execute(api, assignment, work, resume=True)))
            return
        while True:
            try:
                api.post("heartbeat", capabilities)
                assignment = api.post("claim")["job"] if capabilities["ready"] else None
                if assignment:
                    print(f"Running remote trial {assignment['id']}", flush=True)
                    execute(api, assignment, directory / assignment["id"])
                    print(f"Uploaded remote trial {assignment['id']}", flush=True)
                if args.once:
                    return
            except (ProtocolError, ValueError, RuntimeError, OSError) as exc:
                print(f"Worker paused: {type(exc).__name__}. Check backend status and local logs.", flush=True)
                if args.once:
                    raise SystemExit(1) from exc
            time.sleep(10)
            capabilities = preflight()
    finally:
        api.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Worker stopped; no new trial will be claimed.")
