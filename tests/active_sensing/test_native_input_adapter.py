import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from src.inference import native_input
from src.models.experiments import ExperimentSpec


def test_adapter_preserves_raw_features_and_reference():
    raw = np.ones((7, 200, 200), dtype=np.float32)
    labels = np.zeros((200, 200), dtype=np.uint8)
    frames = [{"x": raw, "labels": labels}]
    output = native_input.apply(frames, {"id": "intensity_mean_experimental", "gain": 0.1})
    assert np.all(raw == 1) and np.all(output[0]["x"][3] == np.float32(0.1))
    assert np.array_equal(output[0]["x"][:3], raw[:3])
    assert np.array_equal(output[0]["x"][4:], raw[4:])
    assert output[0]["labels"] is labels


def test_native_adapter_rejected_for_stored_nuscenes():
    with pytest.raises(ValueError, match="cannot change stored"):
        ExperimentSpec(source="nuscenes", scene_id="scene-0103", native_input_adapter="intensity_mean_experimental")


def test_adapter_seal_and_checkpoint_binding(tmp_path, monkeypatch):
    path = tmp_path / "adapter.json"
    data = {
        "kind": "native_input_mean_alignment_experimental_v1",
        "gain": 0.1,
        "fitted_without_labels": True,
        "checkpoint_sha256": "a" * 64,
    }
    path.write_text(json.dumps(data))
    path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.setattr(native_input, "get_settings", lambda: SimpleNamespace(native_input_adapter_manifest=path))
    monkeypatch.setattr(native_input, "verified_hash", lambda _: "a" * 64)
    assert native_input.fingerprint("intensity_mean_experimental")["gain"] == 0.1
    monkeypatch.setattr(native_input, "verified_hash", lambda _: "b" * 64)
    with pytest.raises(ValueError, match="contract mismatch"):
        native_input.fingerprint("intensity_mean_experimental")
    path.write_text("{}")
    with pytest.raises(ValueError, match="manifest changed"):
        native_input.fingerprint("intensity_mean_experimental")


def test_unavailable_adapter_does_not_break_catalog(tmp_path, monkeypatch):
    monkeypatch.setattr(
        native_input, "get_settings", lambda: SimpleNamespace(native_input_adapter_manifest=tmp_path / "missing.json")
    )
    items = native_input.catalog()
    assert items[0]["available"] and not items[1]["available"]
    with pytest.raises(ValueError, match="unavailable"):
        native_input.fingerprint("intensity_mean_experimental")


def test_changed_adapter_fails_before_capture(tmp_path, monkeypatch):
    from src.services import experiment_runner, experiment_store
    from src.simulation import carla_capture

    settings = SimpleNamespace(experiment_root=tmp_path, experiment_max_pending=2, experiment_lease_seconds=600)
    monkeypatch.setattr(experiment_store, "get_settings", lambda: settings)
    monkeypatch.setattr(experiment_store, "validate_spec", lambda spec: None)
    monkeypatch.setattr(experiment_store, "verified_hash", lambda model: "a" * 64)
    monkeypatch.setattr(experiment_runner, "verified_hash", lambda model: "a" * 64)
    monkeypatch.setattr(native_input, "fingerprint", lambda name: {"id": name, "gain": 0.1})
    job = experiment_store.create(ExperimentSpec(native_input_adapter="intensity_mean_experimental"))
    monkeypatch.setattr(native_input, "fingerprint", lambda name: {"id": name, "gain": 0.2})
    monkeypatch.setattr(
        carla_capture, "capture", lambda *args: pytest.fail("Changed adapter must not launch simulator")
    )
    experiment_runner.run_once()
    result = experiment_store.get(job["id"])
    assert result["status"] == "failed" and "adapter changed after enqueue" in result["error"]
