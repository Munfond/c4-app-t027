import json
import zipfile
from pathlib import Path

import pytest

from scripts.perception_bundle import install_bundle
from tests.test_api import test_lab

lab_settings = test_lab.lab_settings
ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "deploy/artifacts/perception-mini-val.zip"


@pytest.mark.asyncio
async def test_cloud_bundle_serves_all_frames_without_raw_data(client, lab_settings):
    catalog = lab_settings.lab_data_root / "exports/L3E/samples.csv"
    catalog.write_bytes((ROOT / "data/lab/exports/L3E/samples.csv").read_bytes())
    manifest = install_bundle(ARCHIVE, lab_settings.lab_data_root / "cache/perception")
    assert len(manifest["tokens"]) == 81
    assert len(manifest["files"]) == 243
    tasks = (await client.get("/api/v1/lab/perception/tasks")).json()["items"]
    assert {task["id"]: task["frame_count"] for task in tasks} == {
        "seg3d": 0, "radar": 81, "occupancy": 81, "flow": 81,
    }
    for task in manifest["tasks"]:
        for token in manifest["tokens"]:
            response = await client.get(f"/api/v1/lab/frames/{token}/perception/{task}")
            assert response.status_code == 200, (task, token, response.text)
            payload = response.json()
            assert payload["task"] == task and payload["sample_token"] == token
            assert payload["coordinates"]["frame"] == "ego"
    token = manifest["tokens"][0]
    assert (await client.get(f"/api/v1/lab/frames/{token}/perception/seg3d")).status_code == 503
    assert (await client.get("/api/v1/lab/frames/unknown/perception/radar")).status_code == 404


@pytest.mark.parametrize("change", ["corrupt", "extra_path"])
def test_bad_bundle_writes_no_files(tmp_path, change):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(ARCHIVE) as original, zipfile.ZipFile(archive, "w") as altered:
        for index, name in enumerate(original.namelist()):
            raw = original.read(name)
            altered.writestr(name, raw + b"!" if change == "corrupt" and index == 0 else raw)
        if change == "extra_path":
            altered.writestr("../escape.json", "{}")
    destination = tmp_path / "cache"
    with pytest.raises(ValueError):
        install_bundle(archive, destination)
    assert not destination.exists()
    assert not (tmp_path / "escape.json").exists()


def test_install_is_repeatable_and_preserves_existing_cache(tmp_path):
    manifest = install_bundle(ARCHIVE, tmp_path)
    assert install_bundle(ARCHIVE, tmp_path) == manifest
    target = tmp_path / next(iter(manifest["files"]))
    original = json.loads(target.read_bytes())
    target.write_text(json.dumps({**original, "model": "newer local model"}))
    with pytest.raises(ValueError, match="Refusing to replace"):
        install_bundle(ARCHIVE, tmp_path)
    assert json.loads(target.read_text())["model"] == "newer local model"
