"""Session isolation, refresh leases and cleanup of both memory and worker artifacts."""

from types import SimpleNamespace

import pytest

from src.services import experiment_sessions as sessions
from src.services import experiment_store as store
from src.services import sensor_studies as studies

# Share the raw-sensor fixture; tests still exercise the real queue and checkpoints.
from tests.test_api.test_dataset_replay import replay_data as raw_replay_fixture
from tests.test_api.test_dataset_replay import study_spec

replay_data = raw_replay_fixture


@pytest.mark.asyncio
async def test_session_api_isolates_studies_and_previews(client, replay_data):
    one = (await client.post("/api/v1/experiments/sessions")).json()["id"]
    two = (await client.post("/api/v1/experiments/sessions")).json()["id"]
    response = await client.post(f"/api/v1/experiments/replay/studies?session={one}", json=study_spec().model_dump())
    assert response.status_code == 201, response.text
    ident = response.json()["id"]
    mine = await client.get(f"/api/v1/experiments/replay/studies?session={one}")
    assert [s["id"] for s in mine.json()["items"]] == [ident]
    assert (await client.get(f"/api/v1/experiments/replay/studies?session={two}")).json()["items"] == []
    assert (await client.get("/api/v1/experiments/replay/studies")).json()["items"] == []
    assert (await client.get(f"/api/v1/experiments/sensor-agent/{ident}?session={two}")).status_code == 404
    with store.scope(sessions.path(one)):
        job = studies.get(ident)["jobs"][0]
        camera = sessions.path(one) / job["id"] / "capture" / "0000_CAM_FRONT.jpg"
        camera.parent.mkdir(parents=True)
        camera.write_bytes(b"preview fixture")
    assert (await client.get(f"/api/v1/experiments/{job['id']}/camera?session={one}")).status_code == 200
    assert (await client.get(f"/api/v1/experiments/{job['id']}/camera?session={two}")).status_code == 404
    assert (await client.get(f"/api/v1/experiments/{job['id']}/sensor-preview?session={two}")).status_code == 404
    assert (await client.post(f"/api/v1/experiments/sessions/{one}/end")).status_code == 200
    assert not sessions.path(one).exists()
    assert sessions.path(two).exists()
    assert (await client.get(f"/api/v1/experiments/replay/studies?session={one}")).status_code == 410


def test_refresh_renews_close_grace_and_expiry_removes_all_artifacts(replay_data, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(sessions, "time", SimpleNamespace(time=lambda: clock[0]))
    one = sessions.create()["id"]
    root = sessions.path(one)
    (root / "cache").mkdir()
    (root / "cache" / "prediction.npz").write_bytes(b"temporary")
    sessions.suspend(one)
    clock[0] += 10
    assert sessions.touch(one) == root  # Refresh during close grace keeps this session.
    clock[0] += 31
    sessions.sweep()
    assert root.exists()
    sessions.suspend(one)
    clock[0] += 31
    sessions.sweep()
    assert not root.exists()
    with pytest.raises(KeyError):
        sessions.touch(one)


def test_end_waits_for_running_worker_and_keeps_other_storage(replay_data):
    settings, _ = replay_data
    original = settings.experiment_root / "existing-artifact.txt"
    original.parent.mkdir(parents=True)
    original.write_text("previous CLI result", encoding="utf-8")
    ident = sessions.create()["id"]
    root = sessions.path(ident)
    with store.scope(root):
        study = studies.create(study_spec())
        job = store.claim("test-worker")
        assert job["id"] == study["jobs"][0]["id"]
    sessions.end(ident)
    assert root.exists()  # Worker must stop before its files can be removed.
    with store.scope(root):
        with pytest.raises(InterruptedError, match="Cancelled"):
            store.touch(job["id"], "test-worker", "inference")
        store.finish(job["id"], "test-worker", "cancelled")
    sessions.sweep()
    assert not root.exists()
    assert original.read_text(encoding="utf-8") == "previous CLI result"


def test_session_paths_reject_traversal(replay_data):
    for ident in ("../outside", "", "a" * 33):
        with pytest.raises(KeyError):
            sessions.path(ident)


def test_end_during_llm_request_does_not_leave_orphan_files(replay_data):
    ident = sessions.create()["id"]
    root = sessions.acquire(ident)
    sessions.end(ident)
    assert root.exists()
    # A provider response arriving after End must still be cleaned up at request exit.
    with store.scope(root):
        studies.create(study_spec())
    sessions.release(ident)
    assert not root.exists()


def test_worker_acquire_does_not_renew_a_closed_tab(replay_data, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(sessions, "time", SimpleNamespace(time=lambda: clock[0]))
    ident = sessions.create()["id"]
    sessions.suspend(ident)
    sessions.acquire(ident, renew=False)
    clock[0] += 31
    sessions.sweep()
    assert sessions.path(ident).exists()  # Held until this worker exits.
    with pytest.raises(KeyError):
        sessions.acquire(ident, renew=False)
    sessions.release(ident)
    assert not sessions.path(ident).exists()


def test_poll_finishing_after_close_does_not_extend_close_grace(replay_data, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(sessions, "time", SimpleNamespace(time=lambda: clock[0]))
    ident = sessions.create()["id"]
    sessions.suspend(ident)
    clock[0] += 10
    sessions.acquire(ident)  # A stale polling request must not revive the old document.
    sessions.release(ident)
    clock[0] += 21
    sessions.sweep()
    assert not sessions.path(ident).exists()


def test_worker_writes_into_session_and_context_restores(replay_data):
    from src.services.experiment_runner import run_once

    settings, _ = replay_data
    ident = sessions.create()["id"]
    spec = study_spec()
    spec.model_ids = ["occupancy_lidar"]
    with store.scope(sessions.path(ident)):
        study = studies.create(spec)
        job = run_once()
        assert job["status"] == "succeeded", job["error"]
        assert (store.root() / job["id"] / "manifest.json").exists()
        assert (store.root() / "cache").exists()
        assert studies.get(study["id"])["jobs"][0]["status"] == "succeeded"
    assert store.root() == settings.experiment_root
    assert not (settings.experiment_root / job["id"]).exists()
    sessions.end(ident)
    assert not sessions.path(ident).exists()
