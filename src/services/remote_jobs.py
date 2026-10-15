"""Authenticated lease protocol. No automatic recapture after an expired lease."""

import json
import re
import time
import uuid

from src.config import get_settings
from src.services import experiment_store as store
from src.services import remote_storage
from src.services import sensor_studies as studies


def workers():
    with store.connection() as db:
        rows = list(db.execute("SELECT * FROM remote_workers ORDER BY id"))
    return [{"id": row["id"], "last_seen": row["heartbeat"],
             "online": row["heartbeat"] > time.time() - get_settings().remote_lease_seconds,
             "ready": json.loads(row["capabilities"])["ready"], "active_job": row["active_job"],
             "notice": json.loads(row["capabilities"])["notice"]} for row in rows]


def hello(worker, capabilities):
    from src.services.experiment_registry import verified_hash

    if capabilities.checkpoint_sha256 != verified_hash("occupancy_lidar"):
        raise ValueError("Worker checkpoint differs from backend checkpoint")
    with store.connection() as db:
        db.execute("INSERT INTO remote_workers(id,heartbeat,capabilities) VALUES(?,?,?) "
                   "ON CONFLICT(id) DO UPDATE SET heartbeat=excluded.heartbeat,capabilities=excluded.capabilities",
                   (worker, time.time(), capabilities.model_dump_json()))
    return {"accepted": True, "lease_seconds": get_settings().remote_lease_seconds}


def expire():
    with store.connection() as db:
        expired = [r[0] for r in db.execute("UPDATE experiments SET status=CASE WHEN cancelled=1 THEN 'cancelled' ELSE 'failed' END,"
                   "stage='lease_expired',error='Remote worker lease expired; inspect worker before a new trial' "
                   "WHERE status='running' AND heartbeat<? RETURNING id",
                   (time.time() - get_settings().remote_lease_seconds,))]
        db.execute("UPDATE remote_workers SET active_job=NULL WHERE active_job IS NOT NULL AND "
                   "active_job NOT IN (SELECT id FROM experiments WHERE status='running')")
    for ident in expired:
        with studies.connection() as db:
            linked = db.execute("SELECT study_id FROM sensor_study_jobs WHERE job_id=?", (ident,)).fetchone()
        if linked:
            studies.cancel(linked[0])


def claim(worker):
    expire()
    studies.advance_running(source="carla")
    with store.connection() as db:
        db.execute("BEGIN IMMEDIATE")
        registered = db.execute("SELECT * FROM remote_workers WHERE id=?", (worker,)).fetchone()
        if not registered or registered["heartbeat"] < time.time() - get_settings().remote_lease_seconds:
            raise ValueError("Worker must register before claiming")
        capabilities = json.loads(registered["capabilities"])
        if not capabilities["ready"] or db.execute("SELECT 1 FROM experiments WHERE status='running'").fetchone():
            return None
        row = db.execute("SELECT * FROM experiments WHERE status='queued' AND cancelled=0 ORDER BY created LIMIT 1").fetchone()
        if not row:
            return None
        frozen = json.loads(row["spec"])
        if frozen["request"]["source"] != "carla" or frozen["checkpoints"] != {"occupancy_lidar": capabilities["checkpoint_sha256"]}:
            raise ValueError("Unsupported remote trial/checkpoint")
        if frozen.get("native_input_adapter") and frozen["native_input_adapter"] != capabilities["adapter"]:
            return None
        lease = uuid.uuid4().hex
        db.execute("UPDATE experiments SET status='running',stage='assigned',owner=?,heartbeat=? WHERE id=?",
                   (worker + ":" + lease, time.time(), row["id"]))
        db.execute("UPDATE remote_workers SET active_job=?,heartbeat=? WHERE id=?", (row["id"], time.time(), worker))
    return {"id": row["id"], "spec": frozen, "lease": lease, "protocol": 1,
            "lease_seconds": get_settings().remote_lease_seconds}


def owned(db, worker, ident, lease, *, allow_cancel=False):
    suffix = " FOR UPDATE" if db.db.dialect.name == "postgresql" else ""
    row = db.execute("SELECT * FROM experiments WHERE id=?" + suffix, (ident,)).fetchone()
    if (not row or row["owner"] != worker + ":" + lease or row["status"] != "running"
            or row["heartbeat"] < time.time() - get_settings().remote_lease_seconds):
        raise PermissionError("Worker lease lost")
    if row["cancelled"] and not allow_cancel:
        raise InterruptedError("Cancellation requested")
    return row


