import hashlib
import json
from types import SimpleNamespace

import pytest

from src.services import native_profile_evidence as service


@pytest.fixture
def report(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.json"
    adapter = {"id": "synthetic-test-only", "gain": 0.1}
    data = {
        "kind": "audited_native_12_profile_integration_pilot",
        "status": "complete_pilot",
        "native_rl_admitted": False,
        "checkpoint_sha256": "a" * 64,
        "adapter": adapter,
        "profiles": [
            {
                "channels": c,
                "points_per_second": r,
                "metrics": {"occupied_iou": 0.5, "class_iou": {"object": 0.2}, "object_recall": 0.5},
            }
            for c in (16, 32, 64)
            for r in (150000, 300000, 450000, 600000)
        ],
    }

    for index, profile in enumerate(data["profiles"]):
        profile.update(
            profile=f"channels{profile['channels']}_{profile['points_per_second'] // 1000}k",
            job_id=f"{index:032x}",
            frames=4,
            sampled_lidar_bytes_per_second=1000,
        )
    data["study_evidence"] = [{"environments": [{"notice": "Synthetic test fixture"}]}]

    def write():
        path.write_text(json.dumps(data))
        path.with_suffix(".sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest())

    write()
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(native_profile_pilot_report=path))
    monkeypatch.setattr(service, "fingerprint", lambda _: adapter)
    monkeypatch.setattr(service, "verified_hash", lambda _: "a" * 64)
    return path, data, write


def test_report_integrity_and_scope(report):
    path, data, write = report
    assert service.read_report()["ready"]
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="changed"):
        service.read_report()
    data["native_rl_admitted"] = True
    write()
    with pytest.raises(ValueError, match="contract mismatch"):
        service.read_report()


def test_incomplete_or_nonfinite_catalog_is_rejected(report):
    _, data, write = report
    data["profiles"][0]["metrics"]["occupied_iou"] = float("nan")
    write()
    with pytest.raises(ValueError, match="quality metric"):
        service.read_report()
    data["profiles"].pop()
    write()
    with pytest.raises(ValueError, match="contract mismatch"):
        service.read_report()
