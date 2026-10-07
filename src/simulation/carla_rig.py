"""Full sensor recording. CARLA-native measurements, never model-ready nuScenes fiction.

This module stays NumPy-only so it can run in the isolated CARLA client runtime.
Ground truth files are separate from perception inputs; no GT inference features.
"""
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from src.inference.bev import carla_to_ego

FLIP = np.diag([1., -1., 1., 1.])
# CARLA x-forward/y-right/z-up -> optical x-right/y-down/z-forward.
OPTICAL = np.array([[0., 1., 0., 0.], [0., 0., -1., 0.],
                    [1., 0., 0., 0.], [0., 0., 0., 1.]])
SEMANTIC_DTYPE = np.dtype([("x", "<f4"), ("y", "<f4"), ("z", "<f4"),
                           ("cos", "<f4"), ("object", "<u4"), ("tag", "<u4")])
CAMERAS = {
    "CAM_FRONT": (1.5, 0, 1.7, 0),
    "CAM_FRONT_LEFT": (1, -0.7, 1.7, -55),
    "CAM_FRONT_RIGHT": (1, 0.7, 1.7, 55),
    "CAM_BACK": (-1.2, 0, 1.7, 180),
    "CAM_BACK_LEFT": (-1, -0.7, 1.7, -125),
    "CAM_BACK_RIGHT": (-1, 0.7, 1.7, 125),
}
RADARS = {
    "RADAR_FRONT": (2, 0, 0.7, 0),
    "RADAR_FRONT_LEFT": (1.7, -0.7, 0.7, -45),
    "RADAR_FRONT_RIGHT": (1.7, 0.7, 0.7, 45),
    "RADAR_BACK_LEFT": (-1.7, -0.7, 0.7, -135),
    "RADAR_BACK_RIGHT": (-1.7, 0.7, 0.7, 135),
}


def camera_intrinsic(width, height, fov):
    focal = width / (2 * math.tan(math.radians(fov) / 2))
    return np.array([[focal, 0, width / 2], [0, focal, height / 2], [0, 0, 1.]])


def radar_xyz(raw):
    """Input columns: radial velocity, azimuth, altitude, depth. No RCS/vector velocity."""
    v, azimuth, altitude, depth = np.asarray(raw).reshape(-1, 4).T
    planar = depth * np.cos(altitude)
    return np.column_stack((planar * np.cos(azimuth), planar * np.sin(azimuth),
                            depth * np.sin(altitude))).astype(np.float32)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def rig_specs(options, timestep):
    width, height, fov = options["width"], options["height"], options["fov"]
    specs, poses = {}, {}
    camera_attrs = {"image_size_x": str(width), "image_size_y": str(height), "fov": str(fov)}
    for name, pose in CAMERAS.items():
        specs[name] = ("sensor.camera.rgb", dict(camera_attrs))
        specs["GT_" + name] = ("sensor.camera.semantic_segmentation", dict(camera_attrs))
        poses[name] = poses["GT_" + name] = pose
    for name, pose in RADARS.items():
        specs[name] = ("sensor.other.radar", {"range": "100", "horizontal_fov": "90",
                                             "vertical_fov": "30", "points_per_second": "1500"})
        poses[name] = pose
    for name, channels, pps in [("LIDAR_TOP", 32, 600000), ("GT_LIDAR", 64, 1200000)]:
        specs[name] = ("sensor.lidar.ray_cast_semantic" if name.startswith("GT_") else "sensor.lidar.ray_cast",
                       {"range": "100", "channels": str(channels), "points_per_second": str(pps),
                        "rotation_frequency": str(1 / timestep), "upper_fov": "10", "lower_fov": "-30"})
        poses[name] = (0, 0, 2, 0)
    if options["include_64"]:
        specs["LIDAR_TOP_64"] = ("sensor.lidar.ray_cast", dict(specs["GT_LIDAR"][1]))
        poses["LIDAR_TOP_64"] = (0, 0, 2, 0)
    return specs, poses


