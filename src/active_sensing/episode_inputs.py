"""Read measured CARLA sensor files into the profile gate, never ground truth.

This is a sensor/monitor boundary, not a BEVFusion/CRN inference adapter.
CARLA radar ABI remains explicit; model-specific preprocessing must be validated.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image

from src.active_sensing.core import Observation
from src.simulation.carla_rig import point_arrays, sha256_file, storage_encoding, verify_episode


class RawEpisode:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.verification = verify_episode(self.root)
        self.manifest = json.loads((self.root / "manifest.json").read_text())
        self.storage = storage_encoding(self.manifest)

    def _artifact(self, artifact, prefix):
        path = (self.root / artifact["path"]).resolve()
        if not path.is_relative_to(self.root / prefix):
            raise ValueError(f"Artifact is outside {prefix} boundary")
        if path.stat().st_size != artifact["bytes"] or sha256_file(path) != artifact["sha256"]:
            raise ValueError("Episode changed after verification")
        return path

    def inputs(self, index):
        if not 0 <= index < len(self.manifest["frames"]):
            raise IndexError("Episode frame index out of range")
        frame = self.manifest["frames"][index]
        path = self._artifact(frame["metadata"], "")
        meta = json.loads(path.read_text())
        fid, timestamp = meta["frame_id"], meta["timestamp"]
        streams = {"camera": {}, "lidar": {}, "radar": {}}
        brightness, contrast, radar_targets = [], [], 0
        lidar_points = 0
        for name, sensor in meta["sensors"].items():
            if sensor["ground_truth_only"]:
                continue
            path = self._artifact(sensor["artifact"], "inputs")
            record = {"frame_id": fid, "timestamp_s": timestamp,
                      "sensor_to_ego_lab": sensor["sensor_to_ego_lab"],
                      "raw_payload_bytes": sensor["raw_payload_bytes"]}
            if name.startswith("CAM_"):
                with Image.open(path) as image:
                    pixels = np.asarray(image.convert("L"), dtype=np.float32) / 255
                    brightness.append(float(pixels.mean()))
                    contrast.append(float(pixels.std()))
                record.update(image_path=str(path), intrinsic=sensor["intrinsic"],
                              optical_to_ego_lab=sensor["optical_to_ego_lab"], encoding="RGB_PNG")
                streams["camera"][name.removeprefix("CAM_").lower()] = record
            else:
                raw, xyz = point_arrays(path, sensor, np.asarray(meta['ego_ground_to_world_carla']), self.storage)
                if name.startswith("LIDAR_"):
                    # No scaling to nuScenes intensity or fabricated timestamp feature.
                    points = np.column_stack((xyz, raw[:, 3]))
                    record.update(points=[tuple(row) for row in points.tolist()],
                                  point_frame="ego_lab", intensity_policy="CARLA_raw_0_to_1")
                    channels = "64" if name.endswith("_64") else "32"
                    streams["lidar"][channels] = record
                    if channels == "32":
                        lidar_points = len(raw)
                elif name.startswith("RADAR_"):
                    record.update(raw=raw.copy(), points_ego=xyz.copy(),
                                  raw_columns=("radial_velocity", "azimuth", "altitude", "depth"),
                                  vector_velocity_available=False, rcs_available=False)
                    streams["radar"][name.removeprefix("RADAR_").lower()] = record
                    radar_targets += len(raw)
        emitted = 600000 * self.manifest["scenario"]["timestep"]
        observation = Observation(timestamp_s=timestamp, speed_mps=meta["ego_speed_mps"],
                                  camera_brightness=float(np.mean(brightness)),
                                  camera_contrast=float(np.mean(contrast)),
                                  lidar_return_ratio=min(1., lidar_points / emitted),
                                  radar_targets=radar_targets, camera_health="ok", lidar_health="ok",
                                  radar_health="ok")
        capture = {"frame_id": fid, "timestamp_s": timestamp, "streams": streams,
                   "sensor_abi": "CARLA_0.9.16_raw", "point_frame": "ego_lab",
                   "detector_adapter_validated": False}
        return capture, observation
