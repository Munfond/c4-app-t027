"""Package/install the small precomputed mini_val outputs used by the cloud demo.

No raw sensor files, camera images or checkpoint weights are included.
Installation verifies every file before writing anything; it never replaces a cache.
"""

import argparse
import csv
import hashlib
import json
import re
import zipfile
from pathlib import Path

TASKS = ("radar", "occupancy", "flow")
ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"(radar|occupancy|flow)/[0-9a-f]{32}\.json")


def build_bundle(lab_root: Path, archive: Path):
    with (lab_root / "exports/L3E/samples.csv").open(encoding="utf-8-sig") as stream:
        frames = list(csv.DictReader(stream))
    tokens = sorted({frame["sample_token"] for frame in frames})
    if len(tokens) != len(frames) or not tokens or any(not re.fullmatch(r"[0-9a-f]{32}", t) for t in tokens):
        raise ValueError("Invalid or duplicate frame tokens")
    payloads = {}
    manifest = {"schema_version": 1, "split": "mini_val", "tokens": tokens, "tasks": list(TASKS), "files": {}}
    for task in TASKS:
        for token in tokens:
            name = f"{task}/{token}.json"
            raw = (lab_root / "cache/perception" / name).read_bytes()
            data = json.loads(raw)
            if data.get("task") != task or data.get("sample_token") != token or not data.get("source"):
                raise ValueError(f"Invalid artifact identity/provenance: {name}")
            payloads[name] = raw
            manifest["files"][name] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    payloads["manifest.json"] = json.dumps(manifest, sort_keys=True, indent=2).encode() + b"\n"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name, raw in sorted(payloads.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 10, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, raw, compresslevel=9)
    return manifest


def install_bundle(archive: Path, destination: Path):
    with zipfile.ZipFile(archive) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        tokens = manifest["tokens"]
        if (
            manifest.get("schema_version") != 1
            or manifest.get("split") != "mini_val"
            or manifest.get("tasks") != list(TASKS)
            or not tokens
            or len(tokens) != len(set(tokens))
            or any(not re.fullmatch(r"[0-9a-f]{32}", token) for token in tokens)
        ):
            raise ValueError("Invalid bundle manifest")
        expected = {f"{task}/{token}.json" for task in TASKS for token in tokens}
        names = bundle.namelist()
        if set(manifest["files"]) != expected or set(names) != expected | {"manifest.json"} or len(names) != len(set(names)):
            raise ValueError("Bundle entries do not match manifest")
        payloads = {}
        for name, metadata in manifest["files"].items():
            if not NAME.fullmatch(name):
                raise ValueError("Invalid bundle path")
            if bundle.getinfo(name).file_size > 1_000_000:
                raise ValueError("Artifact exceeds size limit")
            raw = bundle.read(name)
            if len(raw) != metadata["bytes"] or hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
                raise ValueError(f"Artifact hash mismatch: {name}")
            target = destination / name
            if target.exists() and target.read_bytes() != raw:
                raise ValueError(f"Refusing to replace existing cache: {name}")
            payloads[name] = raw
    for name, raw in payloads.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(raw)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("pack", "install"))
    parser.add_argument("--archive", type=Path, default=ROOT / "deploy/artifacts/perception-mini-val.zip")
    parser.add_argument("--lab-root", type=Path, default=ROOT / "data/lab")
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.action == "pack":
        manifest = build_bundle(args.lab_root, args.archive)
    else:
        manifest = install_bundle(args.archive, args.destination or args.lab_root / "cache/perception")
    print(json.dumps({"action": args.action, "frames": len(manifest["tokens"]), "artifacts": len(manifest["files"])}))


if __name__ == "__main__":
    main()
