"""Read-only adapters for the versioned lab exports. No CUDA or MATLAB imports."""

import csv
import io
import json
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

from src.config import PROJECT_ROOT, get_settings
from src.database import SessionLocal
from src.models.db_models import CameraImageDB, DetectionDB, FrameDB

DETECTORS = {
    "official_lidar": ("exports/L3E/pred_lidar_only_ego.csv", ["lidar"], "official"),
    "official_cl": ("exports/L3E/pred_lidar_camera_ego.csv", ["camera", "lidar"], "official"),
    "our_lidar": ("exports/L3E/pred_our_lidar_ego.csv", ["lidar"], "own"),
    "our_cl": ("exports/L3E/pred_our_bevfusion_ego.csv", ["camera", "lidar"], "own"),
    "crn": ("exports/L3E/pred_camera_radar_ego.csv", ["camera", "radar"], "official"),
    "fused": ("fusion/unified/unified_pretrained_ego.csv", ["camera", "lidar", "radar"], "official"),
    "fused_ours": ("fusion/unified/unified_ours_ego.csv", ["camera", "lidar", "radar"], "mixed"),
}
COORDINATES = {
    "frame": "ego",
    "x": "forward",
    "y": "left",
    "z": "up",
    "length_unit": "m",
    "yaw_unit": "rad",
    "yaw_direction": "CCW",
}
CAMERAS = ("CAM_FRONT", "CAM_FRONT_LEFT", "CAM_FRONT_RIGHT", "CAM_BACK", "CAM_BACK_LEFT", "CAM_BACK_RIGHT")
RISK_SYSTEMS = ("classical", "oracle")


@lru_cache(maxsize=32)
def read_csv(path: Path, modified: int):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def csv_rows(path: Path):
    return read_csv(path, path.stat().st_mtime_ns)


@lru_cache(maxsize=16)
def read_json(path: Path, modified: int):
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def json_data(path: Path):
    return read_json(path, path.stat().st_mtime_ns)


def frames():
    settings = get_settings()
    if (
        settings.lab_data_root != PROJECT_ROOT / "data/lab"
        and (settings.lab_data_root / "exports/L3E/samples.csv").is_file()
    ):
        rows = csv_rows(settings.lab_data_root / "exports/L3E/samples.csv")
        return [
            {
                "sample_token": r["sample_token"],
                "sample_idx": int(r["sample_idx"]),
                "scene": r["scene"],
                "timestamp_s": float(r["timestamp_s"]),
                "split": "mini_val",
            }
            for r in rows
        ]

    try:
        with SessionLocal() as session:
            db_records = session.query(FrameDB).order_by(FrameDB.sample_idx).all()
            if db_records:
                return [
                    {
                        "sample_token": r.sample_token,
                        "sample_idx": r.sample_idx,
                        "scene": r.scene,
                        "timestamp_s": r.timestamp_s,
                        "split": r.split,
                    }
                    for r in db_records
                ]
    except Exception:
        pass

    # Fallback to CSV
    csv_path = get_settings().lab_data_root / "exports/L3E/samples.csv"
    if not csv_path.is_file():
        return []
    rows = csv_rows(csv_path)
    return [
        {
            "sample_token": r["sample_token"],
            "sample_idx": int(r["sample_idx"]),
            "scene": r["scene"],
            "timestamp_s": float(r["timestamp_s"]),
            "split": "mini_val",
        }
        for r in rows
    ]


def frame(token: str):
    return next((item for item in frames() if item["sample_token"] == token), None)


def is_model_available(name: str) -> bool:
    settings = get_settings()
    root = settings.lab_data_root
    rel = DETECTORS[name][0]
    if (root / rel).is_file():
        return True
    if settings.lab_data_root == PROJECT_ROOT / "data/lab":
        try:
            with SessionLocal() as session:
                if session.query(DetectionDB).filter(DetectionDB.model_id == name).first():
                    return True
        except Exception:
            pass
    return False


def models():
    return [
        {
            "id": name,
            "sensors": sensors,
            "origin": origin,
            "mode": "precomputed",
            "available": is_model_available(name),
            "split": "mini_val",
            "contaminated": origin in {"official", "mixed"},
            "fusion_type": "object_level_late_fusion" if name.startswith("fused") else None,
        }
        for name, (rel, sensors, origin) in DETECTORS.items()
    ]


