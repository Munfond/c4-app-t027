import hashlib
import json
from types import SimpleNamespace

import pytest

from src.active_sensing.native_contract import ABI, BASELINE, PROFILES
from src.services import native_rl_evidence as service


def sealed(path, value):
    path.write_text(json.dumps(value))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(".sha256").write_text(digest)
    return digest


@pytest.fixture
def native_report(tmp_path, monkeypatch):
    output, replay, matrix = (tmp_path / p for p in ("ppo", "replay", "matrix"))
    for directory in (output, replay, matrix):
        directory.mkdir()
    monkeypatch.setattr(
        service,
        "get_settings",
        lambda: SimpleNamespace(native_rl_root=output, native_rl_replay_root=replay, native_rl_matrix_root=matrix),
    )
    monkeypatch.setattr(service, "verified_hash", lambda _: "a" * 64)
    adapter = {"id": "synthetic-test-only", "gain": 0.1}
    monkeypatch.setattr(service, "fingerprint", lambda _: adapter)
    dataset_hash = sealed(replay / "replay.json", {"synthetic_test_only": True})
    audit_hash = sealed(
        replay / "audit.json",
        {
            "status": "passed_research_audit",
            "research_training_admitted": True,
            "deployment_ready": False,
            "dataset_sha256": dataset_hash,
            "capture_plan_sha256": "c" * 64,
        },
    )
    plan_hash = sealed(output / "training-plan.json", {"capture_plan_sha256": "c" * 64})
    policy = output / "validation-policy-1024.zip"
    policy.write_bytes(b"synthetic checksum fixture, not an executable PPO model")
    metrics = {
        "decisions": 19,
        "episodes": 1,
        "mean_episode_reward": 0.9,
        "occupied_iou": 1.0,
        "object_iou": 1.0,
        "latency_p50_ms": 10.0,
        "latency_p95_ms": 11.0,
        "confusion": [[19, 0, 0], [0, 19, 0], [0, 0, 19]],
        "action_counts": {str(a): 19 if a == 7 else 0 for a in range(12)},
    }
    data = {
        "kind": "native_occupancy_ppo_research_v1",
        "status": "completed",
        "deployment_ready": False,
        "observation_abi": ABI,
        "profiles": PROFILES,
        "baseline_action": BASELINE,
        "actual_steps": 8192,
        "ppo_epoch_updates": 256,
        "before_ppo_sha256": "a" * 64,
        "after_ppo_sha256": "b" * 64,
        "checkpoint_sha256": "a" * 64,
        "adapter": adapter,
        "test_results": {key: dict(metrics) for key in ["ppo", *[f"fixed_{a:02d}" for a in range(12)]]},
        "no_improvement_over_full": True,
        "audit_sha256": audit_hash,
        "dataset_sha256": dataset_hash,
        "training_plan_sha256": plan_hash,
        "selected_policy": policy.name,
        "selected_policy_trained_steps": 1024,
        "selected_policy_sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
    }
    for strategy, result in data["test_results"].items():
        action = 7 if strategy == "ppo" else int(strategy.rsplit("_", 1)[1])
        result["action_counts"] = {str(a): 19 if a == action else 0 for a in range(12)}
    path = output / "report.json"
    sealed(path, data)
    return path, policy, data


def test_native_report_requires_bound_policy_audit_and_dataset(native_report):
    path, policy, _ = native_report
    assert service.read_report()["ready"] is True
    policy.write_bytes(b"changed")
    with pytest.raises(ValueError, match="Changed selected native policy"):
        service.read_report()
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="Changed sealed"):
        service.read_report()


def test_native_report_rejects_false_improvement_and_counterfeit_metrics(native_report):
    path, _, data = native_report
    data["no_improvement_over_full"] = False
    sealed(path, data)
    with pytest.raises(ValueError, match="conclusion"):
        service.read_report()
    data["no_improvement_over_full"] = True
    data["test_results"]["ppo"]["object_iou"] = 0.5
    sealed(path, data)
    with pytest.raises(ValueError, match="confusion ledger"):
        service.read_report()


def test_unfinished_capture_never_appears_as_trained(native_report, monkeypatch):
    path, _, _ = native_report
    path.unlink()
    root = service.get_settings().native_rl_matrix_root
    plan_hash = sealed(root / "capture-plan.json", {"kind": "native_occupancy_research_capture_plan_v1"})
    state = {
        "status": "incomplete_failed",
        "completed": 28,
        "total": 48,
        "active_job": "synthetic",
        "plan_sha256": plan_hash,
        "trials": [{"failed_retry": {"job_id": "old"}}],
    }
    (root / "capture-state.json").write_text(json.dumps(state))
    monkeypatch.setattr(
        service.store, "get", lambda _: {"status": "running", "capture_progress": {"completed": 3, "total": 20}}
    )
    value = service.read_report()
    assert not value["ready"] and value["phase"] == "capturing" and value["failed_retries"] == 1
    assert value["frame_progress"]["completed"] == 3
    state["completed"] = 49
    (root / "capture-state.json").write_text(json.dumps(state))
    with pytest.raises(ValueError, match="Invalid native capture progress"):
        service.read_report()


def test_review_is_hash_bound_and_kept_separate_from_nuscenes(native_report, tmp_path):
    from src.models.experiments import EngineerReview
    from src.services.occupancy_rl_evidence import add_review, list_reviews

    snapshot = service.read_report()
    native_root = service.get_settings().native_rl_root
    other_root = tmp_path / "other-research-report"
    review = EngineerReview(
        evidence_sha256=snapshot["evidence_sha256"],
        reviewer="Synthetic test reviewer",
        verdict="needs_evidence",
        notes="Synthetic test only: require unseen routes.",
    )
    saved = add_review(review, evidence=snapshot, root=native_root)
    assert saved["evidence_sha256"] == snapshot["evidence_sha256"]
    assert len(list_reviews(evidence=snapshot, root=native_root)) == 1
    assert list_reviews(evidence=snapshot, root=other_root) == []
    review.evidence_sha256 = "0" * 64
    with pytest.raises(ValueError, match="another report"):
        add_review(review, evidence=snapshot, root=native_root)
