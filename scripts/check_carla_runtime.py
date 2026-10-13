"""Read-only file/resource check; does not launch CARLA or prove a capture succeeds."""

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.simulation.carla_server import require_memory_headroom  # noqa: E402


def main():
    root = ROOT / "data/runtime/carla-server-recovery/server"
    binary = root / "CarlaUE4/Binaries/Linux/CarlaUE4-Linux-Shipping"
    libraries = [p for p in root.rglob("*") if p.is_file() and ".so" in p.name]
    invalid = []
    for p in [binary, *libraries]:
        if not p.is_file():
            invalid.append(str(p.relative_to(root)))
            continue
        with p.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                invalid.append(str(p.relative_to(root)))
    try:
        available = require_memory_headroom(10)
        launch = "memory_gate_passed_not_launched"
    except RuntimeError as exc:
        available = None
        launch = str(exc)
    result = {
        "kind": "carla_file_preflight_not_capture_evidence",
        "binary_exists": binary.is_file(),
        "libraries": len(libraries),
        "invalid_elf": invalid,
        "memory_launch_status": launch,
        "available_ram_gib": available,
        "disk_free_gib": shutil.disk_usage(ROOT).free / 1024**3,
        "native_capture_verified": False,
    }
    if binary.is_file():
        with binary.open("rb") as stream:
            result["binary_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    (ROOT / "eval/recovery-mvp-2026-10-13/carla-runtime-preflight.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return int(bool(invalid) or not libraries)


if __name__ == "__main__":
    raise SystemExit(main())
