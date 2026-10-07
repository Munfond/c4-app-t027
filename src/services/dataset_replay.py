"""Read raw nuScenes-mini, reduce sensors BEFORE feature extraction, keep reference fixed."""

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from PIL import Image

from src.config import get_settings
from src.inference.bev import cells, lidar_features
from src.inference.camera_replay import CameraDetector, camera_variant, detection_retention, weather_image
from src.models.replay import CAMERAS, RADARS


def dataset():
    from legacy.streamlit_lab.tools.local.nuscenes_local import NuScenesMini

    root = get_settings().nusc_root
    if not (root / "v1.0-mini/sample.json").is_file():
        raise FileNotFoundError("Raw nuScenes-mini missing: configure NUSC_ROOT with v1.0-mini, samples and sweeps")
    return NuScenesMini(str(root))


def safe_file(ds, filename):
    root = Path(ds.root).resolve()
    path = (root / filename).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Dataset filename escapes NUSC_ROOT")
    if not path.is_file():
        raise FileNotFoundError(
            f"Thiếu file dữ liệu nuScenes: {filename}. "
            "Hãy giải nén đủ samples và sweeps từ v1.0-mini.tgz vào NUSC_ROOT. "
            "LiDAR sweeps được dùng tạo nhãn tham chiếu IoU; không thể bỏ qua file thiếu."
        )
    return path


def catalog():
    try:
        ds = dataset()
        scenes = []
        for scene in sorted(ds.scene.values(), key=lambda s: s["name"]):
            tokens = [t for t in ds.by_split["val"] if ds.sample[t]["scene_token"] == scene["token"]]
            if not tokens:
                continue
            first = tokens[0]
            available = {}
            for channel in ["LIDAR_TOP", *RADARS, *CAMERAS]:
                record = ds.key.get((first, channel))
                available[channel] = bool(record and (Path(ds.root) / record["filename"]).is_file())
            counts = [len(ds.boxes(t)) for t in tokens]
            scenes.append({
                "id": scene["name"], "description": scene.get("description", ""), "frames": len(tokens),
                "mean_annotated_objects": float(np.mean(counts)), "first_frame_sensors": available,
            })
        return {"ready": bool(scenes), "scenes": scenes, "error": None,
                "camera_detector_configured": bool(get_settings().replay_camera_onnx),
                "limitations": ["mini-val only; first-frame availability is not a full dataset validation",
                                "Traffic filter uses annotated object count; highway must be verified manually"]}
    except (FileNotFoundError, ValueError, KeyError, OSError) as exc:
        return {"ready": False, "scenes": [], "error": str(exc),
                "camera_detector_configured": bool(get_settings().replay_camera_onnx)}


def tokens_for(ds, scenario):
    tokens = [t for t in ds.by_split["val"] if ds.scene[ds.sample[t]["scene_token"]]["name"] == scenario.scene_id]
    tokens.sort(key=lambda t: ds.sample[t]["timestamp"])
    if scenario.traffic != "all":
        counts = {t: len(ds.boxes(t)) for t in tokens}
        if counts:
            boundary = float(np.median(list(counts.values())))
            tokens = [t for t in tokens if (counts[t] > boundary if scenario.traffic == "crowded" else counts[t] <= boundary)]
    if len(tokens) < scenario.frames:
        raise ValueError("Not enough mini-val frames for requested scene/traffic filter; reduce frames or change filter")
    return tokens[:scenario.frames]


def validate_trial(trial, ds=None):
    ds = ds or dataset()
    for token in tokens_for(ds, trial.scenario):
        for channel in ["LIDAR_TOP", *trial.radars, *trial.cameras]:
            if (token, channel) not in ds.key:
                raise ValueError(f"Dataset missing sensor channel {channel}")
            safe_file(ds, ds.key[(token, channel)]["filename"])
        # Labels require up to ten previous LiDAR sweeps, independent of profile.
        previous = ds.key[(token, "LIDAR_TOP")]["prev"]
        for _ in range(10):
            if not previous:
                break
            record = ds.sd[previous]
            safe_file(ds, record["filename"])
            previous = record["prev"]
    path = get_settings().replay_camera_onnx
    if path and not path.is_file():
        raise FileNotFoundError("Configured REPLAY_CAMERA_ONNX file is missing")
    if path and importlib.util.find_spec("onnxruntime") is None:
        raise ValueError("Install requirements-camera-replay.txt before configuring REPLAY_CAMERA_ONNX")


