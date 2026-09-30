"""Check raw files, frame mapping and available checkpoint hashes without loading pickle."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check(nusc: Path, lab: Path) -> dict:
    tables = nusc / "v1.0-mini"
    samples = json.loads((tables / "sample.json").read_text(encoding="utf-8"))
    records = json.loads((tables / "sample_data.json").read_text(encoding="utf-8"))
    missing = [r["filename"] for r in records if not (nusc / r["filename"]).is_file()]
    tokens = {r["token"] for r in samples}
    with (lab / "exports/L3E/samples.csv").open(encoding="utf-8-sig") as stream:
        exported = list(csv.DictReader(stream))
    unknown = [r["sample_token"] for r in exported if r["sample_token"] not in tokens]
    present, absent, bad = [], [], []
    for line in (lab / "models/CHECKPOINTS.sha256").read_text().splitlines():
        expected, relative = line.split(maxsplit=1)
        relative = relative.lstrip("*").removeprefix("./")
        path = lab / "models" / relative
        if not path.is_file():
            absent.append(relative)
        else:
            present.append(relative)
            if hashlib.file_digest(path.open("rb"), "sha256").hexdigest() != expected:
                bad.append(relative)
    return {"keyframes": len(samples), "sensor_records": len(records), "missing_sensor_files": len(missing),
            "exported_frames": len(exported), "unknown_export_tokens": unknown,
            "checkpoint_present": len(present), "checkpoint_absent": len(absent), "checkpoint_hash_errors": bad,
            "ok": len(samples) == 404 and len(exported) == 81 and not missing and not unknown and not bad}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--nusc-root", type=Path, default=ROOT / "data/nuscenes")
    parser.add_argument("--lab-root", type=Path, default=ROOT / "data/lab")
    args = parser.parse_args()
    report = check(args.nusc_root, args.lab_root)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["ok"] else 1)
