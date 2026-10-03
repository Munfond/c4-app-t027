"""Precompute measured BEV points and processed cameras for an offline MVP VPS.

Run from repo root: python -m scripts.prepare_demo_media --cameras
Uses NUSC_ROOT, LAB_DATA_ROOT, PLATE_WEIGHTS and ANONYMIZER_ENABLED from .env.
Never copies raw camera images to the output cache.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path

from src.services import lab
from src.services.anonymizer import anonymize_bytes
from src.services.environment import build_environment


def atomic_write(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".tmp-{os.getpid()}")
    temp.write_bytes(data)
    temp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cameras", action="store_true", help="Process six cameras with MTCNN + plate YOLO")
    parser.add_argument("--limit", type=int, default=0, help="Limit frames for a smoke run; 0 = all")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    settings = lab.get_settings()
    frames = lab.frames()[: args.limit or None]
    if args.cameras and not settings.anonymizer_enabled:
        parser.error("Set ANONYMIZER_ENABLED=true to generate processed cameras")
    manifest = {
        "frames": len(frames),
        "camera_pipeline": "MTCNN + YOLO plate; may miss faces/plates",
        "plate_sha256": hashlib.sha256(settings.plate_weights.read_bytes()).hexdigest() if args.cameras else None,
        "files": [],
        "errors": [],
    }
    for index, frame in enumerate(frames, 1):
        token = frame["sample_token"]
        paths = [(settings.lab_data_root / "cache/environment" / f"{token}.json", None)]
        if args.cameras:
            paths += [(lab.camera_cache_path(token, channel), channel) for channel in lab.CAMERAS]
        for path, channel in paths:
            try:
                if args.overwrite or not path.is_file():
                    if channel:
                        raw = lab.camera_path(token, channel)
                        if raw.stat().st_size > settings.max_upload_bytes:
                            raise ValueError("Camera too large")
                        data = anonymize_bytes(raw.read_bytes())
                    else:
                        data = json.dumps(build_environment(token), separators=(",", ":")).encode()
                    atomic_write(path, data)
                manifest["files"].append({"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
            except Exception as exc:
                manifest["errors"].append({"token": token, "channel": channel, "error": str(exc)})
                print(f"FAILED {token} {channel}: {exc}", flush=True)
        print(
            f"{index}/{len(frames)} frames; {len(manifest['files'])} files; {len(manifest['errors'])} errors",
            flush=True,
        )
    atomic_write(settings.lab_data_root / "cache/media-manifest.json", json.dumps(manifest, indent=2).encode())
    if manifest["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
