"""Read-only sealed research report, separate namespace from deployment evidence."""

import hashlib
import json
import math
import re
import sqlite3
import time
import uuid

from src.config import get_settings


def report_path():
    return get_settings().occupancy_rl_root / "report.json"


def read_report():
    path = report_path()
    if not path.is_file():
        return {"ready": False, "notice": "Chưa có báo cáo PPO hoàn tất và được kiểm chứng."}
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("RL report checksum mismatch")
    data = json.loads(raw)
    if data.get("kind") != "measured_occupancy_proxy_ppo_research" or data.get("status") != "completed":
        raise ValueError("Wrong research report kind")
    if data.get("ppo_epoch_updates", 0) <= 0 or data.get("before_ppo_sha256") == data.get("after_ppo_sha256"):
        raise ValueError("No PPO update proof")
    if set(data["results"]) != {"fixed_full", "fixed_half", "fixed_quarter", "rule", "ppo"}:
        raise ValueError("Incomplete baseline comparison")
    for metrics in data["results"].values():
        for key in ("mean_scene_reward", "latency_p50_ms", "latency_p95_ms"):
            value = metrics[key]
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError("Invalid measured metrics")
        for key in ("occupied_iou", "object_iou"):
            value = metrics[key]
            if value is not None and (
                type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
            ):
                raise ValueError("Invalid proxy quality")
        counts = metrics["action_counts"]
        if (
            type(metrics["frames"]) is not int
            or metrics["frames"] <= 0
            or set(counts) != {"0", "1", "2"}
            or any(type(v) is not int or v < 0 for v in counts.values())
            or sum(counts.values()) != metrics["frames"]
            or type(metrics["deadline_misses"]) is not int
            or not 0 <= metrics["deadline_misses"] <= metrics["frames"]
            or metrics["latency_p50_ms"] < 0
            or metrics["latency_p95_ms"] < metrics["latency_p50_ms"]
        ):
            raise ValueError("Invalid decision count or latency")
    policy = data["selected_policy"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.zip", policy):
        raise ValueError("Invalid policy filename")
    policy_path = path.parent / policy
    if not policy_path.resolve().is_relative_to(path.parent.resolve()):
        raise ValueError("Policy is outside evidence root")
    policy_seal = json.loads((path.parent / "policy-seal.json").read_text())
    if policy_seal.get("report_sha256") != digest or policy_seal.get("selected_policy") != policy:
        raise ValueError("Policy seal does not match report")

    with policy_path.open("rb") as stream:
        policy_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if policy_hash != policy_seal.get("policy_sha256"):
        raise ValueError("Selected policy changed")
    return {"ready": True, "evidence_sha256": digest, "policy_file_sha256": policy_hash, "report": data}


def reviews(root=None):
    path = (root or get_settings().occupancy_rl_root) / "engineer-reviews.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, evidence TEXT, reviewer TEXT, verdict TEXT, notes TEXT, created REAL)"
    )
    return db


def add_review(review, *, evidence=None, root=None):
    evidence = evidence if evidence is not None else read_report()
    if not evidence["ready"] or review.evidence_sha256 != evidence["evidence_sha256"]:
        raise ValueError("Review refers to another report")
    value = {
        "id": uuid.uuid4().hex,
        "evidence_sha256": review.evidence_sha256,
        "reviewer": review.reviewer,
        "verdict": review.verdict,
        "notes": review.notes,
        "created_at": time.time(),
    }
    db = reviews(root)
    try:
        with db:
            db.execute(
                "INSERT INTO reviews VALUES(?,?,?,?,?,?)",
                (
                    value["id"],
                    review.evidence_sha256,
                    review.reviewer,
                    review.verdict,
                    review.notes,
                    value["created_at"],
                ),
            )
    finally:
        db.close()
    return value


def list_reviews(*, evidence=None, root=None):
    evidence = evidence if evidence is not None else read_report()
    if not evidence["ready"]:
        return []
    db = reviews(root)
    try:
        return [
            dict(zip(("id", "evidence_sha256", "reviewer", "verdict", "notes", "created_at"), row, strict=True))
            for row in db.execute(
                "SELECT * FROM reviews WHERE evidence=? ORDER BY created DESC", (evidence["evidence_sha256"],)
            )
        ]
    finally:
        db.close()
