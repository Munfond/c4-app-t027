"""Synthetic audit fixtures only; never inserted into real evidence or the experiment DB."""

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from scripts import audit_native_profile_pilot as audit
from src.evaluation.bev import BevEvaluator
from src.inference.bev import lidar_features


@pytest.fixture
def native_fixture(tmp_path, monkeypatch):
    ident, name = "synthetic-job", "frame_0000"
    capture = tmp_path / ident / "capture"
    capture.mkdir(parents=True)
    points, intensity = np.array([[10.0, 10.0, 1.0]]), np.array([25.5], np.float32)
    x = lidar_features(points, intensity)
    labels, valid = np.zeros((200, 200), np.uint8), np.ones((200, 200), bool)
    rotation, translation = np.eye(3), np.zeros(3)
    path = capture / f"{name}.npz"
    np.savez_compressed(
        path,
        x=x,
        labels=labels,
        valid=valid,
        rotation=rotation,
        translation=translation,
        feature_points=points,
        feature_intensity=intensity,
    )
    prediction = tmp_path / ident / "predictions/occupancy_lidar/0000.json"
    prediction.parent.mkdir(parents=True)
    prediction.write_text(json.dumps({"cells": labels.ravel().tolist()}))
    gain = {"id": "intensity_mean_experimental", "gain": 0.1}
    adjusted = x.copy()
    adjusted[3] *= gain["gain"]
    digest, reference = hashlib.sha256(), hashlib.sha256()
    for value in (
        adjusted,
        labels,
        valid,
        np.zeros((2, 200, 200), np.float32),
        np.zeros((200, 200), bool),
        rotation,
        translation,
    ):
        digest.update(value.tobytes())
    for value in (labels, valid, rotation, translation):
        reference.update(value.tobytes())
    evaluator = BevEvaluator()
    evaluator.add({"labels": labels, "valid": valid}, {"occupancy": labels, "flow": None})
    job = {
        "id": ident,
        "status": "succeeded",
        "spec": {
            "checkpoints": {"occupancy_lidar": "a" * 64},
            "request": {"scenario": {"frames": 1, "lidar": {"channels": 16, "points_per_second": 150000}}},
        },
        "result": {
            "manifest": {
                "frames": [{"id": name}],
                "native_input_adapter": gain,
                "sensor_specs": {"lidar": ["sensor.lidar.ray_cast", {"channels": "16", "points_per_second": "150000"}]},
                "input_sha256": digest.hexdigest(),
                "reference_sha256": reference.hexdigest(),
                "sensor_cost": {"mean_points_per_tick": 1, "estimated_lidar_bytes_per_second": 320},
            },
            "models": {"occupancy_lidar": {"metrics": evaluator.report([])}},
        },
    }
    monkeypatch.setattr(audit.store, "root", lambda: tmp_path)
    monkeypatch.setattr(audit.store, "get", lambda _: job)
    monkeypatch.setattr(audit.studies, "get", lambda _: {"status": "completed", "jobs": [{"id": ident}]})
    monkeypatch.setattr(audit, "verified_hash", lambda _: "a" * 64)
    monkeypatch.setattr(audit, "fingerprint", lambda _: gain)
    monkeypatch.setattr(audit, "evidence", lambda _: {"notice": "Synthetic fixture"})
    return SimpleNamespace(job=job, path=path, x=x)


def test_partial_catalog_is_never_admitted_for_training(native_fixture):
    report = audit.audit(["synthetic-study"])
    assert report["status"] == "incomplete" and report["native_rl_admitted"] is False
    assert len(report["profiles"]) == 1


def test_raw_points_must_reproduce_feature_tensor(native_fixture):
    with np.load(native_fixture.path, allow_pickle=False) as data:
        arrays = {key: data[key] for key in data.files}
    arrays["x"] = arrays["x"] + 1
    np.savez_compressed(native_fixture.path, **arrays)
    with pytest.raises(ValueError, match="do not reproduce"):
        audit.audit(["synthetic-study"])


def test_sensor_attributes_cannot_disguise_profile(native_fixture):
    native_fixture.job["result"]["manifest"]["sensor_specs"]["lidar"][1]["channels"] = "64"
    with pytest.raises(ValueError, match="differs from sensor"):
        audit.audit(["synthetic-study"])
