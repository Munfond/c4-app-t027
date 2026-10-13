"""Explicit, sealed native input adapters. Never modify a checkpoint or captured raw data."""

import hashlib
import json
import math

import numpy as np

from src.config import get_settings
from src.services.experiment_registry import verified_hash


def fingerprint(adapter_id):
    if adapter_id == "raw":
        return {"id": "raw"}
    if adapter_id != "intensity_mean_experimental":
        raise ValueError("Unknown native input adapter")
    path = get_settings().native_input_adapter_manifest
    try:
        raw = path.read_bytes()
        expected = path.with_suffix(".sha256").read_text().strip()
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise ValueError("Native adapter manifest unavailable or invalid") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected:
        raise ValueError("Native adapter manifest changed")
    if not isinstance(data, dict):
        raise ValueError("Invalid native adapter manifest")
    gain = data.get("gain")
    if (
        data.get("kind") != "native_input_mean_alignment_experimental_v1"
        or data.get("fitted_without_labels") is not True
        or type(gain) not in (int, float)
        or not math.isfinite(gain)
        or not 0 < gain <= 1
        or data.get("checkpoint_sha256") != verified_hash("occupancy_lidar")
    ):
        raise ValueError("Native adapter/checkpoint contract mismatch")
    return {
        "id": adapter_id,
        "manifest_sha256": digest,
        "gain": gain,
        "checkpoint_sha256": data["checkpoint_sha256"],
        "notice": "Experimental input alignment; validated only on limited Town01 captures, not real-world safety",
    }


def catalog():
    items = [{"id": "raw", "available": True, "label": "Đầu vào gốc"}]
    item = {"id": "intensity_mean_experimental", "label": "Căn chỉnh intensity · thử nghiệm"}
    try:
        item.update(fingerprint(item["id"]), available=True)
    except (OSError, ValueError) as exc:
        item.update(available=False, notice=str(exc))
    return [*items, item]


def apply(frames, frozen):
    if frozen["id"] == "raw":
        return frames
    output = []
    for frame in frames:
        x = frame["x"]
        if x.shape != (7, 200, 200) or not np.isfinite(x).all():
            raise ValueError("Invalid native feature tensor")
        adjusted = x.copy()
        adjusted[3] *= frozen["gain"]
        output.append({**frame, "x": adjusted})
    return output
