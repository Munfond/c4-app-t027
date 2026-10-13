"""Local durable queue. One active experiment per store serializes CARLA/GPU access."""

import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from src.config import get_settings
from src.services.experiment_registry import camera_fingerprint, validate_spec, verified_hash

_scoped_root: ContextVar[Path | None] = ContextVar("experiment_session_root", default=None)


def root():
    return _scoped_root.get() or get_settings().experiment_root


@contextmanager
def scope(path):
    token = _scoped_root.set(path)
    try:
        yield
    finally:
        _scoped_root.reset(token)


@contextmanager
def connection():
    directory = root()
    directory.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(directory / "jobs.sqlite3", timeout=30, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS experiments (
        id TEXT PRIMARY KEY, key TEXT UNIQUE, fingerprint TEXT NOT NULL, spec TEXT NOT NULL,
        status TEXT NOT NULL, stage TEXT NOT NULL, created REAL NOT NULL, heartbeat REAL,
        owner TEXT, cancelled INTEGER NOT NULL DEFAULT 0, result TEXT, error TEXT)""")
    try:
        yield db
    finally:
        db.close()


def decode(row):
    if row is None:
        raise KeyError("Experiment not found")
    value = dict(row)
    value["spec"] = json.loads(value["spec"])
    value["result"] = json.loads(value["result"]) if value["result"] else None
    value["capture_progress"] = None
    if value["status"] == "running" and value["spec"]["request"]["source"] == "carla":
        try:
            progress = json.loads((root() / value["id"] / "capture/progress.json").read_text())
            completed, total = progress["completed"], progress["total"]
            if (
                type(completed) is int
                and type(total) is int
                and 0 <= completed <= total
                and total == value["spec"]["request"]["scenario"]["frames"]
            ):
                value["capture_progress"] = {"completed": completed, "total": total}
        except (OSError, ValueError, KeyError, TypeError):
            pass  # Never invent progress from a partial or invalid snapshot.
    value.pop("owner", None)
    return value


def create(spec, key=None):
    validate_spec(spec)
    checkpoints = {name: verified_hash(name) for name in spec.model_ids}
    frozen = {"request": spec.model_dump(), "checkpoints": checkpoints, "pipeline_version": "bev-v2"}
    if spec.source == "dataset_replay":
        frozen["camera_detector"] = camera_fingerprint()
        frozen["pipeline_version"] = "dataset-replay-v1"
    fingerprint = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        if key:
            existing = db.execute("SELECT * FROM experiments WHERE key=?", (key,)).fetchone()
            if existing:
                db.commit()
                if existing["fingerprint"] != fingerprint:
                    raise ValueError("Idempotency key was used for a different request/checkpoint")
                return decode(existing)
        pending = db.execute("SELECT COUNT(*) FROM experiments WHERE status IN ('queued','running')").fetchone()[0]
        if pending >= get_settings().experiment_max_pending:
            db.rollback()
            raise ValueError("Experiment queue limit reached; wait or cancel an existing job")
        ident = uuid.uuid4().hex
        db.execute(
            "INSERT INTO experiments(id,key,fingerprint,spec,status,stage,created) VALUES(?,?,?,?,?,?,?)",
            (ident, key, fingerprint, json.dumps(frozen), "queued", "queued", time.time()),
        )
        db.commit()
    return get(ident)


def get(ident):
    with connection() as db:
        return decode(db.execute("SELECT * FROM experiments WHERE id=?", (ident,)).fetchone())


def recent():
    with connection() as db:
        return [decode(row) for row in db.execute("SELECT * FROM experiments ORDER BY created DESC LIMIT 30")]


def claim(owner):
    with connection() as db:
        db.execute("BEGIN IMMEDIATE")
        # Never rerun a stale capture automatically: another simulator may still own that world.
        db.execute(
            "UPDATE experiments SET status='failed',error='Worker lease expired; inspect simulator before retry' "
            "WHERE status='running' AND heartbeat<?",
            (time.time() - get_settings().experiment_lease_seconds,),
        )
        if db.execute("SELECT 1 FROM experiments WHERE status='running'").fetchone():
            db.commit()
            return None
        row = db.execute("SELECT id FROM experiments WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
        if row:
            db.execute(
                "UPDATE experiments SET status='running',owner=?,heartbeat=? WHERE id=?",
                (owner, time.time(), row["id"]),
            )
        db.commit()
    return get(row["id"]) if row else None


def touch(ident, owner, stage):
    with connection() as db:
        row = db.execute("SELECT cancelled,status,owner FROM experiments WHERE id=?", (ident,)).fetchone()
        if row is None or row["status"] != "running" or row["owner"] != owner:
            raise InterruptedError("Worker lease lost")
        if row["cancelled"]:
            raise InterruptedError("Cancelled")
        db.execute("UPDATE experiments SET heartbeat=?,stage=? WHERE id=?", (time.time(), stage, ident))


def finish(ident, owner, status, result=None, error=None):
    with connection() as db:
        db.execute(
            "UPDATE experiments SET status=CASE WHEN cancelled=1 THEN 'cancelled' ELSE ? END,"
            "result=?,error=?,stage=? WHERE id=? AND owner=? AND status='running'",
            (status, json.dumps(result, allow_nan=False) if result is not None else None, error, status, ident, owner),
        )


def cancel(ident):
    with connection() as db:
        row = db.execute("SELECT status FROM experiments WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise KeyError(ident)
        db.execute(
            "UPDATE experiments SET cancelled=1,status=CASE WHEN status='queued' THEN 'cancelled' ELSE status END "
            "WHERE id=? AND status IN ('queued','running')",
            (ident,),
        )
    return get(ident)
