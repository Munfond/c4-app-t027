"""Protocol integration: real SQL transactions/HTTP, in-memory object storage, no CARLA/LLM call."""

import hashlib
import io
import json
import time

import pytest
from PIL import Image

from src.config import PROJECT_ROOT, Settings
from src.models.experiments import ExperimentSpec, SensorStudySpec
from src.models.remote_worker import (
    ArtifactSpec,
    JobComplete,
    JobFailure,
    JobHeartbeat,
    UploadRequest,
    WorkerHello,
)
from src.services import experiment_store as store
from src.services import remote_database as database
from src.services import remote_jobs as jobs
from src.services import remote_storage as storage
from src.services import sensor_studies as studies
from src.services.experiment_registry import verified_hash


@pytest.fixture
def remote_settings(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, app_env="test", experiment_execution_mode="remote",
                        experiment_api_enabled_in_production=True, experiment_access_token="operator-" + "a" * 32,
                        remote_worker_tokens=json.dumps({"gpu-1": "b" * 40, "gpu-2": "c" * 40}),
                        remote_database_url="sqlite:///" + str(tmp_path / "remote.sqlite3"),
                        remote_storage_bucket="test-private-bucket", experiment_root=tmp_path / "unused-local",
                        lab_data_root=PROJECT_ROOT / "data/lab")
    for name in ("src.config", "src.services.experiment_store", "src.services.experiment_registry",
                 "src.services.remote_database", "src.services.remote_jobs", "src.services.remote_storage",
                 "src.services.experiment_auth", "src.api.experiments", "src.api.evidence", "src.api.experiment_access"):
        monkeypatch.setattr(name + ".get_settings", lambda: settings)
    monkeypatch.setattr("src.services.carla_runtime.get_settings", lambda: settings)
    database.initialize()
    blobs = {}

    def read(record):
        raw = blobs[record["object_key"]]
        if len(raw) != record["bytes"] or hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise ValueError("Artifact integrity check failed")
        return raw

    monkeypatch.setattr(storage, "ticket", lambda r: {"path": r["path"], "url": "https://storage.test/" + r["object_key"], "headers": {}})
    monkeypatch.setattr(storage, "read", read)
    monkeypatch.setattr(storage, "verify", read)
    return settings, blobs


def register(worker="gpu-1", ready=True):
    return jobs.hello(worker, WorkerHello(checkpoint_sha256=verified_hash("occupancy_lidar"), ready=ready))


def enqueue_study():
    return studies.create(SensorStudySpec(scenarios=[{"frames": 2}],
                                         profiles=[{"name": "half", "lidar": {"points_per_second": 300000}}]))


def output(assignment):
    spec = assignment["spec"]["request"]
    count = spec["scenario"]["frames"]
    manifest = {"source": "carla", "scenario": spec["scenario"],
                "frames": [{"id": f"frame_{i:04d}"} for i in range(count)],
                "reference_sha256": "d" * 64, "input_sha256": "e" * 64,
                "sensor_cost": {"estimated_lidar_bytes_per_second": spec["scenario"]["lidar"]["points_per_second"] * 16}}
    result = {"manifest": manifest, "models": {"occupancy_lidar": {
        "checkpoint_sha256": assignment["spec"]["checkpoints"]["occupancy_lidar"],
        "metrics": {"frame_count": count, "evaluated_cells": count * 40000,
                    "confusion": [[0, 0, 0], [0, count * 40000, 0], [0, 0, 0]],
                    "occupied_iou": 1.0, "class_iou": {"free": None, "static": 1.0, "object": None},
                    "object_recall": None, "latency_model_only_ms": None}}}, "limitations": []}
    artifacts = {path: b"fixture bytes" for path in jobs.required_paths(count)}
    artifacts["manifest.json"] = json.dumps(manifest).encode()
    artifacts["capture/manifest.json"] = json.dumps(manifest).encode()
    image = io.BytesIO()
    Image.new("RGB", (64, 36)).save(image, "PNG")
    for i in range(count):
        artifacts[f"capture/frame_{i:04d}.png"] = image.getvalue()
        artifacts[f"predictions/occupancy_lidar/{i:04d}.json"] = json.dumps({
            "frame_id": f"frame_{i:04d}", "checkpoint_sha256": assignment["spec"]["checkpoints"]["occupancy_lidar"],
            "shape": [200, 200], "cells": [1] * 40000}).encode()
        artifacts[f"references/{i:04d}.json"] = json.dumps({"cells": [1] * 40000, "valid": [True] * 40000,
                                                           "actors": [], "kind": "reference"}).encode()
    return result, artifacts


def stage(assignment, blobs, worker="gpu-1"):
    result, artifacts = output(assignment)
    records = [ArtifactSpec(path=p, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) for p, raw in artifacts.items()]
    jobs.uploads(worker, assignment["id"], UploadRequest(lease=assignment["lease"], artifacts=records))
    with store.connection() as db:
        for row in db.execute("SELECT * FROM remote_artifacts WHERE job_id=?", (assignment["id"],)):
            blobs[row["object_key"]] = artifacts[row["path"]]
    return JobComplete(lease=assignment["lease"], result=result)


