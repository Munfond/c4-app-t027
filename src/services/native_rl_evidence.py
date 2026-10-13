"""Expose bounded native research progress and sealed completed results; never deployment readiness."""

import hashlib
import json
import math
import re

from src.active_sensing.native_occupancy import ABI, BASELINE, PROFILES, quality, read_sealed
from src.config import get_settings
from src.inference.native_input import fingerprint
from src.services import experiment_store as store
from src.services.experiment_registry import verified_hash


def bounded_json(path):
    if path.stat().st_size > 2_000_000:
        raise ValueError("Native research evidence exceeds size limit")
    return json.loads(path.read_text())


def report_path():
    return get_settings().native_rl_root / "report.json"


def progress():
    root = get_settings().native_rl_matrix_root
    file = root / "capture-state.json"
    if not file.is_file():
        return {"ready": False, "notice": "Chưa có bộ capture native RL độc lập.", "phase": "unavailable"}
    state = bounded_json(file)
    plan, plan_hash = read_sealed(root / "capture-plan.json")
    completed, total = state.get("completed", 0), state.get("total", 48)
    if (
        plan.get("kind") != "native_occupancy_research_capture_plan_v1"
        or state.get("plan_sha256") != plan_hash
        or type(completed) is not int
        or not 0 <= completed <= 48
        or total != 48
    ):
        raise ValueError("Invalid native capture progress")
    phase = state["status"]
    frames = None
    if state.get("active_job"):
        active = store.get(state["active_job"])
        if active["status"] in ("running", "queued"):
            phase = "capturing"  # Also reconciles a resumed older collector's persisted interrupted state.
            frames = active["capture_progress"]
    return {
        "ready": False,
        "phase": phase,
        "completed": completed,
        "total": total,
        "frame_progress": frames,
        "failed_retries": sum(bool(r.get("failed_retry")) for r in state["trials"]),
        "notice": "Thu dữ liệu 12 cấu hình vật lý; chưa có policy native RL hoàn tất.",
    }


def read_report():
    path = report_path()
    if not path.is_file():
        return progress()
    bounded_json(path)
    report, digest = read_sealed(path)
    if (
        report.get("kind") != "native_occupancy_ppo_research_v1"
        or report.get("status") != "completed"
        or report.get("deployment_ready") is not False
        or report.get("observation_abi") != ABI
        or report.get("profiles") != PROFILES
        or report.get("baseline_action") != BASELINE
        or report.get("actual_steps") != 8192
        or report.get("ppo_epoch_updates", 0) <= 0
        or report.get("before_ppo_sha256") == report.get("after_ppo_sha256")
        or report.get("checkpoint_sha256") != verified_hash("occupancy_lidar")
        or report.get("adapter") != fingerprint("intensity_mean_experimental")
        or set(report.get("test_results", {})) != {"ppo", *[f"fixed_{i:02d}" for i in range(12)]}
    ):
        raise ValueError("Native PPO report contract mismatch")
    for strategy, metrics in report["test_results"].items():
        if metrics.get("decisions") != 19 or metrics.get("episodes") != 1:
            raise ValueError("Incomplete held-out native episode")
        for name in ("mean_episode_reward", "latency_p50_ms", "latency_p95_ms"):
            value = metrics.get(name)
            if type(value) not in (float, int) or not math.isfinite(value):
                raise ValueError("Invalid native research metric")
        if metrics["latency_p50_ms"] <= 0 or metrics["latency_p95_ms"] < metrics["latency_p50_ms"]:
            raise ValueError("Invalid native timing")
        for name in ("occupied_iou", "object_iou"):
            value = metrics.get(name)
            if value is not None and (
                type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1
            ):
                raise ValueError("Invalid native quality")
        scores = quality(metrics.get("confusion"), max_cells=19 * 40000)
        if any(scores[key] != metrics.get(key) for key in ("occupied_iou", "object_iou")):
            raise ValueError("Native quality disagrees with confusion ledger")
        counts = metrics.get("action_counts", {})
        if (
            set(counts) != {str(i) for i in range(12)}
            or any(type(v) is not int or v < 0 for v in counts.values())
            or sum(counts.values()) != 19
        ):
            raise ValueError("Invalid native action ledger")
        if strategy.startswith("fixed_") and counts[str(int(strategy.rsplit("_", 1)[1]))] != 19:
            raise ValueError("Fixed baseline action ledger is inconsistent")
    full = report["test_results"]["fixed_07"]["mean_episode_reward"]
    policy_reward = report["test_results"]["ppo"]["mean_episode_reward"]
    if report.get("no_improvement_over_full") is not (policy_reward <= full + 1e-6):
        raise ValueError("Native conclusion disagrees with measured reward")
    audit, audit_hash = read_sealed(get_settings().native_rl_replay_root / "audit.json")
    if (
        audit.get("status") != "passed_research_audit"
        or audit.get("research_training_admitted") is not True
        or audit.get("deployment_ready") is not False
        or audit_hash != report.get("audit_sha256")
        or audit.get("dataset_sha256") != report.get("dataset_sha256")
    ):
        raise ValueError("Native research audit does not match report")
    dataset = get_settings().native_rl_replay_root / "replay.json"
    with dataset.open("rb") as stream:
        dataset_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if dataset_hash != report.get("dataset_sha256"):
        raise ValueError("Changed native research dataset")
    plan, plan_hash = read_sealed(path.parent / "training-plan.json")
    if plan_hash != report.get("training_plan_sha256") or plan.get("capture_plan_sha256") != audit.get(
        "capture_plan_sha256"
    ):
        raise ValueError("Native training plan differs from audit/report")
    name = report.get("selected_policy", "")
    if not re.fullmatch(r"validation-policy-\d+\.zip", name):
        raise ValueError("Invalid native policy filename")
    selected_steps = int(name.removesuffix(".zip").rsplit("-", 1)[1])
    if (
        selected_steps != report.get("selected_policy_trained_steps")
        or not 0 < selected_steps <= 8192
        or selected_steps % 1024
    ):
        raise ValueError("Invalid validation policy training step")
    file = path.parent / name
    with file.open("rb") as stream:
        policy_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if policy_hash != report.get("selected_policy_sha256"):
        raise ValueError("Changed selected native policy")
    return {"ready": True, "evidence_sha256": digest, "policy_file_sha256": policy_hash, "report": report}
