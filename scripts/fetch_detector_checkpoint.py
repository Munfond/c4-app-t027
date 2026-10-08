"""Download allowlisted OpenMMLab detector weights into an isolated artifact directory.

Source: MMDetection3D v1.4.0 projects/BEVFusion/README.md model table.
Never overwrite Lab checkpoints/metrics. Downloading does not deserialize pickle.
"""
import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path

SOURCE = "https://github.com/open-mmlab/mmdetection3d/blob/v1.4.0/projects/BEVFusion/README.md"
MODELS = {
    "lidar": "bevfusion_lidar_voxel0075_second_secfpn_8xb4-cyclic-20e_nus-3d-2628f933.pth",
    "camera_lidar": "bevfusion_lidar-cam_voxel0075_second_secfpn_8xb4-cyclic-20e_nus-3d-5239b1af.pth",
}
BASE = "https://download.openmmlab.com/mmdetection3d/v1.1.0_models/bevfusion/"


def fetch(model, root):
    name = MODELS[model]
    prefix = name.rsplit("-", 1)[-1].split(".")[0]
    root.mkdir(parents=True, exist_ok=True)
    target = root / name
    if target.exists():
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
    else:
        pending = root / (name + ".part")
        digest = hashlib.sha256()
        count, deadline = 0, time.monotonic() + 600
        with urllib.request.urlopen(BASE + name, timeout=30) as response, pending.open("wb") as output:
            length = int(response.headers.get("Content-Length", 0))
            if length > 2 * 1024 ** 3:
                raise ValueError("Unexpected checkpoint size")
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                count += len(block)
                if count > 2 * 1024 ** 3 or time.monotonic() > deadline:
                    raise ValueError("Checkpoint download exceeded size/time budget")
                output.write(block)
                digest.update(block)
        digest = digest.hexdigest()
        if not digest.startswith(prefix):
            raise ValueError("Checkpoint SHA256 does not match upstream filename fingerprint; partial retained")
        pending.replace(target)
    if not digest.startswith(prefix):
        raise ValueError("Existing checkpoint fingerprint mismatch; file was not replaced")
    metadata = {"model": model, "path": name, "sha256": digest, "bytes": target.stat().st_size,
                "source": SOURCE, "download_url": BASE + name,
                "upstream_filename_fingerprint": prefix, "loaded": False,
                "note": "OpenMMLab implementation weights, not restored team/MIT weights; old metrics do not apply"}
    (root / (model + "-checkpoint.json")).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", choices=MODELS)
    parser.add_argument("--output", type=Path, default=Path("data/runtime/detector-checkpoints"))
    args = parser.parse_args()
    print(json.dumps(fetch(args.model, args.output), indent=2))
