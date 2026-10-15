from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services import carla_runtime as service


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    server = tmp_path / "CarlaUE4"
    server.write_text("synthetic preflight fixture, never executed")
    settings = SimpleNamespace(carla_server_executable=server, carla_min_available_memory_gib=10)
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    monkeypatch.setattr(service.sys, "platform", "linux")
    monkeypatch.setattr(service, "require_nvidia_health", lambda: None)
    monkeypatch.setattr(service, "require_memory_headroom", lambda _: 12.0)
    return settings


def test_broken_gpu_or_low_memory_does_not_claim_capture_ready(runtime, monkeypatch):
    def broken():
        raise RuntimeError("device lost")

    monkeypatch.setattr(service, "require_nvidia_health", broken)
    result = service.probe()
    assert result["hardware_ready"] is False and result["gpu_ready"] is False
    assert "bản ghi" in result["notice"]
    monkeypatch.setattr(service, "require_nvidia_health", lambda: None)
    monkeypatch.setattr(service, "require_memory_headroom", lambda _: 8.0)
    assert service.probe()["hardware_ready"] is False
    assert service.probe()["memory_required_gib"] == 10


def test_healthy_hardware_is_not_a_worker_or_all_configurations_guarantee(runtime):
    value = service.probe()
    assert value["hardware_ready"] is True
    assert "worker" in value["notice"]


def test_memory_display_cannot_appear_ready_when_launch_guard_rejects(runtime, monkeypatch):
    monkeypatch.setattr(service, "require_memory_headroom", lambda _: 9.999)
    value = service.probe()
    assert value["hardware_ready"] is False
    assert value["memory_available_gib"] == 9.99


def test_external_or_missing_runtime_is_unknown_not_false_success(runtime):
    runtime.carla_server_executable = None
    assert service.probe()["hardware_ready"] is None
    runtime.carla_server_executable = Path("/nonexistent/carla-fixture")
    assert service.probe()["hardware_ready"] is False


def test_bounded_cached_probe_avoids_repeated_driver_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(service, "_cached", None)
    monkeypatch.setattr(service, "_expires", 0)
    monkeypatch.setattr(service, "probe", lambda: calls.append(1) or {"hardware_ready": False})
    monkeypatch.setattr(service.time, "monotonic", lambda: 100)
    assert service.snapshot() == service.snapshot() == {"hardware_ready": False}
    assert len(calls) == 1
    monkeypatch.setattr(service.time, "monotonic", lambda: 113)
    service.snapshot()
    assert len(calls) == 2
