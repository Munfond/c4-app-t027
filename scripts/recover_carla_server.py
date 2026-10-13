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
    args = parser.parse_args()
    target = ROOT / "data/runtime/carla-server-recovery"
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
    if args.extract:
        destination = target / "server"
        if destination.exists():
            raise RuntimeError("Destination already exists; will not overwrite")
        with tarfile.open(archive, "r:gz") as bundle:
            members = bundle.getmembers()
            total = sum(m.size for m in members if m.isfile())
            if shutil.disk_usage(target).free < total + 4 * 1024**3:
                raise RuntimeError("Need extracted size plus 4 GiB free; archive preserved")
            destination.mkdir()
            bundle.extractall(destination, filter="data")
        print("Extracted into", destination, flush=True)
    (target / "download-progress.json").write_text(
        json.dumps({"url": URL, "bytes": SIZE, "expected_bytes": SIZE, "status": "completed"})
    )
    print("Archive complete:", digest, flush=True)


if __name__ == "__main__":
    main()