def detections(token: str, model: str, threshold: float):
    item = frame(token)
    if item is None:
        raise KeyError(token)

    rel = DETECTORS[model][0]

    # Try DB first if available
    try:
        with SessionLocal() as session:
            has_db_frame = session.query(FrameDB).filter(FrameDB.sample_token == token).first()
            if has_db_frame:
                has_model = session.query(DetectionDB).filter(DetectionDB.model_id == model).first()
                if not has_model and not (get_settings().lab_data_root / rel).is_file():
                    raise FileNotFoundError(rel)
                db_boxes = (
                    session.query(DetectionDB)
                    .filter(
                        DetectionDB.sample_token == token,
                        DetectionDB.model_id == model,
                        DetectionDB.score >= threshold,
                    )
                    .all()
                )
                boxes = [
                    {
                        "class_name": b.class_name,
                        "x": b.x,
                        "y": b.y,
                        "z": b.z,
                        "w": b.w,
                        "l": b.l,
                        "h": b.h,
                        "yaw": b.yaw,
                        "vx": b.vx,
                        "vy": b.vy,
                        "score": b.score,
                    }
                    for b in db_boxes
                ]
                return {
                    "frame": item,
                    "model": model,
                    "mode": "precomputed",
                    "coordinates": COORDINATES,
                    "boxes": boxes,
                }
    except FileNotFoundError:
        raise
    except Exception:
        pass

    # Fallback to CSV
    csv_file = get_settings().lab_data_root / rel
    if not csv_file.is_file():
        raise FileNotFoundError(rel)
    rows = csv_rows(csv_file)
    boxes = []
    for row in rows:
        if int(row["sample_idx"]) != item["sample_idx"] or float(row["score"]) < threshold:
            continue
        boxes.append(
            {
                "class_name": row["class"],
                **{key: float(row[key]) for key in ("x", "y", "z", "w", "l", "h", "yaw", "vx", "vy", "score")},
            }
        )
    return {"frame": item, "model": model, "mode": "precomputed", "coordinates": COORDINATES, "boxes": boxes}


def camera_path(token: str, channel: str):
    root = get_settings().nusc_root.resolve()
    table = json_data(root / "v1.0-mini/sample_data.json")
    record = next(
        (
            r
            for r in table
            if r["sample_token"] == token and r["is_key_frame"] and Path(r["filename"]).parts[-2] == channel
        ),
        None,
    )
    if record is None:
        raise KeyError(token)
    path = (root / record["filename"]).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Unsafe dataset path")
    return path


def camera_cache_path(token: str, channel: str) -> Path:
    cache_root = get_settings().resolved_camera_cache_dir.resolve()
    return cache_root / f"{token}_{channel}.jpg"


def get_cached_camera(token: str, channel: str) -> bytes | None:
    # 1. Try DB first
    try:
        with SessionLocal() as session:
            record = (
                session.query(CameraImageDB)
                .filter(CameraImageDB.sample_token == token, CameraImageDB.channel == channel)
                .first()
            )
            if record and record.image_data:
                return bytes(record.image_data)
    except Exception:
        pass

    # 2. Fallback to local file cache
    path = camera_cache_path(token, channel)
    if path.is_file():
        return path.read_bytes()
    return None


def save_cached_camera(token: str, channel: str, data: bytes) -> None:
    try:
        path = camera_cache_path(token, channel)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(f".tmp.{path.suffix}")
        temp_path.write_bytes(data)
        temp_path.replace(path)
    except OSError:
        pass


@lru_cache(maxsize=2)
def read_risk_mat(path: Path, modified: int):
    import scipy.io as sio

    return sio.loadmat(path)


def risk_heatmap_png(token: str, system: str, vmax: float = 0.3) -> bytes:
    """Render a precomputed Stage-H grid without MATLAB or live inference."""
    import numpy as np

    item = frame(token)
    if item is None:
        raise KeyError(token)
    if system not in RISK_SYSTEMS:
        raise ValueError("Unknown risk system")

    path = get_settings().lab_data_root / "stage_h/risk_out.mat"
    payload = read_risk_mat(path, path.stat().st_mtime_ns)
    key = f"risk_{system}"
    if key not in payload:
        raise FileNotFoundError(key)
    maps = np.asarray(payload[key])
    if maps.ndim != 3 or item["sample_idx"] >= maps.shape[0]:
        raise ValueError("Invalid Stage-H risk artifact")

    values = np.nan_to_num(maps[item["sample_idx"]], nan=0.0, posinf=vmax, neginf=0.0)
    scaled = np.clip(values / vmax, 0.0, 1.0)
    red = np.clip(3.0 * scaled, 0.0, 1.0)
    green = np.clip(3.0 * scaled - 1.0, 0.0, 1.0)
    blue = np.clip(3.0 * scaled - 2.0, 0.0, 1.0)
    rgb = (np.stack((red, green, blue), axis=-1) * 255).astype(np.uint8)
    image = Image.fromarray(np.flipud(rgb), mode="RGB").resize((600, 600), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(image)
    draw.polygon(((300, 285), (289, 311), (311, 311)), fill=(40, 220, 120), outline=(255, 255, 255))
    draw.text((12, 12), f"{system} · frame {item['sample_idx']} · max scale {vmax:.1f}", fill=(255, 255, 255))
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
