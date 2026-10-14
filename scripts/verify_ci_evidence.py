"""Restore and verify sealed evidence after checkout on a reused Windows runner."""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PILOTS = ("detector-pilot-2026-10-08", "detector-pilot-sparse-60s-2026-10-08")


def mismatches():
    failures = []
    for pilot in PILOTS:
        directory = ROOT / "eval" / pilot
        manifest = json.loads((directory / "bundle-manifest.json").read_bytes())
        for name, expected in manifest["files"].items():
            path = (directory / name).resolve()
            if not path.is_relative_to(directory.resolve()):
                raise ValueError("Evidence path outside pilot")
            if not path.is_file():
                failures.append({"pilot": pilot, "file": name, "error": "missing"})
                continue
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            if len(raw) != expected["bytes"] or digest != expected["sha256"]:
                failures.append({"pilot": pilot, "file": name, "bytes": len(raw),
                                 "expected_bytes": expected["bytes"], "sha256": digest,
                                 "expected_sha256": expected["sha256"]})
    return failures


def main():
    before = mismatches()
    print(json.dumps({"before_restore_mismatches": before}))
    # Attribute changes alone may leave unchanged files in the previous checkout
    # representation. Re-export only tracked eval files, never regenerate seals.
    names = subprocess.check_output(["git", "ls-files", "-z", "eval/"], cwd=ROOT)
    subprocess.run(["git", "checkout-index", "--force", "--stdin", "-z"],
                   input=names, cwd=ROOT, check=True)
    after = mismatches()
    print(json.dumps({"after_restore_mismatches": after}))
    if after:
        raise ValueError("Original Git evidence does not match its seals; do not rewrite hashes")
    from src.services.detector_pilot_evidence import snapshot

    for pilot in ("short", "sparse60"):
        value = snapshot(pilot)
        print(json.dumps({"pilot": pilot, "available": value["available"], "variants": len(value["variants"])}))


if __name__ == "__main__":
    main()
