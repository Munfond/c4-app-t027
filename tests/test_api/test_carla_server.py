"""Owned simulator processes must clean up without touching external servers."""

import socket
import sys
from types import SimpleNamespace

import pytest

from src.config import Settings
from src.simulation import carla_server

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Managed CARLA server is Linux-only")


@pytest.fixture
def managed(tmp_path, monkeypatch):
    binary = tmp_path / "CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    settings = Settings(_env_file=None, carla_server_executable=binary, carla_port=19400, carla_tm_port=19402)
    child = SimpleNamespace(terminated=False, returncode=None)
    child.poll = lambda: child.returncode

    def terminate():
        child.terminated = True
        child.returncode = -15

    child.terminate = terminate
    child.wait = lambda timeout: child.returncode
    # Lifecycle uses a fake process: host RAM can legitimately be low during a real capture.
    # The memory guard has independent boundary tests in test_recovery_evidence.py.
    monkeypatch.setattr(carla_server, "require_memory_headroom", lambda minimum: 12.0)
    monkeypatch.setattr(carla_server.subprocess, "Popen", lambda *a, **k: child)
    client = SimpleNamespace(
        set_timeout=lambda _: None,
        get_server_version=lambda: "0.9.16",
        get_client_version=lambda: "0.9.16",
        get_world=lambda: SimpleNamespace(get_map=lambda: None),
    )
    monkeypatch.setitem(sys.modules, "carla", SimpleNamespace(Client=lambda *a: client))
    return settings, child, client


def test_cancel_during_startup_terminates_owned_process(managed, tmp_path):
    settings, child, _ = managed

    def cancel():
        raise InterruptedError("cancelled")

    with pytest.raises(InterruptedError, match="cancelled"):
        with carla_server.fresh_server(settings, tmp_path / "capture", cancel):
            pytest.fail("Capture must not start after cancellation")
    assert child.terminated


def test_capture_failure_terminates_owned_server_and_preserves_error(managed, tmp_path):
    settings, child, _ = managed
    with pytest.raises(ValueError, match="sensor failed"):
        with carla_server.fresh_server(settings, tmp_path / "capture", lambda: None):
            raise ValueError("sensor failed")
    assert child.terminated


def test_version_mismatch_terminates_owned_server(managed, tmp_path):
    settings, child, client = managed
    client.get_server_version = lambda: "0.9.15"
    with pytest.raises(RuntimeError, match="version mismatch"):
        with carla_server.fresh_server(settings, tmp_path / "capture", lambda: None):
            pytest.fail("Mismatched server must not capture")
    assert child.terminated


def test_busy_external_port_is_refused_without_launching_or_killing(managed, tmp_path, monkeypatch):
    settings, child, _ = managed

    def forbidden(*a, **k):
        pytest.fail("Must not launch while another server occupies the port")

    monkeypatch.setattr(carla_server.subprocess, "Popen", forbidden)
    with socket.socket() as existing:
        existing.bind(("127.0.0.1", 0))
        existing.listen()
        settings.carla_port = existing.getsockname()[1]
        with pytest.raises(OSError):
            with carla_server.fresh_server(settings, tmp_path, lambda: None):
                pytest.fail("Must not attach to existing server")
        assert existing.getsockname()[1] == settings.carla_port
    assert not child.terminated


def test_remote_server_is_never_managed(managed, tmp_path):
    settings, child, _ = managed
    settings.carla_host = "example.com"
    with pytest.raises(ValueError, match="localhost"):
        with carla_server.fresh_server(settings, tmp_path, lambda: None):
            pytest.fail("Must not manage a remote simulator")
    assert not child.terminated


def test_closed_server_time_wait_does_not_block_next_trial(managed, tmp_path):
    settings, child, _ = managed
    with socket.socket() as previous, socket.socket() as client:
        previous.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        previous.bind(("127.0.0.1", 0))
        port = previous.getsockname()[1]
        previous.listen()
        client.connect(("127.0.0.1", port))
        accepted, _ = previous.accept()
        accepted.shutdown(socket.SHUT_RDWR)
        accepted.close()
        assert client.recv(1) == b""
    settings.carla_port = port
    with carla_server.fresh_server(settings, tmp_path / "next", lambda: None):
        assert not child.terminated
    assert child.terminated


def test_managed_capture_isolates_native_clients_from_long_lived_worker(managed, tmp_path, monkeypatch):
    from contextlib import contextmanager
    from pathlib import Path

    from src.models.experiments import ScenarioSpec
    from src.simulation import carla_bridge, carla_capture

    settings, _, _ = managed
    events = []

    @contextmanager
    def lifecycle(*args):
        events.append("start_server")
        yield lambda: None
        events.append("stop_server")

    def isolated(scenario, root, pulse, child_settings):
        assert child_settings.carla_python_executable == Path(sys.executable)
        assert settings.carla_python_executable is None
        events.append("isolated_capture")
        return [], {}

    monkeypatch.setattr(carla_capture, "get_settings", lambda: settings)
    monkeypatch.setattr(carla_server, "fresh_server", lifecycle)
    monkeypatch.setattr(carla_bridge, "capture_external", isolated)
    _, manifest = carla_capture.capture(ScenarioSpec(), tmp_path, lambda: None)
    assert events == ["start_server", "isolated_capture", "stop_server"]
    assert manifest["client_runtime"] == "isolated_matching_worker_python"


def test_native_crash_after_startup_stops_waiting_for_missing_server(managed, tmp_path):
    settings, child, _ = managed
    with pytest.raises(RuntimeError, match="exited during capture"):
        with carla_server.fresh_server(settings, tmp_path / "crashed", lambda: None) as pulse:
            child.returncode = -11
            pulse()
    assert not child.terminated  # Already dead; no unrelated process is touched.