def test_remote_study_survives_without_local_files_and_advances(remote_settings):
    settings, blobs = remote_settings
    study = enqueue_study()
    register()
    baseline = jobs.claim("gpu-1")
    assert baseline and baseline["id"] == study["jobs"][0]["id"]
    register("gpu-2")
    assert jobs.claim("gpu-2") is None
    body = stage(baseline, blobs)
    assert jobs.complete("gpu-1", baseline["id"], body)["accepted"]
    assert jobs.complete("gpu-1", baseline["id"], body)["accepted"]  # Lost HTTP response retry.
    candidate = jobs.claim("gpu-1")
    assert candidate and candidate["id"] != baseline["id"]
    jobs.complete("gpu-1", candidate["id"], stage(candidate, blobs))
    report = studies.comparison(study["id"])
    assert report["environments"][0]["provisional_selected"] == "half"
    assert not settings.experiment_root.exists()
    assert len(json.loads(jobs.artifact(candidate["id"], "references/0000.json"))["cells"]) == 40000
    database.engine.cache_clear()  # Simulated backend process restart; files are still absent.
    assert studies.get(study["id"])["status"] == "completed"


def test_wrong_owner_cancel_and_lease_expiry(remote_settings):
    study = enqueue_study()
    register()
    job = jobs.claim("gpu-1")
    body = JobHeartbeat(lease=job["lease"], completed_frames=1)
    with pytest.raises(PermissionError):
        jobs.heartbeat("gpu-2", job["id"], body)
    with pytest.raises(PermissionError):
        jobs.heartbeat("gpu-1", job["id"], JobHeartbeat(lease="f" * 32))
    jobs.heartbeat("gpu-1", job["id"], body)
    assert store.get(job["id"])["capture_progress"] == {"completed": 1, "total": 2}
    studies.cancel(study["id"])
    assert jobs.heartbeat("gpu-1", job["id"], body)["cancel_requested"]
    with pytest.raises(InterruptedError):
        jobs.uploads("gpu-1", job["id"], UploadRequest(lease=job["lease"], artifacts=[
            ArtifactSpec(path="manifest.json", bytes=1, sha256="0" * 64)]))
    jobs.fail("gpu-1", job["id"], JobFailure(lease=job["lease"], status="cancelled", error="Cancelled"))
    assert store.get(job["id"])["status"] == "cancelled"
    second = enqueue_study()
    job = jobs.claim("gpu-1")
    with store.connection() as db:
        db.execute("UPDATE experiments SET heartbeat=? WHERE id=?", (time.time() - 1000, job["id"]))
    jobs.expire()
    assert studies.get(second["id"])["status"] == "cancelled"
    assert jobs.claim("gpu-1") is None  # No silent recapture or next candidate.


def test_artifact_integrity_quota_and_path_rules(remote_settings):
    settings, blobs = remote_settings
    register()
    assignment = jobs.claim("gpu-1")
    assert assignment is None
    store.create(ExperimentSpec(scenario={"frames": 2}))
    assignment = jobs.claim("gpu-1")
    with pytest.raises(ValueError, match="exactly"):
        jobs.uploads("gpu-1", assignment["id"], UploadRequest(lease=assignment["lease"], artifacts=[
            ArtifactSpec(path="../../escape", bytes=1, sha256="0" * 64)]))
    body = stage(assignment, blobs)
    key = next(iter(blobs))
    blobs[key] += b"tampered"
    with pytest.raises(ValueError, match="integrity"):
        jobs.complete("gpu-1", assignment["id"], body)
    assert store.get(assignment["id"])["status"] == "running"
    settings.remote_job_max_bytes = 1
    result, artifacts = output(assignment)
    with pytest.raises(ValueError, match="budget"):
        jobs.uploads("gpu-1", assignment["id"], UploadRequest(lease=assignment["lease"], artifacts=[
            ArtifactSpec(path=p, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()) for p, raw in artifacts.items()]))


