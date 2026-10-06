"""Synchronous CARLA capture for the LiDAR occupancy checkpoint.

RGB is recorded for review. No fabricated radar RCS/velocity is supplied to a model.
"""

import importlib
import json
import math
import queue
import random
import time

import numpy as np

from src.config import get_settings
from src.inference.bev import carla_to_ego, cells, footprint, lidar_features

SEMANTIC_DTYPE = np.dtype(
    [
        ("x", "<f4"),
        ("y", "<f4"),
        ("z", "<f4"),
        ("cos", "<f4"),
        ("object", "<u4"),
        ("tag", "<u4"),
    ]
)


def matching_sensor(q, frame_id, timeout, pulse):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pulse()
        try:
            packet = q.get(timeout=min(0.5, max(0.01, deadline - time.monotonic())))
        except queue.Empty:
            continue
        if packet.frame == frame_id:
            return packet
        if packet.frame > frame_id:
            raise RuntimeError(f"Sensor skipped frame {frame_id}")
    raise TimeoutError(f"Missing sensor frame {frame_id}")


def capture(scenario, root, pulse):
    try:
        carla = importlib.import_module("carla")
    except ImportError as exc:
        raise RuntimeError("CARLA Python client is not installed; use the matching server/client version") from exc
    settings = get_settings()
    rng = random.Random(scenario.seed)
    client = carla.Client(settings.carla_host, settings.carla_port)
    client.set_timeout(settings.carla_timeout_seconds)
    if client.get_client_version() != client.get_server_version():
        raise RuntimeError("CARLA client/server version mismatch")
    world = client.get_world()
    # Dedicated simulator required: loading a map changes its world.
    # Reset the world for every fresh trial; population/route comparisons need a common start.
    world = client.load_world(scenario.map)
    original = world.get_settings()
    original_weather = world.get_weather()
    actors, sensors, controllers = [], [], []
    tm = client.get_trafficmanager(settings.carla_tm_port)
    queues = {}
    root.mkdir(parents=True, exist_ok=True)
    try:
        synchronous = world.get_settings()
        synchronous.synchronous_mode = True
        synchronous.fixed_delta_seconds = scenario.timestep
        synchronous.no_rendering_mode = False
        world.apply_settings(synchronous)
        tm.set_synchronous_mode(True)
        tm.set_random_device_seed(scenario.seed)
        world.set_pedestrians_seed(scenario.seed)
        weather = carla.WeatherParameters(
            cloudiness=70 if scenario.weather == "rain" else 10,
            precipitation=70 if scenario.weather == "rain" else 0,
            precipitation_deposits=50 if scenario.weather == "rain" else 0,
            wetness=70 if scenario.weather == "rain" else 0,
            fog_density=70 if scenario.weather == "fog" else 0,
            fog_distance=5 if scenario.weather == "fog" else 0,
            sun_altitude_angle=60,
        )
        world.set_weather(weather)
        library = world.get_blueprint_library()
        spawns = world.get_map().get_spawn_points()
        if scenario.route_spawn_index >= len(spawns):
            raise ValueError("route_spawn_index is outside this map's spawn points")
        vehicles = sorted(library.filter("vehicle.*"), key=lambda bp: bp.id)
        ego = world.try_spawn_actor(library.find("vehicle.tesla.model3"), spawns[scenario.route_spawn_index])
        if ego is None:
            raise RuntimeError("Ego spawn failed")
        actors.append(ego)
        ego.set_autopilot(True, settings.carla_tm_port)
        candidates = [i for i in range(len(spawns)) if i != scenario.route_spawn_index]
        rng.shuffle(candidates)
        count_vehicle = 0
        for index in candidates:
            if count_vehicle >= scenario.vehicles:
                break
            actor = world.try_spawn_actor(rng.choice(vehicles), spawns[index])
            if actor:
                actors.append(actor)
                actor.set_autopilot(True, settings.carla_tm_port)
                count_vehicle += 1
        count_pedestrian = 0
        walker_blueprints = sorted(library.filter("walker.pedestrian.*"), key=lambda bp: bp.id)
        for _ in range(scenario.pedestrians * 3):
            if count_pedestrian >= scenario.pedestrians:
                break
            pulse()
            location = world.get_random_location_from_navigation()
            if location is None:
                continue
            blueprint = rng.choice(walker_blueprints)
            if blueprint.has_attribute("is_invincible"):
                blueprint.set_attribute("is_invincible", "false")
            walker = world.try_spawn_actor(blueprint, carla.Transform(location))
            if walker is None:
                continue
            actors.append(walker)
            controller = world.try_spawn_actor(
                library.find("controller.ai.walker"), carla.Transform(), attach_to=walker
            )
            if controller is None:
                continue
            controllers.append(controller)
            count_pedestrian += 1
        if count_vehicle != scenario.vehicles or count_pedestrian != scenario.pedestrians:
            raise RuntimeError(f"Actor spawn shortfall: vehicles={count_vehicle}, pedestrians={count_pedestrian}")
        world.tick()
        for controller in controllers:
            controller.start()
            destination = world.get_random_location_from_navigation()
            if destination:
                controller.go_to_location(destination)
            controller.set_max_speed(1.4)

        sensor_specs = {
            "lidar": (
                "sensor.lidar.ray_cast",
                {
                    "range": str(scenario.lidar.range_m),
                    "channels": str(scenario.lidar.channels),
                    "points_per_second": str(scenario.lidar.points_per_second),
                    "rotation_frequency": "20",
                    "upper_fov": str(scenario.lidar.upper_fov),
                    "lower_fov": str(scenario.lidar.lower_fov),
                },
            ),
            "semantic": (
                "sensor.lidar.ray_cast_semantic",
                {
                    "range": "100",
                    "channels": "32",
                    "points_per_second": "600000",
                    "rotation_frequency": "20",
                    "upper_fov": "10",
                    "lower_fov": "-30",
                },
            ),
            "camera": ("sensor.camera.rgb", {"image_size_x": "640", "image_size_y": "360", "fov": "90"}),
        }
        for name, (blueprint_id, attrs) in sensor_specs.items():
            bp = library.find(blueprint_id)
            for key, value in attrs.items():
                bp.set_attribute(key, value)
            bp.set_attribute("sensor_tick", "0.0")
            transform = (
                carla.Transform(carla.Location(z=scenario.lidar.mount_z), carla.Rotation(pitch=scenario.lidar.pitch))
                if name == "lidar"
                else (carla.Transform(carla.Location(z=2.0)))
            )
            sensor = world.spawn_actor(bp, transform, attach_to=ego)
            sensors.append(sensor)
            q = queue.Queue(maxsize=8)
            queues[name] = q

            def enqueue(packet, target=q):
                try:
                    target.put_nowait(packet)
                except queue.Full:
                    pass  # Missing/overflowed frames fail the matching_sensor contract.

            sensor.listen(enqueue)

        frames = []
        captured = []
        visible_counts = []
        point_counts, lidar_bytes = [], []
        cadence = round(scenario.capture_interval / scenario.timestep)
        warmup = 20
        for step in range(warmup + scenario.frames * cadence):
            pulse()
            frame_id = world.tick()
            packets = {
                name: matching_sensor(q, frame_id, settings.carla_timeout_seconds, pulse) for name, q in queues.items()
            }
            if step < warmup or (step - warmup) % cadence:
                continue
            snapshot = world.get_snapshot()
            if snapshot.frame != frame_id:
                raise RuntimeError("World snapshot does not match sensor frame")
            ego_transform = ego.get_transform()
            # Ground-origin approximation is explicit: bottom of ego bounding box.
            ground_offset = ego.bounding_box.location.z - ego.bounding_box.extent.z
            ground_location = ego_transform.transform(carla.Location(z=ground_offset))
            reference = carla.Transform(ground_location, ego_transform.rotation)
            ego_matrix = np.asarray(reference.get_matrix(), dtype=float)
            raw = np.frombuffer(packets["lidar"].raw_data, dtype="<f4").reshape(-1, 4)
            if not len(raw):
                raise RuntimeError("LiDAR returned no points; cannot evaluate sensor cost/quality")
            point_counts.append(len(raw))
            lidar_bytes.append(len(packets["lidar"].raw_data))
            points = carla_to_ego(raw[:, :3], np.asarray(packets["lidar"].transform.get_matrix()), ego_matrix)
            x = lidar_features(points, np.clip(raw[:, 3], 0, 1) * 255)
            semantic = np.frombuffer(packets["semantic"].raw_data, dtype=SEMANTIC_DTYPE)
            xyz = np.column_stack((semantic["x"], semantic["y"], semantic["z"]))
            sem_points = carla_to_ego(xyz, np.asarray(packets["semantic"].transform.get_matrix()), ego_matrix)
            labels = np.zeros((200, 200), dtype=np.uint8)
            valid = np.zeros((200, 200), dtype=bool)
            r, c, _ = cells(sem_points)
            valid[r, c] = True
            if not valid.any():
                raise RuntimeError("Reference semantic LiDAR observed no BEV cells")
            static = (sem_points[:, 2] > 0.3) & (sem_points[:, 2] < 3)
            r, c, _ = cells(sem_points[static])
            labels[r, c] = 1
            boxes = []
            visible = set(int(value) for value in semantic["object"])
            for actor in actors[1:]:
                if actor.id not in visible:
                    continue
                world_matrix = np.asarray(actor.get_transform().get_matrix())
                bb = actor.bounding_box
                local_matrix = np.asarray(carla.Transform(bb.location, bb.rotation).get_matrix())
                box_matrix = np.linalg.inv(ego_matrix) @ world_matrix @ local_matrix
                center = box_matrix[:3, 3]
                box = {
                    "id": actor.id,
                    "class": actor.type_id,
                    "x": float(center[0]),
                    "y": float(-center[1]),
                    "z": float(center[2]),
                    "l": float(bb.extent.x * 2),
                    "w": float(bb.extent.y * 2),
                    "h": float(bb.extent.z * 2),
                    "yaw": float(math.atan2(-box_matrix[1, 0], box_matrix[0, 0])),
                }
                labels[footprint(box) & valid] = 2
                boxes.append(box)
            name = f"frame_{len(frames):04d}"
            packets["camera"].save_to_disk(str(root / f"{name}.png"))
            if not (root / f"{name}.png").is_file():
                raise RuntimeError("Camera capture was not saved")
            np.savez_compressed(
                root / f"{name}.npz",
                x=x,
                labels=labels,
                valid=valid,
                points=points.astype(np.float32),
                rotation=ego_matrix[:3, :3],
                translation=ego_matrix[:3, 3],
            )
            (root / f"{name}.json").write_text(
                json.dumps({"boxes": boxes, "ego_matrix": ego_matrix.tolist()}), encoding="utf-8"
            )
            frames.append(
                {
                    "id": name,
                    "x": x,
                    "labels": labels,
                    "valid": valid,
                    "flow": np.zeros((2, 200, 200), dtype=np.float32),
                    "flow_valid": np.zeros((200, 200), bool),
                    "rotation": ego_matrix[:3, :3],
                    "translation": ego_matrix[:3, 3],
                }
            )
            captured.append({"id": name, "frame_id": frame_id, "timestamp": snapshot.timestamp.elapsed_seconds})
            visible_counts.append(len(boxes))
        manifest = {
            "source": "carla",
            "server_version": client.get_server_version(),
            "scenario": scenario.model_dump(),
            "frames": captured,
            "sensor_specs": sensor_specs,
            "realized_vehicles": count_vehicle,
            "realized_pedestrians": count_pedestrian,
            "visible_actor_counts": visible_counts,
            "sensor_cost": {
                "mean_points_per_tick": float(np.mean(point_counts)),
                "mean_lidar_bytes_per_tick": float(np.mean(lidar_bytes)),
                "estimated_lidar_bytes_per_second": float(np.mean(lidar_bytes) / scenario.timestep),
                "configured_points_per_second": scenario.lidar.points_per_second,
                "note": "Sampled raw LiDAR payload only; not power, dollar cost, or network protocol overhead",
            },
            "label_policy": "Only semantic-LiDAR observed cells; static-height proxy + visible actor footprints",
            "limitations": [
                "GT static cells are a height-based proxy, not complete free-space ground truth",
                "Weather affects RGB; current checkpoint consumes LiDAR only",
                "LiDAR intensity scaled 0..1 to 0..255 is an approximation, not calibrated to nuScenes",
                "Ego ground origin approximated using vehicle bounding-box bottom",
                "Actor population is not guaranteed dense in ego ROI; inspect visible_actor_counts",
                "Autopilot spawn-index route; no verified highway route classification",
                "Camera is for review, not an input to these occupancy checkpoints",
                "Reference semantic LiDAR configuration is fixed independently of input LiDAR",
                "Fresh trials reset world/seed; exact reference hash must match before quality-based selection",
            ],
        }
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return frames, manifest
    finally:
        for sensor in sensors:
            try:
                sensor.stop()
            except RuntimeError:
                pass
        for controller in controllers:
            try:
                controller.stop()
            except RuntimeError:
                pass
        for actor in sensors + controllers + actors[::-1]:
            try:
                actor.destroy()
            except RuntimeError:
                pass
        try:
            tm.set_synchronous_mode(False)
        finally:
            world.set_weather(original_weather)
            world.apply_settings(original)