def heartbeat(worker, ident, body):
    with store.connection() as db:
        row = owned(db, worker, ident, body.lease, allow_cancel=True)
        total = json.loads(row["spec"])["request"]["scenario"]["frames"]
        progress = None
        if body.completed_frames is not None:
            if body.completed_frames > total:
                raise ValueError("Progress exceeds frame count")
            progress = json.dumps({"completed": body.completed_frames, "total": total})
        db.execute("UPDATE experiments SET heartbeat=?,stage=?,progress=COALESCE(?,progress) WHERE id=?",
                   (time.time(), body.stage, progress, ident))
        db.execute("UPDATE remote_workers SET heartbeat=? WHERE id=?", (time.time(), worker))
    return {"cancel_requested": bool(row["cancelled"]), "lease_seconds": get_settings().remote_lease_seconds}


def required_paths(frames):
    return {"manifest.json", "capture/manifest.json", *[
        name for i in range(frames) for name in (
            f"capture/frame_{i:04d}.png", f"capture/frame_{i:04d}.json", f"capture/frame_{i:04d}.npz",
            f"predictions/occupancy_lidar/{i:04d}.json", f"references/{i:04d}.json")
    ]}


def uploads(worker, ident, body):
    settings = get_settings()
    with store.connection() as db:
        row = owned(db, worker, ident, body.lease)
        expected = required_paths(json.loads(row["spec"])["request"]["scenario"]["frames"])
        if {a.path for a in body.artifacts} != expected or len(body.artifacts) != len(expected):
            raise ValueError("Upload manifest must contain exactly the trial's required artifacts")
        if sum(a.bytes for a in body.artifacts) > settings.remote_job_max_bytes:
            raise ValueError("Job exceeds artifact budget")
        prefix = settings.remote_storage_prefix.strip("/")
        if not re.fullmatch(r"[a-zA-Z0-9/_-]{1,100}", prefix):
            raise ValueError("Invalid server storage prefix")
        records = []
        for artifact in body.artifacts:
            if artifact.bytes > settings.remote_artifact_max_bytes:
                raise ValueError("Artifact exceeds size limit")
            record = {**artifact.model_dump(), "object_key": f"{prefix}/{ident}/{body.lease}/{artifact.path}"}
            existing = db.execute("SELECT * FROM remote_artifacts WHERE job_id=? AND path=?", (ident, artifact.path)).fetchone()
            if existing and (existing["owner"] != worker + ":" + body.lease
                             or any(existing[k] != record[k] for k in ("bytes", "sha256", "object_key"))):
                raise ValueError("Cannot change a registered artifact")
            if not existing:
                db.execute("INSERT INTO remote_artifacts(job_id,path,owner,bytes,sha256,object_key) VALUES(?,?,?,?,?,?)",
                           (ident, artifact.path, worker + ":" + body.lease, artifact.bytes, artifact.sha256, record["object_key"]))
            records.append(record)
    return {"uploads": [remote_storage.ticket(r) for r in records]}


def artifact(ident, path):
    job = store.get(ident)
    if job["status"] != "succeeded":
        raise FileNotFoundError("Remote artifacts are published only after completion")
    with store.connection() as db:
        row = db.execute("SELECT * FROM remote_artifacts WHERE job_id=? AND path=?", (ident, path)).fetchone()
    if not row:
        raise FileNotFoundError("Artifact not registered")
    return remote_storage.read(dict(row))


