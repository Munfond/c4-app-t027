import hashlib
import json
from types import SimpleNamespace

import pytest

from src.models.experiments import EngineerReview
from src.services import occupancy_rl_evidence as evidence
from src.simulation.carla_capture_core import camera_attributes


@pytest.mark.parametrize("camera,fov", [(None, 90), ({"fov": 60}, 60), (SimpleNamespace(fov=110), 110)])
def test_camera_bridge(camera, fov):
    assert camera_attributes(SimpleNamespace(camera=camera))["fov"] == str(fov)


def test_camera_rejects_unsupported():
    with pytest.raises(ValueError):
        camera_attributes(SimpleNamespace(camera={"fov": 75}))


@pytest.fixture
def sealed(tmp_path, monkeypatch):
    # Synthetic fixtures never enter the real evidence directory.
    metrics = dict(
        mean_scene_reward=0.2,
        latency_p50_ms=90,
        latency_p95_ms=100,
        occupied_iou=0.4,
        object_iou=0.2,
        frames=2,
        action_counts={"0": 2, "1": 0, "2": 0},
        deadline_misses=0,
    )
    report = dict(
        kind="measured_occupancy_proxy_ppo_research",
        status="completed",
        ppo_epoch_updates=1,
        before_ppo_sha256="a" * 64,
        after_ppo_sha256="b" * 64,
        selected_policy="test-policy.zip",
        results={key: metrics for key in ("fixed_full", "fixed_half", "fixed_quarter", "rule", "ppo")},
    )
    raw = json.dumps(report).encode()
    (tmp_path / "report.json").write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    (tmp_path / "report.sha256").write_text(digest)
    (tmp_path / "test-policy.zip").write_bytes(b"synthetic-policy-fixture-not-executable")
    (tmp_path / "policy-seal.json").write_text(
        json.dumps(
            dict(
                report_sha256=digest,
                selected_policy="test-policy.zip",
                policy_sha256=hashlib.sha256((tmp_path / "test-policy.zip").read_bytes()).hexdigest(),
            )
        )
    )
    monkeypatch.setattr(evidence, "get_settings", lambda: SimpleNamespace(occupancy_rl_root=tmp_path))
    return tmp_path


def test_report_and_policy_integrity(sealed):
    assert evidence.read_report()["ready"]
    policy = json.loads((sealed / "report.json").read_text())["selected_policy"]
    with (sealed / policy).open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="policy changed"):
        evidence.read_report()


def test_review_is_bound_to_evidence(sealed):
    digest = evidence.read_report()["evidence_sha256"]
    body = dict(reviewer="Test fixture", verdict="needs_evidence", notes="Synthetic test review only")
    # The test database is isolated; no engineer feedback is invented in the real report.
    with pytest.raises(ValueError):
        evidence.add_review(EngineerReview(evidence_sha256="0" * 64, **body))
    evidence.add_review(EngineerReview(evidence_sha256=digest, **body))
    assert len(evidence.list_reviews()) == 1
    (sealed / "report.json").write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        evidence.read_report()


@pytest.mark.asyncio
async def test_evidence_routes_fail_closed(client, sealed):
    response = await client.get("/api/v1/experiments/occupancy-rl")
    assert response.status_code == 200 and response.json()["ready"]
    assert (await client.get("/api/v1/experiments/occupancy-rl/report")).status_code == 200
    response = await client.post(
        "/api/v1/experiments/occupancy-rl/reviews",
        json={
            "evidence_sha256": "0" * 64,
            "reviewer": "Test fixture",
            "verdict": "needs_evidence",
            "notes": "Synthetic test review only",
        },
    )
    assert response.status_code == 409
    (sealed / "report.json").write_text("{}")
    for path in ("", "/report", "/reviews"):
        assert (await client.get("/api/v1/experiments/occupancy-rl" + path)).status_code == 503


def test_owned_carla_refuses_low_memory(tmp_path):
    from src.simulation.carla_server import require_memory_headroom

    mem = tmp_path / "meminfo"
    mem.write_text("MemTotal: 15000000 kB\nMemAvailable: 9437184 kB\n")
    with pytest.raises(RuntimeError, match="before launch"):
        require_memory_headroom(10, mem)
    mem.write_text("MemTotal: 15000000 kB\nMemAvailable: 11534336 kB\n")
    assert require_memory_headroom(10, mem) == 11
