import hashlib
import json
import zipfile

import pytest

from scripts.native_demo_bundle import install


@pytest.mark.parametrize("failure", ["traversal", "corruption", "existing"])
def test_native_bundle_rejects_unsafe_inputs_before_writing(tmp_path, failure):
    first = "data/native-rl-measured-v1-20261013/audit.json"
    second = "../outside.json" if failure == "traversal" else "data/native-rl-measured-v1-20261013/replay.json"
    files = {name: {"bytes": 2, "sha256": hashlib.sha256(b"{}").hexdigest()} for name in (first, second)}
    archive = tmp_path / "test.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("manifest.json", json.dumps({"kind": "native_ppo_playback_bundle_v1", "files": files}))
        bundle.writestr(first, b"{}")
        bundle.writestr(second, b"bad" if failure == "corruption" else b"{}")
    destination = tmp_path / "restore"
    if failure == "existing":
        target = destination / second
        target.parent.mkdir(parents=True)
        target.write_bytes(b"preserve")
    with pytest.raises(ValueError):
        install(archive, destination)
    assert not (destination / first).exists()
    assert not (tmp_path / "outside.json").exists()
    if failure == "existing":
        assert (destination / second).read_bytes() == b"preserve"
