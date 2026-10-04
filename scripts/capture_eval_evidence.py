"""Record real HTTP outputs for the documented manual evaluation; no browser automation."""

import argparse
import hashlib
import io
import json
import subprocess
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:3111")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8001")
    parser.add_argument("--output", type=Path, default=Path("eval/evidence/2026-10-04/api-probes.json"))
    args = parser.parse_args()
    records = []

    def request(path, base=None):
        started = time.perf_counter()
        url = (base or args.base_url).rstrip("/") + path
        try:
            response = urlopen(url, timeout=30)
        except HTTPError as error:
            response = error
        with response:
            raw = response.read()
            headers = {k.lower(): v for k, v in response.headers.items()}
            record = {
                "url": url,
                "captured_at_utc": datetime.now(UTC).isoformat(),
                "status": response.status,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "headers": {
                    k: v
                    for k, v in headers.items()
                    if k
                    in (
                        "content-type",
                        "x-camera-cache",
                        "x-anonymized",
                        "cache-control",
                        "x-risk-system",
                        "x-risk-uncalibrated",
                    )
                },
            }
            payload = None
            if "application/json" in headers.get("content-type", ""):
                payload = json.loads(raw)
                record["output"] = dict(payload) if isinstance(payload, dict) else payload
                for field in ("points", "cells", "vectors"):
                    if isinstance(payload, dict) and field in payload:
                        rows = payload[field]
                        record["output"].pop(field)
                        record["output"][field + "_count"] = len(rows)
                        record["output"][field + "_first_3"] = rows[:3]
                        if field == "cells":
                            record["output"]["class_counts"] = dict(Counter(rows))
                        record["output"]["payload_note"] = (
                            "Large arrays excerpted; byte count and SHA256 describe full HTTP body."
                        )
            elif headers.get("content-type", "").startswith("image/"):
                with Image.open(io.BytesIO(raw)) as image:
                    record["output"] = {"format": image.format, "width": image.width, "height": image.height}
            else:
                record["output"] = {"html_received": b"<!DOCTYPE html" in raw[:100] or b"<!doctype html" in raw[:100]}
            records.append(record)
        return payload, record

    checks = []

    def check(name, condition):
        checks.append({"name": name, "result": "PASS" if condition else "FAIL"})

    health, result = request("/health", args.backend_url)
    check("Backend health", result["status"] == 200 and health["status"] == "ok")
    for page in ("/lab", "/compare", "/benchmarks"):
        _, result = request(page)
        check("HTML " + page, result["status"] == 200)
    scenes, result = request("/api/v1/lab/scenes")
    check(
        "Scene catalog through Next rewrite",
        result["status"] == 200 and sum(s["frame_count"] for s in scenes["items"]) == 81,
    )
    models, result = request("/api/v1/lab/models")
    check("Model catalog", result["status"] == 200 and len(models["items"]) == 7)
    frames, _ = request("/api/v1/lab/scenes/scene-0103/frames")
    token = frames["items"][0]["sample_token"]
    frame_path = "/api/v1/lab/frames/" + token
    low, low_record = request(frame_path + "/detections?model=official_lidar&threshold=0.3")
    high, high_record = request(frame_path + "/detections?model=official_lidar&threshold=0.7")
    check(
        "Detection score filtering",
        low_record["status"] == high_record["status"] == 200
        and len(high["boxes"]) <= len(low["boxes"])
        and all(b["score"] >= 0.7 for b in high["boxes"]),
    )
    _, result = request(frame_path + "/detections?model=official_cl&threshold=0.3")
    check("Second model same frame", result["status"] == 200)
    environment, result = request(frame_path + "/environment")
    check("LiDAR environment", result["status"] == 200 and len(environment["points"]) > 0)
    _, result = request("/api/v1/lab/perception/tasks")
    check("Task catalog", result["status"] == 200)
    for task in ("radar", "occupancy", "flow"):
        payload, result = request(frame_path + "/perception/" + task)
        check(
            task + " aligned artifact",
            result["status"] == 200 and payload["sample_token"] == token and payload["task"] == task,
        )
    _, result = request(frame_path + "/perception/seg3d")
    check("Missing Seg3D explicitly unavailable", result["status"] == 503)
    for channel in ("CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT", "CAM_BACK", "CAM_BACK_LEFT", "CAM_BACK_RIGHT"):
        _, result = request(frame_path + "/cameras/" + channel)
        check(
            "Processed camera " + channel,
            result["status"] == 200
            and result["headers"].get("x-anonymized") == "true"
            and result["headers"]["content-type"] == "image/jpeg",
        )
    for system in ("classical", "oracle"):
        _, result = request(frame_path + "/risk?system=" + system + "&vmax=0.3")
        check(
            "Risk " + system,
            result["status"] == 200
            and result["headers"].get("x-risk-uncalibrated") == "true"
            and result["output"]["width"] == 600,
        )
    benchmarks, result = request("/api/v1/lab/benchmarks")
    check(
        "All four benchmark sources",
        result["status"] == 200 and all(s["available"] for s in benchmarks["sections"].values()),
    )
    for path, expected in (
        ("/api/v1/lab/scenes/not-a-scene/frames", 404),
        ("/api/v1/lab/frames/not-a-frame/detections", 404),
        (frame_path + "/detections?model=not-a-model", 422),
        (frame_path + "/detections?threshold=1.1", 422),
        (frame_path + "/perception/not-a-task", 422),
    ):
        _, result = request(path)
        check("Invalid input: " + path, result["status"] == expected)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    def git(*command):
        return subprocess.check_output(["git", *command], text=True).strip()

    build_id = Path("frontend/.next/BUILD_ID")
    document = {
        "scope": "Local HTTP observations supporting manual browser cases; not an ML accuracy evaluation or VPS deployment test.",
        "base_commit": git("rev-parse", "HEAD"),
        "branch": git("branch", "--show-current"),
        "working_tree_dirty": bool(git("status", "--porcelain")),
        "frontend_build_id": build_id.read_text().strip() if build_id.is_file() else None,
        "selected_frame": frames["items"][0],
        "checks": checks,
        "requests": records,
    }
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "token": token,
                "requests": len(records),
                "passed": sum(c["result"] == "PASS" for c in checks),
                "failed": [c for c in checks if c["result"] != "PASS"],
            },
            ensure_ascii=False,
        )
    )
    if any(c["result"] != "PASS" for c in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
