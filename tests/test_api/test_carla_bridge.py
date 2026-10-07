"""Regressions at the process boundary: cancellation, errors and artifact identity."""
import json
import sys

import pytest

from src.config import Settings
from src.models.experiments import ScenarioSpec
from src.simulation import carla_bridge as bridge


def test_cancelled_capture_terminates_child(tmp_path, monkeypatch):
    class Child:
        returncode = None
        terminated = False

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = -1

        def wait(self, timeout=None):
            return self.returncode

    child = Child()
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda *a, **k: child)
    settings = Settings(_env_file=None, carla_python_executable=sys.executable)

    def cancel():
        raise InterruptedError("Cancelled")

    with pytest.raises(InterruptedError, match="Cancelled"):
        bridge.run_client({"mode": "capture"}, tmp_path, cancel, settings)
    assert child.terminated


def test_client_error_is_reported_without_reading_partial_capture(tmp_path, monkeypatch):
    class Child:
        returncode = 1

        def poll(self):
            return self.returncode

    def fail(*args, **kwargs):
        kwargs["stdout"].write("CARLA client/server version mismatch")
        return Child()

    monkeypatch.setattr(bridge.subprocess, "Popen", fail)
    settings = Settings(_env_file=None, carla_python_executable=sys.executable)
    with pytest.raises(RuntimeError, match="client/server version mismatch"):
        bridge.capture_external(ScenarioSpec(), tmp_path, lambda: None, settings)


def test_bridge_rejects_capture_from_a_different_scenario(tmp_path, monkeypatch):
    scenario = ScenarioSpec(frames=1)

    def wrong_capture(request, root, pulse, settings):
        other = scenario.model_dump()
        other["seed"] += 1
        (root / "manifest.json").write_text(json.dumps({"scenario": other, "frames": [{}]}))

    monkeypatch.setattr(bridge, "run_client", wrong_capture)
    with pytest.raises(ValueError, match="does not match"):
        bridge.capture_external(scenario, tmp_path, lambda: None, Settings(_env_file=None))


def test_external_client_is_available_without_importing_carla(tmp_path):
    settings = Settings(_env_file=None, carla_python_executable=sys.executable, carla_client_path=tmp_path)
    assert bridge.client_available(settings)
    settings.carla_python_executable = tmp_path / "missing-python.exe"
    assert not bridge.client_available(settings)


def test_second_capture_on_same_simulator_is_rejected(tmp_path):
    from src.simulation.carla_capture import simulator_lock

    settings = Settings(_env_file=None)
    with simulator_lock(settings, tmp_path):
        with pytest.raises(RuntimeError, match="busy"), simulator_lock(settings, tmp_path):
            pass
    with simulator_lock(settings, tmp_path):
        pass


def test_stale_synchronous_world_is_released_before_map_load():
    from types import SimpleNamespace

    from src.simulation.carla_capture_core import release_stale_sync

    applied = []
    world = SimpleNamespace(
        get_settings=lambda: SimpleNamespace(synchronous_mode=True, fixed_delta_seconds=0.05),
        apply_settings=applied.append,
    )
    assert release_stale_sync(world)
    assert applied[0].synchronous_mode is False
    world.get_settings = lambda: SimpleNamespace(synchronous_mode=False)
    assert not release_stale_sync(world)
    assert len(applied) == 1
