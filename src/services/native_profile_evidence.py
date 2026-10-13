"""Sealed physical profile pilot. Research evidence, never a native RL admission flag."""

import hashlib
import json
import math
import re

from src.config import get_settings
from src.inference.native_input import fingerprint
from src.services.experiment_registry import verified_hash


def read_report():
    path = get_settings().native_profile_pilot_report
    if not path.is_file():
        return {"ready": False, "notice": "Chưa có pilot 12 profile LiDAR đã audit."}
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Native pilot report exceeds bounded size")
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != path.with_suffix(".sha256").read_text().strip():
        raise ValueError("Native pilot report changed")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Invalid native pilot report")
    profiles = data.get("profiles", [])
    if (
        data.get("kind") != "audited_native_12_profile_integration_pilot"
        or data.get("status") != "complete_pilot"
        or data.get("native_rl_admitted") is not False
        or len(profiles) != 12
        or data.get("checkpoint_sha256") != verified_hash("occupancy_lidar")
        or data.get("adapter") != fingerprint("intensity_mean_experimental")
    ):
        raise ValueError("Native pilot/checkpoint/adapter contract mismatch")
    expected = {(c, r) for c in (16, 32, 64) for r in (150000, 300000, 450000, 600000)}
    if {(p["channels"], p["points_per_second"]) for p in profiles} != expected:
        raise ValueError("Incomplete physical profile catalog")
    for profile in profiles:
        if (
            profile.get("profile") != f"channels{profile['channels']}_{profile['points_per_second'] // 1000}k"
            or not re.fullmatch(r"[a-f0-9]{32}", profile.get("job_id", ""))
            or profile.get("frames") != 4
        ):
            raise ValueError("Invalid pilot profile identity")
        metrics = profile["metrics"]
        for value in (metrics["occupied_iou"], metrics["class_iou"]["object"], metrics["object_recall"]):
            if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Invalid pilot quality metric")
        rate = profile.get("sampled_lidar_bytes_per_second")
        if type(rate) not in (int, float) or not math.isfinite(rate) or rate < 0:
            raise ValueError("Invalid sampled payload rate")
    studies = data.get("study_evidence")
    if not isinstance(studies, list) or not studies or any(not study.get("environments") for study in studies):
        raise ValueError("Missing paired study evidence")
    return {"ready": True, "report": data, "evidence_sha256": digest}
