"""Synthetic integrity fixtures, not training data or measured research evidence."""

import hashlib
import json
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from src.active_sensing.native_contract import ABI, PROFILES, sensor_context
from src.evaluation.bev import BevEvaluator
from src.services import native_online_evidence as service
from src.simulation.online_sensor_gate import sensor_name


def seal(path, value):
    path.write_text(json.dumps(value))
    hash_ = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(".sha256").write_text(hash_)
    return hash_


@pytest.fixture
def recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(native_online_root=tmp_path))
    folder = tmp_path / service.RUNS["ppo-smoke"]
    capture = folder / "capture"
    (capture / "ipc").mkdir(parents=True)
    (capture / "online-predictions").mkdir()
    plan = {
        "frames": 4,
        "mode": "ppo",
        "profiles": PROFILES,
        "initial_action": 7,
        "route": 110,
        "seed": 210,
        "map": "Town01",
        "weather": "clear",
        "native_report_sha256": "a" * 64,
        "policy_sha256": "b" * 64,
        "checkpoint_sha256": "c" * 64,
        "adapter": {"gain": 0.1},
    }
    plan_hash = seal(folder / "plan.json", plan)
    monkeypatch.setattr(
        service,
        "frozen_policy",
        lambda: {
            "ready": True,
            "evidence_sha256": "a" * 64,
            "policy_file_sha256": "b" * 64,
            "report": {"checkpoint_sha256": "c" * 64, "adapter": {"gain": 0.1}},
        },
    )
    reference = hashlib.sha256()
    trace = []
    evaluator = BevEvaluator()
    for i in range(4):
        labels = np.zeros((200, 200), np.uint8)
        labels[90, 100] = 2
        valid = np.zeros((200, 200), bool)
        valid[90:110, 90:110] = True
        points = np.array([[5.0, 0.0, 1.0], [10.0, 1.0, 1.0]])
        intensity = np.array([40.0, 60.0], np.float32)
        rotation, translation = np.eye(3), np.array([i, 0.0, 0.0])
        np.savez_compressed(
            capture / f"frame_{i:04d}.npz",
            labels=labels,
            valid=valid,
            rotation=rotation,
            translation=translation,
            feature_points=points,
            feature_intensity=intensity,
        )
        np.savez_compressed(capture / f"ipc/signal-{i:04d}.npz", points=points, intensity=intensity)
        np.savez_compressed(capture / f"online-predictions/{i:04d}.npz", prediction=labels)
        (capture / f"frame_{i:04d}.json").write_text(
            json.dumps(
                {"selected_lidar_action": 7, "simulation_frame_id": 100 + i, "camera_frame_id": 100 + i, "boxes": []}
            )
        )
        # Bytes only exercise checksum binding; not a claimed image decode test.
        (capture / f"frame_{i:04d}.png").write_bytes(b"synthetic checksum fixture")
        for array in (labels, valid, rotation, translation):
            reference.update(array.tobytes())
        evaluator.add({"labels": labels, "valid": valid}, {"occupancy": labels, "flow": None})
        trace.append(
            {
                "index": i,
                "frame_id": 100 + i,
                "current_action": 7,
                "next_action": 7,
                "current_profile": PROFILES[7],
                "mode": "ppo",
                "observation_abi": ABI,
                "applies_to_capture_index": None if i == 3 else i + 1,
                "observation": sensor_context(points, intensity) + [0.02] + [float(k == 7) for k in range(12)],
                "cpu_feature_model_ms": 10.0,
                "cpu_model_only_ms": 8.0,
                "cpu_policy_ms": None if i == 3 else 1.0,
                "prediction_sha256": service.digest(capture / f"online-predictions/{i:04d}.npz"),
                "signal_sha256": service.digest(capture / f"ipc/signal-{i:04d}.npz"),
            }
        )
    report = {
        "kind": "native_online_sensor_selector_evidence_v1",
        "status": "completed",
        "mode": "ppo",
        "frames": 4,
        "decisions": 3,
        "training": False,
        "deployment_ready": False,
        "trace": trace,
        "policy_sha256": "b" * 64,
        "plan_sha256": plan_hash,
        "native_policy_report_sha256": "a" * 64,
        "metrics": evaluator.report([8.0] * 4),
        "reference_sha256": reference.hexdigest(),
        "limits": [],
        "timing_scope": "cpu",
    }
    seal(folder / "report.json", report)
    manifest = {
        "online_sensor_selector": True,
        "scenario": {
            "route_spawn_index": 110,
            "seed": 210,
            "map": "Town01",
            "weather": "clear",
            "capture_interval": 0.5,
        },
        "frames": [{"frame_id": 100 + i, "timestamp": i * 0.5} for i in range(4)],
        "online_sensor_bank_actual_attributes": {
            sensor_name(k): {key: str(v) for key, v in p.items()} for k, p in enumerate(PROFILES)
        },
    }
    (capture / "manifest.json").write_text(json.dumps(manifest))
    return folder, report


