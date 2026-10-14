"""Restore sealed evidence from raw Git index blobs on a reused Windows runner."""

import hashlib
import io
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOTS = ("detector-pilot-2026-10-08", "detector-pilot-sparse-60s-2026-10-08")


def mismatches(root=ROOT):
    failures = []
    for pilot in PILOTS:
        directory = root / "eval" / pilot
        manifest = json.loads((directory / "bundle-manifest.json").read_bytes())
        for name, expected in manifest["files"].items():
            path = (directory / name).resolve()
            if not path.is_relative_to(directory.resolve()):
                raise ValueError("Evidence path outside pilot")
            if not path.is_file():
                failures.append({"pilot": pilot, "file": name, "error": "missing"})
                continue
            raw = path.read_bytes()
            if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
                failures.append({"pilot": pilot, "file": name, "bytes": len(raw), "expected_bytes": expected["bytes"]})
    return failures


def restore_index_blobs(root=ROOT):
    folders = [f"eval/{p}/" for p in PILOTS]
    entries = subprocess.check_output(["git", "ls-files", "--stage", "-z", *folders], cwd=root)
    indexed = []
    for row in entries.split(b"\0"):
        if not row:
            continue
        header, name = row.split(b"\t", 1)
        mode, oid, stage = header.split()
        path = name.decode("utf-8")
        if mode not in (b"100644", b"100755") or stage != b"0" or not (root / path).resolve().is_relative_to(root.resolve()):
            raise ValueError("Invalid evidence index entry")
        indexed.append((path, oid))
    # cat-file reads original blob bytes with no checkout filters or stat-cache
    # shortcut. One batch avoids hundreds of Git process launches on Windows.
    response = subprocess.check_output(["git", "cat-file", "--batch"],
                                       input=b"\n".join(oid for _, oid in indexed) + b"\n", cwd=root)
    stream = io.BytesIO(response)
    payloads = {}
    for name, expected_oid in indexed:
        oid, kind, size = stream.readline().split()
        if oid != expected_oid or kind != b"blob" or int(size) > 2_000_000:
            raise ValueError("Invalid or oversized evidence blob")
        raw = stream.read(int(size))
        if len(raw) != int(size) or stream.read(1) != b"\n":
            raise ValueError("Truncated evidence blob")
        payloads[name] = raw
    # Verify source bytes against all existing seals before any replacement.
    for pilot in PILOTS:
        prefix = f"eval/{pilot}/"
        manifest = json.loads(payloads[prefix + "bundle-manifest.json"])
        for name, expected in manifest["files"].items():
            raw = payloads[prefix + name]
            if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
                raise ValueError("Original Git blob does not match its seal; never rewrite hashes")
    restored = 0
    for name, raw in payloads.items():
        path = root / name
        if not path.is_file() or path.read_bytes() != raw:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            restored += 1
    return restored


def main():
    before = mismatches()
    print(json.dumps({"before_restore_mismatches": {"count": len(before), "examples": before[:3]}}), flush=True)
    restored = restore_index_blobs()
    after = mismatches()
    print(json.dumps({"restored_files": restored, "after_restore_mismatches": {"count": len(after), "examples": after[:3]}}), flush=True)
    if after:
        raise ValueError("Evidence restore failed; never rewrite hashes")
    from src.services.detector_pilot_evidence import snapshot

    for pilot in ("short", "sparse60"):
        value = snapshot(pilot)
        print(json.dumps({"pilot": pilot, "available": value["available"], "variants": len(value["variants"])}))


if __name__ == "__main__":
    main()