def complete(worker, ident, body):
    json.dumps(body.result, allow_nan=False)  # No NaN/Infinity in evidence or SQL JSON.
    with store.connection() as db:
        prior = db.execute("SELECT * FROM experiments WHERE id=?", (ident,)).fetchone()
        if (prior and prior["status"] == "succeeded" and prior["owner"] == worker + ":" + body.lease
                and json.loads(prior["result"]) == body.result):
            return {"accepted": True, "status": "succeeded"}
        row = owned(db, worker, ident, body.lease)
        frozen = json.loads(row["spec"])
        records = [dict(r) for r in db.execute("SELECT * FROM remote_artifacts WHERE job_id=?", (ident,))]
    frames = frozen["request"]["scenario"]["frames"]
    if {r["path"] for r in records} != required_paths(frames):
        raise ValueError("Missing registered artifacts")
    manifest, models = body.result.get("manifest", {}), body.result.get("models", {})
    if (len(manifest.get("frames", [])) != frames or manifest.get("source") != "carla"
            or manifest.get("scenario") != frozen["request"]["scenario"]
            or set(models) != {"occupancy_lidar"}
            or models["occupancy_lidar"].get("checkpoint_sha256") != frozen["checkpoints"]["occupancy_lidar"]
            or not re.fullmatch(r"[a-f0-9]{64}", manifest.get("reference_sha256", ""))
            or not re.fullmatch(r"[a-f0-9]{64}", manifest.get("input_sha256", ""))):
        raise ValueError("Result does not match frozen trial")
    import io

    import numpy as np
    from PIL import Image

    from src.evaluation.bev import BevEvaluator

    indexed = {record["path"]: record for record in records}
    evaluator = BevEvaluator()
    for record in records:
        remote_storage.verify(record)
        if record["path"] == "manifest.json":
            if json.loads(remote_storage.read(record)) != manifest:
                raise ValueError("Manifest differs from submitted result")
        if record["path"].startswith("predictions/"):
            prediction = json.loads(remote_storage.read(record))
            index = int(record["path"].rsplit("/", 1)[1][:-5])
            cells = prediction.get("cells", [])
            if (prediction.get("checkpoint_sha256") != frozen["checkpoints"]["occupancy_lidar"]
                    or prediction.get("frame_id") != manifest["frames"][index]["id"]
                    or prediction.get("shape") != [200, 200] or len(cells) != 40000
                    or any(type(v) is not int or v not in (0, 1, 2) for v in cells)):
                raise ValueError("Invalid frame prediction")
            reference = json.loads(remote_storage.read(indexed[f"references/{index:04d}.json"]))
            labels, valid = reference.get("cells", []), reference.get("valid", [])
            if (len(labels) != 40000 or len(valid) != 40000
                    or any(type(v) is not int or v not in (0, 1, 2) for v in labels)
                    or any(type(v) is not bool for v in valid) or not any(valid)):
                raise ValueError("Invalid reference cells")
            evaluator.add({"labels": np.asarray(labels).reshape(200, 200),
                           "valid": np.asarray(valid).reshape(200, 200)},
                          {"occupancy": np.asarray(cells).reshape(200, 200), "flow": None})
        if record["path"].endswith(".png"):
            with Image.open(io.BytesIO(remote_storage.read(record))) as image:
                if image.format != "PNG" or image.width * image.height > get_settings().max_image_pixels:
                    raise ValueError("Invalid camera preview")
                image.verify()
    measured = evaluator.report([])
    submitted = models["occupancy_lidar"].get("metrics", {})
    for key in ("frame_count", "evaluated_cells", "confusion", "class_iou", "occupied_iou", "object_recall"):
        if submitted.get(key) != measured[key]:
            raise ValueError("Submitted metrics disagree with uploaded prediction/reference")
    with store.connection() as db:
        owned(db, worker, ident, body.lease)
        db.execute("UPDATE experiments SET result=?,status='succeeded',stage='succeeded',heartbeat=? WHERE id=?",
                   (json.dumps(body.result, allow_nan=False), time.time(), ident))
        db.execute("UPDATE remote_workers SET active_job=NULL,heartbeat=? WHERE id=?", (time.time(), worker))
    studies.advance_running(source="carla")
    return {"accepted": True, "status": "succeeded"}


def fail(worker, ident, body):
    with store.connection() as db:
        row = owned(db, worker, ident, body.lease, allow_cancel=True)
        status = "cancelled" if row["cancelled"] else body.status
        db.execute("UPDATE experiments SET status=?,stage=?,error=?,heartbeat=? WHERE id=?",
                   (status, status, body.error, time.time(), ident))
        db.execute("UPDATE remote_workers SET active_job=NULL WHERE id=?", (worker,))
    # Stop the remaining study after a failed capture; never silently recapture another world.
    with studies.connection() as db:
        linked = db.execute("SELECT study_id FROM sensor_study_jobs WHERE job_id=?", (ident,)).fetchone()
    if linked:
        studies.cancel(linked[0])
    return {"accepted": True, "status": status}


def status(worker, ident, lease):
    expire()
    with store.connection() as db:
        row = db.execute("SELECT * FROM experiments WHERE id=?", (ident,)).fetchone()
    if not row or row["owner"] != worker + ":" + lease:
        raise PermissionError("Worker lease lost")
    return {"status": row["status"], "cancel_requested": bool(row["cancelled"])}