class RigRecorder:
    def __init__(self, root, options, timestep):
        self.root = root
        self.options = options
        self.timestep = timestep
        self.specs, self.poses = rig_specs(options, timestep)
        self.frames = []
        self.artifact_bytes = 0
        self.counts = {name: [] for name in self.specs}
        self.raw_bytes = {name: 0 for name in self.specs}

    def transform(self, name, carla):
        x, y, z, yaw = self.poses[name]
        return carla.Transform(carla.Location(x=x, y=y, z=z), carla.Rotation(yaw=yaw))

    def artifact(self, path):
        self.artifact_bytes += path.stat().st_size
        return {"path": path.relative_to(self.root).as_posix(), "bytes": path.stat().st_size,
                "sha256": sha256_file(path)}

    def record(self, packets, snapshot, ego_matrix, actors, ego):
        frame_id = snapshot.frame
        timestamp = snapshot.timestamp.elapsed_seconds
        if set(packets) != set(self.specs):
            raise ValueError("Incomplete rig packet set")
        for packet in packets.values():
            if packet.frame != frame_id or abs(packet.timestamp - timestamp) > 1e-5:
                raise ValueError("Rig packet frame/timestamp does not match world snapshot")
        name = f"frame_{len(self.frames):05d}"
        inputs = self.root / "inputs" / name
        truth = self.root / "ground_truth" / name
        inputs.mkdir(parents=True)
        truth.mkdir(parents=True)
        metadata = {"id": name, "frame_id": frame_id, "timestamp": timestamp,
                    "ego_ground_to_world_carla": ego_matrix.tolist(), "sensors": {}}
        semantic = np.frombuffer(packets["GT_LIDAR"].raw_data, dtype=SEMANTIC_DTYPE)
        visible_ids = set(int(v) for v in semantic["object"])
        for sensor_name, packet in packets.items():
            is_gt = sensor_name.startswith("GT_")
            base = truth if is_gt else inputs
            sensor_matrix = np.asarray(packet.transform.get_matrix(), dtype=float)
            extrinsic = FLIP @ np.linalg.inv(ego_matrix) @ sensor_matrix
            item = {"frame_id": packet.frame, "timestamp": packet.timestamp,
                    "sensor_to_world_carla": sensor_matrix.tolist(), "sensor_to_ego_lab": extrinsic.tolist(),
                    "raw_payload_bytes": len(packet.raw_data), "ground_truth_only": is_gt}
            self.raw_bytes[sensor_name] += len(packet.raw_data)
            blueprint = self.specs[sensor_name][0]
            if "camera" in blueprint:
                pixels = np.frombuffer(packet.raw_data, dtype=np.uint8).reshape(packet.height, packet.width, 4)
                if (packet.width, packet.height) != (self.options["width"], self.options["height"]):
                    raise ValueError("Camera dimensions differ from calibration")
                item["intrinsic"] = camera_intrinsic(packet.width, packet.height, self.options["fov"]).tolist()
                item["optical_to_ego_lab"] = (extrinsic @ np.linalg.inv(OPTICAL)).tolist()
                if is_gt:
                    path = base / (sensor_name + ".npy")
                    np.save(path, pixels[:, :, 2])  # Raw BGRA red channel contains semantic IDs.
                    item["encoding"] = "CARLA_0.9.16_semantic_tag_uint8"
                else:
                    path = base / (sensor_name + ".png")
                    packet.save_to_disk(str(path))
                    item["encoding"] = "RGB_PNG"
                count = packet.width * packet.height
            elif "semantic" in blueprint:
                path = base / (sensor_name + ".npz")
                xyz = np.column_stack((semantic["x"], semantic["y"], semantic["z"]))
                np.savez_compressed(path, raw=semantic, points_ego=carla_to_ego(xyz, sensor_matrix, ego_matrix))
                count = len(semantic)
                item["encoding"] = "xyz_incidence_actor_id_semantic_tag"
            else:
                raw = np.frombuffer(packet.raw_data, dtype="<f4").reshape(-1, 4)
                if not np.isfinite(raw).all():
                    raise ValueError("Non-finite sensor measurement")
                xyz = radar_xyz(raw) if "radar" in blueprint else raw[:, :3]
                path = base / (sensor_name + ".npz")
                np.savez_compressed(path, raw=raw, points_ego=carla_to_ego(xyz, sensor_matrix, ego_matrix))
                count = len(raw)
                item["encoding"] = "velocity_azimuth_altitude_depth" if "radar" in blueprint else "XYZI_CARLA_0_to_1"
            item["elements"] = int(count)
            self.counts[sensor_name].append(int(count))
            item["artifact"] = self.artifact(path)
            metadata["sensors"][sensor_name] = item
        import carla
        boxes = []
        inv_ego = np.linalg.inv(ego_matrix)
        for actor in actors:
            if actor.id == ego.id:
                continue
            bb = actor.bounding_box
            matrix = inv_ego @ np.asarray(actor.get_transform().get_matrix()) @ np.asarray(
                carla.Transform(bb.location, bb.rotation).get_matrix())
            center = FLIP[:3, :3] @ matrix[:3, 3]
            velocity = actor.get_velocity()
            velocity_ego = FLIP[:3, :3] @ inv_ego[:3, :3] @ [velocity.x, velocity.y, velocity.z]
            boxes.append({"actor_id": actor.id, "type_id": actor.type_id,
                          "center_ego": center.tolist(), "size_lwh": [bb.extent.x * 2, bb.extent.y * 2, bb.extent.z * 2],
                          "rotation_ego": (FLIP[:3, :3] @ matrix[:3, :3] @ FLIP[:3, :3]).tolist(),
                          "velocity_world_in_ego_axes": velocity_ego.tolist(),
                          "semantic_lidar_visible": actor.id in visible_ids})
        velocity = ego.get_velocity()
        metadata["ego_speed_mps"] = math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2)
        gt_path = truth / "actors.json"
        gt_path.write_text(json.dumps({"frame_id": frame_id, "timestamp": timestamp, "boxes": boxes},
                                      allow_nan=False), encoding="utf-8")
        metadata["actor_ground_truth"] = self.artifact(gt_path)
        meta_path = self.root / (name + ".json")
        meta_path.write_text(json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8")
        self.frames.append({"id": name, "frame_id": frame_id, "timestamp": timestamp,
                            "metadata": self.artifact(meta_path), "visible_actor_count": sum(
                                box["semantic_lidar_visible"] for box in boxes)})

    def finish(self, scenario, common):
        if len(self.frames) != scenario.frames:
            raise ValueError("Incomplete full-rig capture")
        manifest = dict(common, schema_version=1, kind="carla_raw_sensor_episode", status="complete",
                        rig_options=self.options, frames=self.frames, scenario=scenario.model_dump(),
                        sensor_specs=self.specs, sensor_poses_carla=self.poses,
                        sensor_element_counts=self.counts, sensor_raw_payload_bytes=self.raw_bytes,
                        coordinate_systems={"raw": "CARLA x-forward/y-right/z-up",
                                            "ego_lab": "x-forward/y-left/z-up, bounding-box bottom origin",
                                            "camera_optical": "x-right/y-down/z-forward"},
                        artifact_bytes=self.artifact_bytes,
                        perception_ready=False, measured_gpu_work=False,
                        limitations=[
                            "Synthetic CARLA geometry/calibration, not nuScenes-equivalent rig or calibrated hardware",
                            "Radar supplies radial velocity only; RCS and full compensated velocity are unavailable",
                            "Semantic LiDAR is an independent reference; labels are not point-aligned to input LiDAR",
                            "Weather changes rendered RGB; no validated weather degradation model for LiDAR/radar",
                            "GT boxes cover actors spawned by this episode, not every static/parked vehicle or map prop",
                            "GT is engine actor boxes and visible semantic surfaces, not complete occupancy/free-space truth",
                            "Actor population may be outside ego ROI; inspect per-frame visible_actor_count",
                            "No detector adapter, GPU perception timing, trained policy, or ROS publication in this capture",
                        ])
        # Write only after all frames succeed. Readers reject partial directories.
        pending = self.root / "manifest.pending"
        pending.write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
        pending.replace(self.root / "manifest.json")
        return manifest


def verify_episode(root):
    """Checksum, synchrony and calibration validation before any adapter consumes files."""
    root = Path(root).resolve()
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest.get("kind") != "carla_raw_sensor_episode" or manifest.get("status") != "complete":
        raise ValueError("Not a complete raw sensor episode")
    frames = manifest["frames"]
    if not frames or len(frames) != manifest["scenario"]["frames"]:
        raise ValueError("Incomplete episode frame count")
    expected = set(rig_specs(manifest["rig_options"], manifest["scenario"]["timestep"])[0])
    if set(manifest["sensor_specs"]) != expected:
        raise ValueError("Rig sensor inventory mismatch")
    def checked(artifact):
        path = (root / artifact["path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Artifact path escapes episode")
        if path.stat().st_size != artifact["bytes"] or sha256_file(path) != artifact["sha256"]:
            raise ValueError("Artifact checksum mismatch: " + artifact["path"])
        return path
    previous = None
    element_totals = {name: 0 for name in expected}
    for frame in frames:
        stamp = (frame["frame_id"], frame["timestamp"])
        if previous is not None:
            cadence = round(manifest["scenario"]["capture_interval"] / manifest["scenario"]["timestep"])
            if stamp[0] - previous[0] != cadence or abs(stamp[1] - previous[1] - cadence * manifest["scenario"]["timestep"]) > 1e-5:
                raise ValueError("Episode has a gap or invalid timestamp cadence")
        previous = stamp
        metadata = json.loads(checked(frame["metadata"]).read_text())
        if (metadata["frame_id"], metadata["timestamp"]) != stamp or set(metadata["sensors"]) != expected:
            raise ValueError("Frame metadata mismatch")
        ego = np.asarray(metadata["ego_ground_to_world_carla"])
        if ego.shape != (4, 4) or not np.isfinite(ego).all():
            raise ValueError("Invalid ego calibration")
        for name, sensor in metadata["sensors"].items():
            if sensor["frame_id"] != stamp[0] or abs(sensor["timestamp"] - stamp[1]) > 1e-5:
                raise ValueError("Sensor synchrony mismatch")
            measured = np.asarray(sensor["sensor_to_ego_lab"])
            expected_matrix = FLIP @ np.linalg.inv(ego) @ np.asarray(sensor["sensor_to_world_carla"])
            if not np.allclose(measured, expected_matrix, atol=1e-6):
                raise ValueError("Extrinsic calibration mismatch")
            if "intrinsic" in sensor:
                options = manifest["rig_options"]
                if not np.allclose(sensor["intrinsic"], camera_intrinsic(options["width"], options["height"], options["fov"])):
                    raise ValueError("Camera intrinsic mismatch")
                if not np.allclose(sensor["optical_to_ego_lab"], measured @ np.linalg.inv(OPTICAL)):
                    raise ValueError("Camera optical calibration mismatch")
            path = checked(sensor["artifact"])
            if sensor["ground_truth_only"] != name.startswith("GT_"):
                raise ValueError("GT/input boundary mismatch")
            if path.suffix == ".npz":
                with np.load(path, allow_pickle=False) as data:
                    raw, points = data["raw"], data["points_ego"]
                    if name == "GT_LIDAR":
                        if raw.dtype != SEMANTIC_DTYPE or raw.ndim != 1:
                            raise ValueError("Invalid semantic LiDAR encoding")
                        xyz = np.column_stack((raw["x"], raw["y"], raw["z"]))
                    else:
                        if raw.ndim != 2 or raw.shape[1] != 4 or not np.isfinite(raw).all():
                            raise ValueError("Invalid point input encoding")
                        xyz = radar_xyz(raw) if name.startswith("RADAR_") else raw[:, :3]
                    if points.shape != (len(raw), 3) or len(raw) != sensor["elements"]:
                        raise ValueError("Point count/shape mismatch")
                    converted = carla_to_ego(xyz, np.asarray(sensor["sensor_to_world_carla"]), ego)
                    if not np.isfinite(points).all() or not np.allclose(points, converted, atol=1e-5):
                        raise ValueError("Point coordinates/calibration mismatch")
            elif path.suffix == ".npy":
                tags = np.load(path, allow_pickle=False)
                if tags.dtype != np.uint8 or tags.shape != (options["height"], options["width"]):
                    raise ValueError("Invalid camera GT tag encoding")
            elif path.suffix == ".png":
                from PIL import Image
                with Image.open(path) as image:
                    image.load()
                    if image.size != (options["width"], options["height"]):
                        raise ValueError("RGB camera size mismatch")
            else:
                raise ValueError("Unknown sensor artifact encoding")
            element_totals[name] += sensor["elements"]
        actor_gt = json.loads(checked(metadata["actor_ground_truth"]).read_text())
        if actor_gt["frame_id"] != stamp[0] or actor_gt["timestamp"] != stamp[1]:
            raise ValueError("Actor GT synchrony mismatch")
    return {"status": "verified", "frames": len(frames), "sensors": len(expected),
            "duration_between_first_last_s": frames[-1]["timestamp"] - frames[0]["timestamp"],
            "element_totals": element_totals, "manifest_sha256": sha256_file(root / "manifest.json"),
            "perception_ready": False}