def test_completed_capture_binds_camera_prediction_reference_and_frozen_policy(recorded, monkeypatch):
    folder, _ = recorded
    service.seal_artifacts(folder)
    assert service.snapshot("ppo-smoke")["decisions"] == 3
    assert len(service.frame_prediction("ppo-smoke", 0)["cells"]) == 40000
    assert service.artifact("ppo-smoke", 0, "png").is_file()
    (folder / "capture/frame_0000.png").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Changed online frame"):
        service.artifact("ppo-smoke", 0, "png")
    monkeypatch.setattr(service, "frozen_policy", lambda: {"ready": False})
    with pytest.raises(ValueError, match="frozen policy"):
        service.snapshot("ppo-smoke")


def test_unsealed_or_failed_run_never_appears_completed(recorded):
    folder, _ = recorded
    assert not service.catalog()["items"]
    assert service.catalog()["unavailable"] == ["ppo-smoke"]
    (folder / "report.json").unlink()
    (folder / "status.json").write_text(json.dumps({"status": "incomplete", "frames": 0}))
    assert service.catalog()["pending"][0]["status"] == "incomplete"
    with pytest.raises(KeyError):
        service.root("../../outside")


def test_causal_trace_and_metric_rewrite_are_rejected(recorded):
    folder, report = recorded
    report["trace"][1]["current_action"] = 0
    seal(folder / "report.json", report)
    with pytest.raises(ValueError, match="causal"):
        service.seal_artifacts(folder)
    report["trace"][1]["current_action"] = 7
    report["metrics"]["occupied_iou"] = 0.5
    seal(folder / "report.json", report)
    with pytest.raises(ValueError, match="metrics differ"):
        service.seal_artifacts(folder)


def test_actor_gt_leakage_is_rejected_even_with_updated_checksum(recorded):
    folder, report = recorded
    file = folder / "capture/ipc/signal-0000.npz"
    with np.load(file) as raw:
        fields = {k: raw[k] for k in raw.files}
    np.savez_compressed(file, **fields, labels=np.zeros((200, 200), np.uint8))
    report["trace"][0]["signal_sha256"] = service.digest(file)
    seal(folder / "report.json", report)
    with pytest.raises(ValueError, match="RAW only"):
        service.seal_artifacts(folder)


def test_web_evidence_readers_do_not_import_optional_training_libraries(tmp_path):
    code = """
import sys
sys.modules['gymnasium'] = None
sys.modules['torch'] = None
sys.modules['stable_baselines3'] = None
from types import SimpleNamespace
from pathlib import Path
from src.services import native_online_evidence as service
service.get_settings = lambda: SimpleNamespace(native_online_root=Path(sys.argv[1]))
assert service.catalog() == {'items': [], 'unavailable': [], 'pending': []}
"""
    subprocess.run([sys.executable, "-c", code, str(tmp_path)], check=True, timeout=10)
