"""Fetch a separate, official CARLA 0.9.16 archive; never overwrite the old runtime."""

import argparse
import hashlib
import json
import shutil
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "https://downloads.carlasim.com/Linux/CARLA_0.9.16.tar.gz"
SIZE = 8346095504


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract", action="store_true")
    parser.add_argument(
        "--minimal", action="store_true", help="Omit debug symbols, HDMaps point clouds and bundled Python SDK"
    )
    parser.add_argument("--reserve-gib", type=float, default=4)
    args = parser.parse_args()
    if args.reserve_gib < 3:
        parser.error("Keep at least 3 GiB disk reserve")
    target = ROOT / "data/runtime/carla-server-recovery"
    if args.extract and (target / "server").exists():
        raise RuntimeError("Server folder already exists; inspect it instead of downloading again")
    target.mkdir(parents=True, exist_ok=True)
    archive = target / "CARLA_0.9.16.tar.gz"
    partial = archive.with_suffix(".gz.part")
    if not archive.is_file():
        offset = partial.stat().st_size if partial.exists() else 0
        if shutil.disk_usage(target).free < SIZE - offset + 8 * 1024**3:
            raise RuntimeError("Need remaining download size plus 8 GiB free; preserve existing files")
        request = urllib.request.Request(
            URL, headers={"User-Agent": "P027-Recovery/1.0", **({"Range": f"bytes={offset}-"} if offset else {})}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            if offset and (
                response.status != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-")
            ):
                raise RuntimeError("Server did not accept resume; existing partial preserved")
            with partial.open("ab" if offset else "wb") as stream:
                next_notice = offset
                while chunk := response.read(1024**2):
                    if shutil.disk_usage(target).free < 8 * 1024**3:
                        raise RuntimeError("Disk reserve reached; partial preserved")
                    stream.write(chunk)
                    offset += len(chunk)
                    if offset >= next_notice:
                        stream.flush()
                        (target / "download-progress.json").write_text(
                            json.dumps({"url": URL, "bytes": offset, "expected_bytes": SIZE, "status": "incomplete"})
                        )
                        print(f"{offset / SIZE:.1%} · {offset / 1024**3:.2f} GiB", flush=True)
                        next_notice = offset + 256 * 1024**2
        if offset != SIZE:
            raise RuntimeError("Archive size mismatch; incomplete file preserved")
        partial.rename(archive)
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if archive.stat().st_size != SIZE:
        raise RuntimeError("Archive size mismatch")
    (target / "archive-provenance.json").write_text(
        json.dumps(
            {
                "url": URL,
                "bytes": SIZE,
                "sha256": digest,
                "origin": "official release 0.9.16; TLS download, locally computed hash",
            },
            indent=2,
        )
    )
    (target / "download-progress.json").write_text(
        json.dumps({"url": URL, "bytes": SIZE, "expected_bytes": SIZE, "status": "completed", "extraction": "pending"})
    )
    if args.extract:
        destination = target / "server"
        if destination.exists():
            raise RuntimeError("Destination already exists; will not overwrite")
        with tarfile.open(archive, "r:gz") as bundle:
            members = bundle.getmembers()
            excluded = [
                m
                for m in members
                if args.minimal
                and (m.name.lstrip("./").startswith(("HDMaps/", "PythonAPI/")) or m.name.endswith(".debug"))
            ]
            omit = {m.name for m in excluded}
            members = [m for m in members if m.name not in omit]
            total = sum(m.size for m in members if m.isfile())
            (target / "extraction-plan.json").write_text(
                json.dumps(
                    {
                        "minimal": args.minimal,
                        "required_bytes": total,
                        "free_bytes": shutil.disk_usage(target).free,
                        "omitted": [m.name for m in excluded],
                    },
                    indent=2,
                )
            )
            print(
                f"Extract {total / 1024**3:.2f} GiB; free {shutil.disk_usage(target).free / 1024**3:.2f} GiB",
                flush=True,
            )
            if shutil.disk_usage(target).free < total + args.reserve_gib * 1024**3:
                raise RuntimeError(f"Need extracted size plus {args.reserve_gib:g} GiB free; archive preserved")
            destination.mkdir()
            bundle.extractall(destination, members=members, filter="data")
        print("Extracted into", destination, flush=True)
    (target / "download-progress.json").write_text(
        json.dumps({"url": URL, "bytes": SIZE, "expected_bytes": SIZE, "status": "completed"})
    )
    print("Archive complete:", digest, flush=True)


if __name__ == "__main__":
    main()
