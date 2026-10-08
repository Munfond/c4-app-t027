"""Measured decisions and append-only human review. No LLM-generated metric or ranking."""
import hashlib
import json
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager

from src.services import experiment_store as store
from src.services import sensor_studies as studies


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def measured(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def evidence(ident):
    study = studies.get(ident)
    report = studies.comparison(ident)
    replay = study["source"] == "dataset_replay"
    environments = []
    for environment in report["environments"]:
        rows = environment["trials"]
        baseline = next(row for row in rows if row["profile"] == "baseline")
        model_ids = study["spec"]["model_ids"] if replay else ["occupancy_lidar"]
        decisions = []
        for model in model_ids:
            def values(row):
                if not replay:
                    return row["occupied_iou"], row["lidar_bytes_per_second"]
                keys = {"occupancy_lidar": ["lidar_payload_bytes"],
                        "occupancy_radar": ["radar_payload_bytes"],
                        "occupancy_lidar_radar": ["lidar_payload_bytes", "radar_payload_bytes"]}[model]
                cost = row["sensor_cost"]
                return (row["models"].get(model, {}).get("metrics", {}).get("occupied_iou"),
                        sum(cost[key] for key in keys) if all(key in cost for key in keys) else None)

            base_iou, base_cost = values(baseline)
            trials = []
            for row in rows:
                iou, cost = values(row)
                drop = base_iou - iou if measured(base_iou) and measured(iou) else None
                reasons = []
                if row["status"] != "succeeded":
                    reasons.append("trial_failed_or_cancelled")
                if not row["reference_matches_baseline"]:
                    reasons.append("reference_mismatch_or_missing")
                if (not measured(iou) or not measured(cost) or not measured(base_iou)
                        or not measured(base_cost) or base_cost <= 0 or (measured(cost) and cost < 0)):
                    reasons.append("missing_measurement")
                if measured(iou) and iou < study["spec"].get("min_occupied_iou", 0.3):
                    reasons.append("below_minimum_iou")
                if drop is not None and drop > study["spec"]["max_iou_drop"]:
                    reasons.append("quality_drop_exceeds_limit")
                job = store.get(row["job_id"])
                result = job.get("result") or {}
                manifest = result.get("manifest", {})
                model_result = result.get("models", {}).get(model, {})
                trials.append({
                    "job_id": row["job_id"], "profile": row["profile"], "status": row["status"],
                    "iou": iou, "cost": cost, "iou_drop": drop,
                    "reduction": 1 - cost / base_cost if measured(cost) and measured(base_cost) and base_cost > 0 else None,
                    "eligible": not reasons, "reasons": reasons, "error": row["error"],
                    "configuration": job["spec"]["request"],
                    "reference_sha256": manifest.get("reference_sha256"),
                    "input_sha256": manifest.get("input_sha256"),
                    "checkpoint_sha256": job["spec"].get("checkpoints", {}).get(model),
                    "hardware": model_result.get("hardware"), "device": model_result.get("device"),
                    "cache_hits": model_result.get("cache_hits"),
                    "latency_model_only_ms": model_result.get("metrics", {}).get("latency_model_only_ms"),
                    "frame_count": len(manifest.get("frames", [])),
                    "visible_actor_counts": manifest.get("visible_actor_counts"),
                    "label_policy": manifest.get("label_policy"),
                    "limitations": result.get("limitations", []),
                    "evidence_path": f"/api/v1/experiments/{row['job_id']}",
                })
            if replay:
                choice = environment["model_choices"].get(model)
                selected = choice["profile"] if choice else None
            else:
                selected = environment["provisional_selected"]
            chosen = next((row for row in trials if row["profile"] == selected), None)
            incomplete = any(any(reason in row["reasons"] for reason in (
                "trial_failed_or_cancelled", "reference_mismatch_or_missing", "missing_measurement"
            )) for row in trials)
            improved = bool(chosen and chosen["eligible"] and chosen["profile"] != "baseline"
                            and chosen["reduction"] is not None and chosen["reduction"] > 0)
            outcome = "improved" if improved else ("inconclusive" if incomplete or not chosen else "no_improvement")
            explanations = {
                "improved": "Có cấu hình giảm dữ liệu và đạt ngưỡng chất lượng trong các lượt đã đo; chưa chứng minh giảm GPU hoặc tối ưu toàn cục.",
                "no_improvement": "Không tìm được cấu hình giảm dữ liệu tốt hơn trong các cấu hình đã thử và theo ngưỡng đã đặt. Giữ baseline; baseline không nhất thiết là cấu hình kém.",
                "inconclusive": "Chưa đủ bằng chứng kết luận: có số đo thiếu, trial lỗi, tham chiếu không khớp hoặc không cấu hình nào đạt ngưỡng. Không tự đề xuất thay cấu hình.",
            }
            decisions.append({"model": model, "outcome": outcome, "selected": selected,
                              "explanation": explanations[outcome], "trials": trials,
                              "cost_scope": "recorded_input_payload" if replay else "estimated_lidar_payload_rate",
                              "cost_unit": "bytes/frame" if replay else "bytes/s"})
        environments.append({"environment": environment["environment"], "scenario": environment["scenario"],
                             "decisions": decisions})
    value = {"schema_version": 1, "study_id": ident, "source": study["source"],
             "checkpoint_sha256": study["checkpoint_sha256"],
             "constraints": {key: study["spec"].get(key) for key in ("min_occupied_iou", "max_iou_drop")},
             "environments": environments, "limitations": report["limitations"],
             "comparison_path": f"/api/v1/experiments/sensor-agent/{ident}/comparison",
             "notice": "Occupancy proxy evidence; not validated real-world safety or GPU savings. Camera selection remains separate in comparison."}
    return value | {"evidence_sha256": digest(value)}


def review_connection(db):
    db.execute("""CREATE TABLE IF NOT EXISTS agent_reviews (
        id TEXT PRIMARY KEY, study_id TEXT NOT NULL, created REAL NOT NULL,
        evidence_sha256 TEXT NOT NULL, payload TEXT NOT NULL, snapshot TEXT NOT NULL)""")


@contextmanager
def connection():
    # Keep review snapshots beyond temporary replay session cleanup. HTTP reads
    # still require access to the original study; this is an engineering archive.
    directory = store.get_settings().experiment_root
    directory.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(directory / "engineer-feedback.sqlite3", timeout=30, isolation_level=None)
    try:
        review_connection(db)
        yield db
    finally:
        db.close()


def reviews(ident):
    studies.get(ident)
    return archived_reviews(ident)


def archived_reviews(ident):
    """Internal archive read; callers must validate access to their evidence source."""
    with connection() as db:
        return [json.loads(row[0]) for row in db.execute(
            "SELECT payload FROM agent_reviews WHERE study_id=? ORDER BY created DESC LIMIT 100", (ident,)
        )]


def save_review(ident, request):
    snapshot = evidence(ident)
    return save_snapshot_review(ident, request, snapshot)


def save_snapshot_review(ident, request, snapshot):
    """Persist an already verified evidence snapshot. Never mutates measured data."""
    if request.evidence_sha256 != snapshot["evidence_sha256"]:
        raise ValueError("Evidence changed; reload before reviewing")
    value = request.model_dump() | {"id": uuid.uuid4().hex, "study_id": ident,
                                    "created_at": time.time(), "used_for_training": False,
                                    "reviewer_identity_verified": False}
    with connection() as db:
        db.execute("INSERT INTO agent_reviews VALUES(?,?,?,?,?,?)", (
            value["id"], ident, value["created_at"], value["evidence_sha256"],
            json.dumps(value, ensure_ascii=False), json.dumps(snapshot, ensure_ascii=False)
        ))
    return value