@pytest.mark.asyncio
async def test_remote_http_auth_and_preview(client, remote_settings):
    settings, blobs = remote_settings
    operator = {"Authorization": "Bearer " + settings.experiment_access_token}
    worker = {"Authorization": "Bearer " + "b" * 40, "X-Worker-ID": "gpu-1"}
    assert (await client.get("/api/v1/experiments/registry")).status_code == 401
    assert (await client.post("/api/v1/chat", json={"message": "test"})).status_code == 401
    assert (await client.post("/api/v1/remote-workers/claim", headers=operator)).status_code == 401
    assert (await client.post("/api/v1/experiment-access", json={"token": "x" * 40})).status_code == 401
    signed = await client.post("/api/v1/experiment-access", json={"token": settings.experiment_access_token})
    assert signed.status_code == 200 and "HttpOnly" in signed.headers["set-cookie"]
    assert (await client.get("/api/v1/evidence/capabilities")).json()["authenticated"]
    assert (await client.get("/api/v1/experiments/registry")).status_code == 200
    assert (await client.post("/api/v1/experiments/sessions")).status_code == 422
    register()
    ident = store.create(ExperimentSpec(scenario={"frames": 2}))["id"]
    response = await client.post("/api/v1/remote-workers/claim", headers=worker)
    assignment = response.json()["job"]
    assert assignment["id"] == ident
    assert (await client.get(f"/api/v1/experiments/{ident}/camera")).status_code == 404
    jobs.complete("gpu-1", ident, stage(assignment, blobs))
    assert (await client.get(f"/api/v1/experiments/{ident}/camera")).status_code == 200
    reference = await client.get(f"/api/v1/experiments/{ident}/reference/0")
    assert len(reference.json()["valid"]) == 40000
    assert (await client.get(f"/api/v1/experiments/{ident}/predictions/occupancy_lidar/0")).status_code == 200
    assert (await client.get(f"/api/v1/experiments/{ident}/capture/0/exe")).status_code == 404
    assert (await client.get("/api/v1/experiments/runtime")).json()["worker_online"]


def test_remote_rejects_local_sources_and_wrong_checkpoint(remote_settings):
    with pytest.raises(ValueError, match="fresh CARLA"):
        store.create(ExperimentSpec(source="nuscenes", scene_id="scene-0103"))
    with pytest.raises(ValueError, match="checkpoint"):
        jobs.hello("gpu-1", WorkerHello(checkpoint_sha256="0" * 64, ready=True))
    register(ready=False)
    store.create(ExperimentSpec())
    assert jobs.claim("gpu-1") is None


def test_real_occupancy_runner_export_and_remote_completion(remote_settings, tmp_path, monkeypatch):
    import numpy as np

    from scripts.remote_worker import manifest as export
    from src.services.experiment_runner import run_once

    settings, blobs = remote_settings
    register()
    ident = store.create(ExperimentSpec(scenario={"frames": 2}))["id"]
    assignment = jobs.claim("gpu-1")
    work = tmp_path / "isolated-worker"

    def capture(scenario, directory, pulse):
        directory.mkdir(parents=True)
        frames = []
        for i in range(2):
            frame = {"id": f"frame_{i:04d}", "x": np.zeros((7, 200, 200), np.float32),
                     "labels": np.ones((200, 200), np.uint8), "valid": np.ones((200, 200), bool),
                     "flow": np.zeros((2, 200, 200), np.float32), "flow_valid": np.zeros((200, 200), bool),
                     "rotation": np.eye(3), "translation": np.zeros(3)}
            frames.append(frame)
            np.savez_compressed(directory / f"frame_{i:04d}.npz", **{k: v for k, v in frame.items() if k != "id"})
            (directory / f"frame_{i:04d}.json").write_text('{"boxes": []}')
            Image.new("RGB", (64, 36)).save(directory / f"frame_{i:04d}.png")
        value = {"source": "carla", "scenario": scenario.model_dump(), "frames": [{"id": f["id"]} for f in frames],
                 "limitations": [], "sensor_cost": {"estimated_lidar_bytes_per_second": 9600000}}
        (directory / "manifest.json").write_text(json.dumps(value))
        return frames, value

    monkeypatch.setattr("src.simulation.carla_capture.capture", capture)
    with store.scope(work):
        with store.connection() as db:
            db.execute("INSERT INTO experiments(id,fingerprint,spec,status,stage,created) VALUES(?,?,?,?,?,?)",
                       (ident, "0" * 64, json.dumps(assignment["spec"]), "queued", "queued", time.time()))
        result = run_once()
    assert result["status"] == "succeeded"
    records = export(work / ident, assignment)
    jobs.uploads("gpu-1", ident, UploadRequest(lease=assignment["lease"], artifacts=records))
    with store.connection() as db:
        for row in db.execute("SELECT * FROM remote_artifacts WHERE job_id=?", (ident,)):
            blobs[row["object_key"]] = (work / ident / row["path"]).read_bytes()
    assert jobs.complete("gpu-1", ident, JobComplete(lease=assignment["lease"], result=result["result"]))["accepted"]


def test_reject_metrics_that_disagree_with_predictions(remote_settings):
    settings, blobs = remote_settings
    register()
    assignment_id = store.create(ExperimentSpec(scenario={"frames": 2}))["id"]
    assignment = jobs.claim("gpu-1")
    body = stage(assignment, blobs)
    body.result["models"]["occupancy_lidar"]["metrics"]["occupied_iou"] = 0.123
    with pytest.raises(ValueError, match="metrics disagree"):
        jobs.complete("gpu-1", assignment_id, body)
