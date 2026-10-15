"""Install a fixed, checksum-verified native PPO playback bundle. No execution or training."""

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "deploy/artifacts/native-ppo-demo.zip"
RUNS = ("native-online-full20-retry1-20261014", "native-online-ppo20-20261014")


def allowed(name):
    if name in {
        "data/lab/models/occupancy/variants/our_occupancy_lidar.pth",
        "data/lab/models/CHECKPOINTS.sha256",
        "eval/recovery-mvp-2026-10-13/native-input-adapter.json",
        "eval/recovery-mvp-2026-10-13/native-input-adapter.sha256",
        *[f"data/native-rl-measured-v1-20261013/{f}" for f in ("audit.json", "audit.sha256", "replay.json")],
        *[f"data/native-rl-ppo-v1-20261013/{f}" for f in (
            "report.json", "report.sha256", "training-plan.json", "training-plan.sha256",
            "validation-policy-4096.zip")],
    }:
        return True
    for run in RUNS:
        prefix = f"data/{run}/"
        if name.startswith(prefix):
            part = name[len(prefix):]
            return bool(re.fullmatch(
                r"(?:report|plan|artifacts)\.(?:json|sha256)|capture/manifest\.json|"
                r"capture/frame_00(?:0[0-9]|1[0-9])\.(?:npz|json|png)|"
                r"capture/online-predictions/00(?:0[0-9]|1[0-9])\.npz|"
                r"capture/ipc/signal-00(?:0[0-9]|1[0-9])\.npz", part))
    return False


def install(archive, destination):
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)) or "manifest.json" not in names:
            raise ValueError("Duplicate or missing bundle manifest")
        if bundle.getinfo("manifest.json").file_size > 100_000:
            raise ValueError("Oversized manifest")
        manifest = json.loads(bundle.read("manifest.json"))
        files = manifest.get("files", {})
        if (manifest.get("kind") != "native_ppo_playback_bundle_v1" or not files
                or len(files) > 250 or set(names) != {*files, "manifest.json"}
                or sum(bundle.getinfo(n).file_size for n in files) > 80_000_000):
            raise ValueError("Invalid native playback bundle")
        payloads = {}
        root = destination.resolve()
        for name, metadata in files.items():
            target = destination / name
            if not allowed(name) or not target.resolve().is_relative_to(root):
                raise ValueError("Invalid bundle path")
            if bundle.getinfo(name).file_size > 10_000_000:
                raise ValueError("Oversized artifact")
            raw = bundle.read(name)
            if len(raw) != metadata["bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
                raise ValueError("Artifact checksum mismatch")
            if target.exists() and target.read_bytes() != raw:
                raise ValueError("Refusing to replace an existing artifact")
            payloads[name] = raw
    # All inputs and existing files were verified before any write.
    for name, raw in payloads.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(raw)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--destination", type=Path, default=ROOT)
    args = parser.parse_args()
    value = install(args.archive, args.destination)
    print(json.dumps({"installed": len(value["files"]), "mode": "read-only playback; no training"}))


if __name__ == "__main__":
    main()
