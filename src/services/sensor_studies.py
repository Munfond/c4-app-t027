"""Durable bounded sensor studies. Only one trial is enqueued at a time; no LLM polling."""

import json
import time
import uuid
from contextlib import contextmanager

from src.models.experiments import ExperimentSpec, SensorStudySpec
from src.services import experiment_store as store
from src.services.experiment_registry import verified_hash


@contextmanager
def connection():
    with store.connection() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS sensor_studies (
            id TEXT PRIMARY KEY, spec TEXT NOT NULL, created REAL NOT NULL,
            checkpoint TEXT NOT NULL, metadata TEXT NOT NULL, summary TEXT,
            cancelled INTEGER NOT NULL DEFAULT 0)""")
        db.execute("""CREATE TABLE IF NOT EXISTS sensor_study_jobs (
            study_id TEXT NOT NULL, ordinal INTEGER NOT NULL, job_id TEXT NOT NULL,
            PRIMARY KEY(study_id,ordinal))""")
        yield db


def trials(spec):
    items = []
    for index, scenario in enumerate(spec.scenarios):
        profiles = [("baseline", scenario.lidar)] + [(p.name, p.lidar) for p in spec.profiles]
        for name, lidar in profiles:
            modified = scenario.model_dump()
            modified["lidar"] = lidar.model_dump()
            items.append({"environment": index, "profile": name, "spec": ExperimentSpec(scenario=modified)})
    return items


def create(spec, metadata=None):
    spec = SensorStudySpec.model_validate(spec)
    checkpoint = verified_hash("occupancy_lidar")
    ident = uuid.uuid4().hex
    with connection() as db:
        db.execute(
            "INSERT INTO sensor_studies(id,spec,created,checkpoint,metadata) VALUES(?,?,?,?,?)",
            (ident, spec.model_dump_json(), time.time(), checkpoint, json.dumps(metadata or {})),
        )
    return advance(ident)


def get(ident):
    with connection() as db:
        row = db.execute("SELECT * FROM sensor_studies WHERE id=?", (ident,)).fetchone()
        if row is None:
            raise KeyError("Sensor study not found")
        records = list(
            db.execute("SELECT ordinal,job_id FROM sensor_study_jobs WHERE study_id=? ORDER BY ordinal", (ident,))
        )
    spec = SensorStudySpec.model_validate_json(row["spec"])
    commands = trials(spec)
    jobs = []
    for record in records:
        job = store.get(record["job_id"])
        command = commands[record["ordinal"]]
        jobs.append(
            {
                "id": job["id"],
                "environment": command["environment"],
                "profile": command["profile"],
                "status": job["status"],
                "stage": job["stage"],
                "error": job["error"],
                "result": job["result"],
            }
        )
    active = any(job["status"] in ("queued", "running") for job in jobs)
    complete = len(jobs) == len(commands) and not active
    return {
        "id": ident,
        "spec": spec.model_dump(),
        "total_trials": len(commands),
        "jobs": jobs,
        "status": "cancelled" if row["cancelled"] else ("completed" if complete else "running"),
        "checkpoint_sha256": row["checkpoint"],
        "metadata": json.loads(row["metadata"]),
        "summary": json.loads(row["summary"]) if row["summary"] else None,
    }


def advance(ident):
    study = get(ident)
    if study["status"] != "running" or any(j["status"] in ("queued", "running") for j in study["jobs"]):
        return study
    if verified_hash("occupancy_lidar") != study["checkpoint_sha256"]:
        raise ValueError("Checkpoint changed during study; do not compare different weights")
    index = len(study["jobs"])
    commands = trials(SensorStudySpec.model_validate(study["spec"]))
    try:
        job = store.create(commands[index]["spec"], f"sensor-study:{ident}:{index}")
    except ValueError as exc:
        if "queue limit" in str(exc):
            study["waiting_for_queue"] = True
            return study
        raise
    # Concurrent advances use the same idempotency key and cannot duplicate this trial.
    with connection() as db:
        db.execute(
            "INSERT OR IGNORE INTO sensor_study_jobs(study_id,ordinal,job_id) VALUES(?,?,?)", (ident, index, job["id"])
        )
        cancelled = db.execute("SELECT cancelled FROM sensor_studies WHERE id=?", (ident,)).fetchone()[0]
    if cancelled:
        store.cancel(job["id"])
    return get(ident)


def cancel(ident):
    get(ident)
    with connection() as db:
        db.execute("UPDATE sensor_studies SET cancelled=1 WHERE id=?", (ident,))
    for job in get(ident)["jobs"]:
        store.cancel(job["id"])
    return get(ident)


def comparison(ident):
    study = get(ident)
    if study["status"] != "completed":
        raise ValueError("Study must complete before comparison")
    environments = []
    for index, scenario in enumerate(study["spec"]["scenarios"]):
        jobs = [job for job in study["jobs"] if job["environment"] == index]
        baseline = next(job for job in jobs if job["profile"] == "baseline")
        rows, eligible = [], []
        for job in jobs:
            result = job["result"] if job["status"] == "succeeded" else None
            base = baseline["result"] if baseline["status"] == "succeeded" else None
            metrics = result["models"]["occupancy_lidar"]["metrics"] if result else {}
            cost = result["manifest"].get("sensor_cost", {}) if result else {}
            iou = metrics.get("occupied_iou")
            matched = bool(
                result
                and base
                and result["manifest"].get("reference_sha256")
                and result["manifest"]["reference_sha256"] == base["manifest"].get("reference_sha256")
            )
            base_iou = base["models"]["occupancy_lidar"]["metrics"]["occupied_iou"] if base else None
            drop = base_iou - iou if base_iou is not None and iou is not None else None
            bandwidth = cost.get("estimated_lidar_bytes_per_second")
            base_bandwidth = (
                base["manifest"].get("sensor_cost", {}).get("estimated_lidar_bytes_per_second") if base else None
            )
            row = {
                "job_id": job["id"],
                "profile": job["profile"],
                "status": job["status"],
                "error": job["error"],
                "occupied_iou": iou,
                "iou_drop": drop,
                "reference_matches_baseline": matched,
                "lidar_bytes_per_second": bandwidth,
                "data_reduction_fraction": 1 - bandwidth / base_bandwidth
                if bandwidth is not None and base_bandwidth
                else None,
                "latency_model_only_ms": metrics.get("latency_model_only_ms"),
            }
            rows.append(row)
            if matched and drop is not None and drop <= study["spec"]["max_iou_drop"] and bandwidth is not None:
                eligible.append(row)
        eligible.sort(key=lambda row: (row["lidar_bytes_per_second"], -row["occupied_iou"], row["profile"]))
        environments.append(
            {
                "environment": index,
                "scenario": scenario,
                "trials": rows,
                "provisional_selected": eligible[0]["profile"] if eligible else None,
            }
        )
    return {
        "study_id": ident,
        "environments": environments,
        "criterion": "Lowest sampled LiDAR byte rate within absolute occupied-IoU drop bound, exact reference match",
        "limitations": [
            "Exploratory two-dimensional occupancy proxy, not validated real-world sensor recommendation",
            "Reference mismatch excludes trial from selection; more seeds/routes are needed",
            "Data rate is not electricity or dollar cost; fixed BEV shape may keep model latency unchanged",
            "Weather affects RGB; no physical LiDAR rain/fog degradation has been validated",
        ],
    }


def save_summary(ident, summary):
    with connection() as db:
        db.execute("UPDATE sensor_studies SET summary=? WHERE id=?", (json.dumps(summary, ensure_ascii=False), ident))


def recent():
    with connection() as db:
        rows = list(db.execute("SELECT id FROM sensor_studies ORDER BY created DESC LIMIT 30"))
    return [get(row["id"]) for row in rows]


def advance_running():
    for study in recent():
        if study["status"] == "running":
            advance(study["id"])