def rng_for(seed, token, channel):
    digest = hashlib.sha256(f"{seed}:{token}:{channel}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "little"))


def reduce_points(points, spec, rng, origin=None, rotation=None):
    """Filter in sensor coordinates, then subset; returned points remain in ego frame."""
    local = points if origin is None else (points - origin) @ rotation
    distance = np.linalg.norm(local, axis=1)
    azimuth = np.abs(np.degrees(np.arctan2(local[:, 1], local[:, 0])))
    keep = np.flatnonzero(np.isfinite(points).all(axis=1) & (distance <= spec.range_m) & (azimuth <= spec.horizontal_fov / 2))
    count = int(np.ceil(len(keep) * spec.keep_fraction))
    if count < len(keep):
        # Stable seeded permutation makes lower fractions nested for the same source.
        keep = keep[rng.permutation(len(keep))[:count]]
    output = points[keep].copy()
    if spec.noise_std_m:
        output += rng.normal(0, spec.noise_std_m, output.shape)
    return output, keep


def radar_features(parts):
    features = np.zeros((3, 200, 200), dtype=np.float32)
    hits, rcs, speed = (np.zeros((200, 200)) for _ in range(3))
    for points, reflectivity, velocity in parts:
        valid = np.isfinite(points).all(axis=1) & np.isfinite(reflectivity) & np.isfinite(velocity)
        points, reflectivity, velocity = points[valid], reflectivity[valid], velocity[valid]
        r, c, ok = cells(points)
        np.add.at(hits, (r, c), 1)
        np.add.at(rcs, (r, c), reflectivity[ok])
        np.add.at(speed, (r, c), velocity[ok])
    features[0] = np.log1p(hits) / 2
    features[1] = rcs / np.maximum(hits, 1) / 50
    features[2] = speed / np.maximum(hits, 1) / 20
    return features


def frames(trial, root, pulse):
    from legacy.streamlit_lab.tools.local.nuscenes_local import qR

    ds = dataset()
    validate_trial(trial, ds)
    tokens = tokens_for(ds, trial.scenario)
    root.mkdir(parents=True, exist_ok=True)
    detector = CameraDetector()
    records, camera_rows, costs = [], [], []
    reference_digest = hashlib.sha256()
    for index, token in enumerate(tokens):
        pulse(f"replay:{index + 1}/{len(tokens)}")
        source_points, intensity = ds.keyframe_lidar(token)
        lidar_cal = ds.cs[ds.key[(token, "LIDAR_TOP")]["calibrated_sensor_token"]]
        points, retained = reduce_points(source_points, trial.profile.lidar, rng_for(trial.scenario.seed, token, "lidar"),
                                        np.array(lidar_cal["translation"]), qR(lidar_cal["rotation"]))
        x = lidar_features(points, intensity[retained])
        reference_digest.update(token.encode())
        reference_digest.update(np.ascontiguousarray(source_points).tobytes())
        reference_digest.update(np.ascontiguousarray(intensity).tobytes())
        radar_parts, radar_count, original_radar_count = [], 0, 0
        for channel in trial.radars:
            parts = ds.keyframe_radar(token, chans=(channel,))
            for raw, rcs, speed in parts:
                for value in (raw, rcs, speed):
                    reference_digest.update(np.ascontiguousarray(value).tobytes())
                cal = ds.cs[ds.key[(token, channel)]["calibrated_sensor_token"]]
                reduced, retained_radar = reduce_points(raw, trial.profile.radar,
                    rng_for(trial.scenario.seed, token, channel), np.array(cal["translation"]), qR(cal["rotation"]))
                radar_parts.append((reduced, rcs[retained_radar], speed[retained_radar]))
                radar_count += len(reduced)
                original_radar_count += len(raw)
        x[4:] = radar_features(radar_parts)
        labels = ds.labels(token)  # Always original sweeps, never reduced points.
        rotation, translation = ds.pose(token)
        for value in (labels, rotation, translation):
            reference_digest.update(np.ascontiguousarray(value).tobytes())
        camera_bytes = 0
        for channel in trial.cameras:
            pulse(f"camera:{index + 1}:{channel}")
            path = safe_file(ds, ds.key[(token, channel)]["filename"])
            with Image.open(path) as source:
                if source.width * source.height > get_settings().max_image_pixels:
                    raise ValueError("Camera image exceeds configured pixel limit")
                original = source.convert("RGB")
            reference = weather_image(original, trial.scenario.weather, trial.scenario.weather_strength,
                                      rng_for(trial.scenario.seed, token, channel))
            reference_digest.update(np.asarray(reference).tobytes())
            reduced, payload, quality = camera_variant(reference, trial.profile.camera)
            calibration = ds.cs[ds.key[(token, channel)]["calibrated_sensor_token"]]
            intrinsic = calibration.get("camera_intrinsic")
            scaled_intrinsic = None
            if intrinsic:
                scaled = np.asarray(intrinsic, dtype=float).copy()
                scaled[0] *= reduced.width / reference.width
                scaled[1] *= reduced.height / reference.height
                scaled_intrinsic = scaled.tolist()
            camera_bytes += len(payload)
            # Every saved camera is paired with its exact environmental reference.
            reference.save(root / f"{index:04d}_{channel}_reference.jpg", quality=95)
            (root / f"{index:04d}_{channel}.jpg").write_bytes(payload)
            baseline_boxes, boxes = detector.predict(reference), detector.predict(reduced)
            if boxes is not None:
                boxes = np.asarray(boxes).reshape(-1, 6)
                boxes[:, [0, 2]] *= reference.width / reduced.width
                boxes[:, [1, 3]] *= reference.height / reduced.height
                retention = detection_retention(np.asarray(baseline_boxes).reshape(-1, 6), boxes)
            else:
                retention = None
            camera_rows.append({"frame": index, "channel": channel, **quality,
                "camera_intrinsic": intrinsic, "profile_camera_intrinsic": scaled_intrinsic,
                "sensor_rotation": calibration["rotation"], "sensor_translation": calibration["translation"],
                "detection_retention": retention, "baseline_detections": len(baseline_boxes) if baseline_boxes is not None else None,
                "detections": boxes.tolist() if boxes is not None else None})
        costs.append({"lidar_payload_bytes": len(points) * 5 * 4,
                      "radar_payload_bytes": radar_count * 18 * 4, "camera_encoded_bytes": camera_bytes,
                      "lidar_points": len(points), "radar_points": radar_count,
                      "original_lidar_points": len(source_points), "original_radar_points": original_radar_count})
        records.append({"id": token, "x": x, "labels": labels, "valid": np.ones((200, 200), bool),
                        "flow": np.zeros((2, 200, 200), np.float32), "flow_valid": np.zeros((200, 200), bool),
                        "rotation": rotation, "translation": translation})
        np.savez_compressed(root / f"{index:04d}.npz", points=points, x=x, labels=labels,
            radar_points=np.concatenate([p[0] for p in radar_parts]) if radar_parts else np.empty((0, 3)),
            radar_rcs=np.concatenate([p[1] for p in radar_parts]) if radar_parts else np.empty(0),
            radar_speed=np.concatenate([p[2] for p in radar_parts]) if radar_parts else np.empty(0),
            rotation=rotation, translation=translation)
    retention_rows = [r for r in camera_rows if r["baseline_detections"]]
    weighted_retention = (sum(r["detection_retention"] * r["baseline_detections"] for r in retention_rows)
                          / sum(r["baseline_detections"] for r in retention_rows)) if retention_rows else None
    manifest = {"source": "dataset_replay", "replay": trial.model_dump(),
        "frames": [{"id": t, "timestamp_s": ds.sample[t]["timestamp"] / 1e6} for t in tokens], "dataset_reference_sha256": reference_digest.hexdigest(),
        "sensor_cost": {key: float(np.mean([row[key] for row in costs])) for key in costs[0]},
        "camera": {"mode": "detector_consistency" if detector.session else "image_fidelity_only",
            "checkpoint_sha256": detector.digest, "mean_psnr_db": float(np.mean([r["psnr_db"] for r in camera_rows])),
            "detection_retention": weighted_retention, "rows": camera_rows,
            "latency_model_only_ms": float(np.mean(detector.timing)) if detector.timing else None},
        "limitations": ["Recorded-data reductions/corruptions, not simulation of new sensor hardware or mounting",
            "Payload costs per evaluated keyframe: 20-byte LiDAR, 72-byte radar records, JPEG camera bytes; no power/dollar cost",
            "Static occupancy pseudo-GT from original LiDAR sweeps; free includes unobserved cells",
            "Rain/fog image overlays are sensitivity tests; no physical radar/LiDAR weather attenuation",
            "Camera fidelity is not task accuracy; optional detector retention is consistency against predictions, not GT",
            "No camera fusion inference; calibration/FPS/beam changes are not inferred from point subsampling"]}
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return records, manifest
