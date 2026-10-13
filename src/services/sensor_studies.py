"""Durable bounded sensor studies. Only one trial is enqueued at a time; no LLM polling."""

import hashlib
import json
import math
import time
import uuid
from contextlib import contextmanager

from src.models.experiments import ExperimentSpec, SensorStudySpec
from src.models.replay import ReplayProfile, ReplayStudySpec, ReplayTrialSpec
from src.services import experiment_store as store
from src.services.experiment_registry import camera_fingerprint, verified_hash


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
    if isinstance(spec, ReplayStudySpec):
        return [
            {
                "environment": index,
                "profile": profile.name,
                "spec": ExperimentSpec(
                    source="dataset_replay",
                    model_ids=spec.model_ids,
                    replay=ReplayTrialSpec(
                        scenario=scenario, profile=profile, cameras=spec.cameras, radars=spec.radars
                    ),
                ),
            }
            for index, scenario in enumerate(spec.scenarios)
            for profile in [ReplayProfile(name="baseline"), *spec.profiles]
        ]
    items = []
    for index, scenario in enumerate(spec.scenarios):
        profiles = [("baseline", scenario.lidar)] + [(p.name, p.lidar) for p in spec.profiles]
        for name, lidar in profiles:
            modified = scenario.model_dump()
            modified["lidar"] = lidar.model_dump()
            items.append(
                {
                    "environment": index,
                    "profile": name,
                    "spec": ExperimentSpec(scenario=modified, native_input_adapter=spec.native_input_adapter),
                }
            )
    return items


def parse_spec(value):
    if isinstance(value, (ReplayStudySpec, SensorStudySpec)):
        return value
    if isinstance(value, str):
        value = json.loads(value)
    return (
        ReplayStudySpec.model_validate(value)
        if value.get("source") == "dataset_replay"
        else SensorStudySpec.model_validate(value)
    )


def checkpoint_identity(spec):
    if isinstance(spec, ReplayStudySpec):
        identity = {"models": {name: verified_hash(name) for name in spec.model_ids}, "camera": camera_fingerprint()}
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    checkpoint = verified_hash("occupancy_lidar")
    if spec.native_input_adapter != "raw":
        from src.inference.native_input import fingerprint

        return hashlib.sha256(
            json.dumps(
                {"checkpoint": checkpoint, "input_adapter": fingerprint(spec.native_input_adapter)}, sort_keys=True
            ).encode()
        ).hexdigest()
    return checkpoint


def object_quality_reasons(spec, metrics):
    reasons = []
    for key, value, reason in (
        ("min_object_iou", (metrics.get("class_iou") or {}).get("object"), "below_minimum_object_iou"),
        ("min_object_recall", metrics.get("object_recall"), "below_minimum_object_recall"),
    ):
        threshold = spec.get(key)
        if threshold is None:
            continue  # Legacy studies did not request these constraints.
        if type(value) not in (int, float) or not math.isfinite(value):
            reasons.append("missing_object_measurement")
        elif value < threshold:
            reasons.append(reason)
    return list(dict.fromkeys(reasons))


def create(spec, metadata=None):
    spec = parse_spec(spec)
    if isinstance(spec, ReplayStudySpec):
        from src.services.experiment_registry import validate_spec

        for command in trials(spec):
            if command["profile"] == "baseline":
                validate_spec(command["spec"])
    checkpoint = checkpoint_identity(spec)
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
    spec = parse_spec(row["spec"])
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
        "source": "dataset_replay" if isinstance(spec, ReplayStudySpec) else "carla",
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
    parsed = parse_spec(study["spec"])
    if checkpoint_identity(parsed) != study["checkpoint_sha256"]:
        raise ValueError("Checkpoint changed during study; do not compare different weights")
    index = len(study["jobs"])
    commands = trials(parsed)
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
    if study["source"] == "dataset_replay":
        from src.services.replay_comparison import compare

        return compare(study)
    environments = []
    for index, scenario in enumerate(study["spec"]["scenarios"]):
        jobs = [job for job in study["jobs"] if job["environment"] == index]
        baseline = next(job for job in jobs if job["profile"] == "baseline")
        rows, eligible = [], []
        for job in jobs:
            result = job["result"] if job["status"] == "succeeded" else None
            base = baseline["result"] if baseline["status"] == "succeeded" else None
            metrics = result["models"]["occupancy_lidar"]["metrics"] if result else {}
            object_reasons = object_quality_reasons(study["spec"], metrics)
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
                "object_iou": (metrics.get("class_iou") or {}).get("object"),
                "object_recall": metrics.get("object_recall"),
                "object_quality_reasons": object_reasons,
                "iou_drop": drop,
                "reference_matches_baseline": matched,
                "lidar_bytes_per_second": bandwidth,
                "data_reduction_fraction": 1 - bandwidth / base_bandwidth
                if bandwidth is not None and base_bandwidth
                else None,
                "latency_model_only_ms": metrics.get("latency_model_only_ms"),
            }
            rows.append(row)
            if (
                matched
                and not object_reasons
                and drop is not None
                and drop <= study["spec"]["max_iou_drop"]
                and iou >= study["spec"].get("min_occupied_iou", 0.3)
                and bandwidth is not None
            ):
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
        "criterion": "Lowest sampled LiDAR byte rate within requested occupied/object quality constraints and IoU drop bound, exact reference match",
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
        ids = [row[0] for row in db.execute("SELECT id FROM sensor_studies ORDER BY created DESC LIMIT 30")]
    return [get(ident) for ident in ids]


def advance_running(source=None):
    """Worker advances both sources, bounded to one queued trial per study."""
    with connection() as db:
        ids = [row[0] for row in db.execute("SELECT id FROM sensor_studies WHERE cancelled=0 ORDER BY created")]
    for ident in ids:
        study = get(ident)
        if study["status"] != "running" or (source and study["source"] != source):
            continue
        try:
            advance(ident)
        except (ValueError, FileNotFoundError) as exc:
            cancel(ident)
            with connection() as db:
                metadata = study["metadata"] | {"orchestration_error": str(exc)}
                db.execute("UPDATE sensor_studies SET metadata=? WHERE id=?", (json.dumps(metadata), ident))


def advance_pending_replays():
    """Compatibility entry point for replay-only workers."""
    advance_running(source="dataset_replay")
