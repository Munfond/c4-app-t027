"""Pinned NVIDIA compiler/headers inside data/runtime; does not change the GPU driver.

Run with Python >= 3.12 for tar extraction with the data security filter.
Package SHA256 values verified against NVIDIA linux-64 repodata on 2026-10-08.
"""
import hashlib
import json
import tarfile
import urllib.request
from pathlib import Path

PACKAGES = {
    "cuda-nvcc-12.1.105-0.tar.bz2": "bb8176dd6595206ac393c03a54d10643bdfa2101af8285f3e48caa73be0ef4d7",
    "cuda-cudart-dev-12.1.105-0.tar.bz2": "eaf9ea2d6a606eb2883a356a24afe04c0075d802054524d9c4c6c10bbeef40de",
    "cuda-cudart-12.1.105-0.tar.bz2": "8ce27449a0a1d98630b8b13669590a34b04bccf11bf9a98151a40541f7edf7ba",
    "cuda-cccl-12.1.109-0.tar.bz2": "b3aacf23055a5b0a2b8e52adbb59933775209e14274457dfb8673a3cf5f60ccb",
}
HEADER_PACKAGES = {
    "libcublas-dev-12.1.3.1-0.tar.bz2": "8ef2656ee6dc7b596f31a2149881e3bcc9e23d72574a00fbae0aa65542be324f",
    "libcusolver-dev-11.4.5.107-0.tar.bz2": "b033ec659a10b265c5725ce4823173b26f632c4d0df06a4c649eaa941d95168c",
    "libcusparse-dev-12.1.0.106-0.tar.bz2": "da7b401d9e95a73006dc28afdab5985ab14d948eacbdc826fbc6af7cf2fd0d0d",
}
BASE = "https://conda.anaconda.org/nvidia/linux-64/"


def main():
    root = Path("data/runtime/cuda-12.1")
    downloads = Path("data/runtime/downloads")
    root.mkdir(parents=True, exist_ok=True)
    downloads.mkdir(parents=True, exist_ok=True)
    for name, expected in (PACKAGES | HEADER_PACKAGES).items():
        path = downloads / name
        if not path.exists():
            partial = downloads / (name + ".part")
            with urllib.request.urlopen(BASE + name, timeout=60) as response, partial.open("wb") as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
            partial.replace(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("NVIDIA package SHA256 mismatch: " + name)
        with tarfile.open(path) as archive:
            members = [m for m in archive.getmembers() if not m.name.startswith("info/")
                       and (name not in HEADER_PACKAGES or m.name.startswith("include/"))]
            archive.extractall(root, members=members, filter="data")
        print("Verified/extracted:", name, flush=True)
    (root / "package-provenance.json").write_text(json.dumps({"source": BASE + "repodata.json",
                                                           "packages": PACKAGES, "headers_only": HEADER_PACKAGES}, indent=2))


if __name__ == "__main__":
    main()
