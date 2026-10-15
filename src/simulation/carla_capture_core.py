"""Synchronous CARLA capture for the LiDAR occupancy checkpoint.

RGB is recorded for review. No fabricated radar RCS/velocity is supplied to a model.
"""

import importlib
import json
import logging
import math
import queue
import random
import time

import numpy as np

from src.inference.bev import carla_to_ego, cells, footprint, lidar_features
from src.simulation.carla_scenarios import LaneChanges, highway_placement


def camera_attributes(scenario):
    camera = getattr(scenario, "camera", None)
    fov = camera.get("fov", 90) if isinstance(camera, dict) else getattr(camera, "fov", 90)
    if fov not in (60, 90, 110):
        raise ValueError("Unsupported camera FOV preset")
    return {"image_size_x": "640", "image_size_y": "360", "fov": str(fov)}


logger = logging.getLogger(__name__)

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


def release_stale_sync(world):
    """A killed client never restores settings; nobody ticks the synchronous world, so load_world stalls."""
    stale = world.get_settings()
    if not stale.synchronous_mode:
        return False
    logger.warning("Releasing synchronous mode left by a previous client")
    stale.synchronous_mode = False
    world.apply_settings(stale)
    return True


def capture(scenario, root, pulse, settings, rig_options=None, online_control=None):
    try:
        carla = importlib.import_module("carla")
    except ImportError as exc:
        raise RuntimeError("CARLA Python client is not installed; use the matching server/client version") from exc
    if online_control is not None and rig_options is not None:
        raise ValueError("Online selector cannot use the detector rig recorder")
    rng = random.Random(scenario.seed)
    client = carla.Client(settings.carla_host, settings.carla_port)
    client.set_timeout(settings.carla_timeout_seconds)
    if client.get_client_version() != client.get_server_version():
        raise RuntimeError("CARLA client/server version mismatch")
    release_stale_sync(client.get_world())
    # Dedicated simulator required: loading a map changes its world.
    # Reset the world for every fresh trial; population/route comparisons need a common start.
    logger.info("Loading map %s", scenario.map)
    world = client.load_world(scenario.map)
    original = world.get_settings()
    original_weather = world.get_weather()
    actors, sensors, controllers = [], [], []
    tm = client.get_trafficmanager(settings.carla_tm_port)
    queues = {}
    root.mkdir(parents=True, exist_ok=True)
    try:
        logger.info("Configuring synchrony, traffic manager and weather")
        synchronous = world.get_settings()
        synchronous.synchronous_mode = True
        synchronous.fixed_delta_seconds = scenario.timestep
        synchronous.no_rendering_mode = False
        world.apply_settings(synchronous)
        tm.set_synchronous_mode(True)
        tm.set_random_device_seed(scenario.seed)
        pedestrian_seed_supported = hasattr(world, "set_pedestrians_seed")
        if pedestrian_seed_supported:
            world.set_pedestrians_seed(scenario.seed)
        elif scenario.pedestrians:
            raise RuntimeError("This CARLA version cannot seed pedestrians; use pedestrians=0 for comparable trials")
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
        logger.info("Spawning ego and requested traffic")
        road_map = world.get_map()
        route_kind = getattr(scenario, "route_kind", "spawn")
        if route_kind == "highway":
            ego_spawn, traffic_spawns, route_evidence = highway_placement(road_map, scenario.route_spawn_index, carla)
        else:
            spawns = road_map.get_spawn_points()
            if scenario.route_spawn_index >= len(spawns):
                raise ValueError("route_spawn_index is outside this map's spawn points")
            ego_spawn = spawns[scenario.route_spawn_index]
            candidates = [i for i in range(len(spawns)) if i != scenario.route_spawn_index]
            rng.shuffle(candidates)
            traffic_spawns = [spawns[i] for i in candidates]
            placement = (
                rig_options["traffic_placement"]
                if rig_options is not None
                else getattr(scenario, "traffic_placement", "random_spawn")
            )
            if placement == "nearest_spawn":
                traffic_spawns.sort(key=lambda spawn: ego_spawn.location.distance(spawn.location))
            route_evidence = {
                "policy": "autopilot spawn-index route",
                "original_spawn_index": scenario.route_spawn_index,
                "traffic_placement": placement,
            }
        if rig_options is not None:
            route_evidence["traffic_placement"] = (
                "verified_highway" if route_kind == "highway" else rig_options["traffic_placement"]
            )
        vehicles = sorted(library.filter("vehicle.*"), key=lambda bp: bp.id)
        if route_kind == "highway":
            vehicles = [
                bp
                for bp in vehicles
                if bp.has_attribute("number_of_wheels") and int(bp.get_attribute("number_of_wheels")) == 4
            ]
        ego = world.try_spawn_actor(library.find("vehicle.tesla.model3"), ego_spawn)
        if ego is None:
            raise RuntimeError("Ego spawn failed")
        actors.append(ego)
        ego.set_autopilot(True, settings.carla_tm_port)
        count_vehicle = 0
        for spawn in traffic_spawns:
            if count_vehicle >= scenario.vehicles:
                break
            actor = world.try_spawn_actor(rng.choice(vehicles), spawn)
            if actor:
                actors.append(actor)
                actor.set_autopilot(True, settings.carla_tm_port)
                count_vehicle += 1
        lane_interval = getattr(scenario, "lane_change_interval_seconds", None)
        vehicle_actors = list(actors)
        if lane_interval:
            if not hasattr(tm, "force_lane_change"):
                raise RuntimeError("This CARLA client does not support forced lane changes")
            for actor in vehicle_actors:
                tm.auto_lane_change(actor, False)
                tm.vehicle_percentage_speed_difference(actor, 0)
        lane_changes = LaneChanges(vehicle_actors, road_map, tm, lane_interval, carla) if lane_interval else None
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
            "camera": ("sensor.camera.rgb", camera_attributes(scenario)),
        }
        rig = None
        if rig_options is not None:
            from src.simulation.carla_rig import RigRecorder

            rig = RigRecorder(root, rig_options, scenario.timestep)
            if rig_options.get("record_environment_inventory"):
                rig.record_environment(world, carla)
            sensor_specs = rig.specs
        if online_control is not None:
            from src.simulation.online_sensor_gate import sensor_bank

            sensor_specs = sensor_bank(sensor_specs)
        logger.info("Attaching %s synchronized sensors", len(sensor_specs))
        for name, (blueprint_id, attrs) in sensor_specs.items():
            bp = library.find(blueprint_id)
            for key, value in attrs.items():
                bp.set_attribute(key, value)
            bp.set_attribute("sensor_tick", "0.0")
            transform = (
                carla.Transform(carla.Location(z=scenario.lidar.mount_z), carla.Rotation(pitch=scenario.lidar.pitch))
                if name == "lidar" or name.startswith("lidar_profile_")
                else (carla.Transform(carla.Location(z=2.0)))
            )
            if rig is not None:
                transform = rig.transform(name, carla)
            sensor = world.spawn_actor(bp, transform, attach_to=ego)
            sensors.append(sensor)
            if online_control is not None:
                online_control.record_sensor(name, sensor.attributes)
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
        logger.info("Capturing %s frames after warmup", scenario.frames)
        spectator = world.get_spectator() if getattr(settings, "carla_follow_ego", False) else None
        for step in range(warmup + scenario.frames * cadence):
            tick_started = time.monotonic()
            pulse()
            frame_id = world.tick()
            if lane_changes is not None:
                lane_changes.tick((step + 1) * scenario.timestep)
            packets = {
                name: matching_sensor(q, frame_id, settings.carla_timeout_seconds, pulse) for name, q in queues.items()
            }
            if spectator is not None:
                view = ego.get_transform()
                spectator.set_transform(
                    carla.Transform(
                        view.transform(carla.Location(x=-8, z=4)),
                        carla.Rotation(pitch=-15, yaw=view.rotation.yaw),
                    )
                )
            if getattr(settings, "carla_realtime_capture", False):
                time.sleep(max(0, scenario.timestep - (time.monotonic() - tick_started)))
            if step < warmup or (step - warmup) % cadence:
                continue
            current_action = None
            if online_control is not None:
                from src.simulation.online_sensor_gate import sensor_name

                current_action = online_control.current_action
                packets["lidar"] = packets[sensor_name(current_action)]
            snapshot = world.get_snapshot()
            logger.info("Processing captured frame %s", frame_id)
            if snapshot.frame != frame_id:
                raise RuntimeError("World snapshot does not match sensor frame")
            ego_transform = ego.get_transform()
            # Ground-origin approximation is explicit: bottom of ego bounding box.
            ground_offset = ego.bounding_box.location.z - ego.bounding_box.extent.z
            ground_location = ego_transform.transform(carla.Location(z=ground_offset))
            reference = carla.Transform(ground_location, ego_transform.rotation)
            ego_matrix = np.asarray(reference.get_matrix(), dtype=float)
            if rig is not None:
                # All live vehicle/walker actors, not only the list created here.
                reference_actors = [
                    a for a in world.get_actors() if a.type_id.startswith(("vehicle.", "walker.pedestrian."))
                ]
                rig.record(
                    packets, snapshot, ego_matrix, reference_actors, ego, actor_scope="world_vehicle_walker_actors"
                )
                continue
            raw = np.frombuffer(packets["lidar"].raw_data, dtype="<f4").reshape(-1, 4)
            if not len(raw):
                raise RuntimeError("LiDAR returned no points; cannot evaluate sensor cost/quality")
            point_counts.append(len(raw))
            lidar_bytes.append(len(packets["lidar"].raw_data))
            points = carla_to_ego(raw[:, :3], np.asarray(packets["lidar"].transform.get_matrix()), ego_matrix)
            intensity = np.clip(raw[:, 3], 0, 1) * 255
            x = lidar_features(points, intensity)
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
            from src.simulation.camera_projection import camera_box

            camera_matrix = np.asarray(packets["camera"].transform.get_matrix(), dtype=float)
            camera_size = (int(packets["camera"].width), int(packets["camera"].height))
            camera_fov = float(sensor_specs["camera"][1]["fov"])
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
                    "camera_box_uv": camera_box(
                        world_matrix @ local_matrix,
                        (bb.extent.x, bb.extent.y, bb.extent.z),
                        camera_matrix,
                        camera_size,
                        camera_fov,
                    ),
                    "camera_projection_status": "geometry_recorded",
                    "world_box_matrix": (world_matrix @ local_matrix).tolist(),
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
                feature_points=points,
                feature_intensity=intensity,
                rotation=ego_matrix[:3, :3],
                translation=ego_matrix[:3, 3],
            )
            (root / f"{name}.json").write_text(
                json.dumps(
                    {
                        **({"selected_lidar_action": current_action} if online_control is not None else {}),
                        "boxes": boxes,
                        "ego_matrix": ego_matrix.tolist(),
                        "camera_matrix": camera_matrix.tolist(),
                        "camera_size": list(camera_size),
                        "camera_fov": camera_fov,
                        "camera_projection_policy": "geometry reference; no pixel visibility/occlusion test",
                        "camera_frame_id": int(packets["camera"].frame),
                        "simulation_frame_id": int(snapshot.frame),
                        "ego_lane": road_map.get_waypoint(ego.get_location()).lane_id,
                        "ego_road": road_map.get_waypoint(ego.get_location()).road_id,
                    }
                ),
                encoding="utf-8",
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
            progress = root / "progress.json"
            temporary = progress.with_suffix(".tmp")
            temporary.write_text(json.dumps({"completed": len(captured), "total": scenario.frames}))
            temporary.replace(progress)
            visible_counts.append(len(boxes))
            if online_control is not None:
                online_control.decide(
                    points, intensity, len(frames) - 1, frame_id, final=len(frames) == scenario.frames
                )

        if rig is not None:
            manifest = rig.finish(
                scenario,
                {
                    "source": "carla",
                    "server_version": client.get_server_version(),
                    "pedestrian_seed_supported": pedestrian_seed_supported,
                    "route_evidence": route_evidence,
                    "ego_actor_id": ego.id,
                    "realized_vehicles": count_vehicle,
                    "realized_pedestrians": count_pedestrian,
                    "lane_change_requests": lane_changes.requests if lane_changes else [],
                    "observed_lane_changes": lane_changes.observed if lane_changes else [],
                },
            )
            return [], manifest
        manifest = {
            "source": "carla",
            "online_sensor_selector": online_control is not None,
            "server_version": client.get_server_version(),
            "pedestrian_seed_supported": pedestrian_seed_supported,
            "follow_ego": bool(getattr(settings, "carla_follow_ego", False)),
            "realtime_capture": bool(getattr(settings, "carla_realtime_capture", False)),
            "route_evidence": route_evidence,
            "ego_actor_id": ego.id,
            "lane_change_requests": lane_changes.requests if lane_changes else [],
            "observed_lane_changes": lane_changes.observed if lane_changes else [],
            "scenario": scenario.model_dump(),
            "frames": captured,
            "sensor_specs": sensor_specs,
            "feature_input_format": "ego_xyz_float64+intensity_0_255_float32",
            "realized_vehicles": count_vehicle,
            "realized_pedestrians": count_pedestrian,
            "visible_actor_counts": visible_counts,
            "sensor_cost": {
                "mean_points_per_tick": float(np.mean(point_counts)),
                "mean_lidar_bytes_per_tick": float(np.mean(lidar_bytes)),
                "estimated_lidar_bytes_per_second": float(np.mean(lidar_bytes) / scenario.timestep),
                "configured_points_per_second": None
                if online_control is not None
                else scenario.lidar.points_per_second,
                "selected_points_per_second_by_frame": [
                    sensor_specs[
                        sensor_name(json.loads((root / f"frame_{i:04d}.json").read_text())["selected_lidar_action"])
                    ][1]["points_per_second"]
                    for i in range(len(captured))
                ]
                if online_control is not None
                else None,
                "note": (
                    "Selected input stream only; all12 sensors stay spawned, not total simulator work or power saving"
                    if online_control is not None
                    else "Sampled raw LiDAR payload only; not power, dollar cost, or network protocol overhead"
                ),
            },
            "label_policy": "Only semantic-LiDAR observed cells; static-height proxy + visible actor footprints",
            "limitations": [
                "GT static cells are a height-based proxy, not complete free-space ground truth",
                "Weather affects RGB; current checkpoint consumes LiDAR only",
                "LiDAR intensity scaled 0..1 to 0..255 is an approximation, not calibrated to nuScenes",
                "Ego ground origin approximated using vehicle bounding-box bottom",
                "Actor population is not guaranteed dense in ego ROI; inspect visible_actor_counts",
                (
                    "Highway placement verified at spawn; autopilot may later leave that road"
                    if getattr(scenario, "route_kind", "spawn") == "highway"
                    else "Autopilot spawn-index route; no verified highway route classification"
                ),
                "Camera is for review, not an input to these occupancy checkpoints",
                "Reference semantic LiDAR configuration is fixed independently of input LiDAR",
                "Fresh trials reset world/seed; exact reference hash must match before quality-based selection",
            ],
        }
        if online_control is not None:
            manifest["online_sensor_bank_actual_attributes"] = online_control.actual_attributes
            manifest["limitations"] += [
                "All12 LiDAR variants remain spawned; gate selects perception input only, no physical sensor power saving",
                "Policy runs in a separate process with selected raw signal only; GT used after capture for evaluation",
                "Online selector experimental; sim-time cadence is not proof of real-time wall-clock performance",
            ]
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return frames, manifest
    finally:
        # Detach vehicles before destruction: old Windows Traffic Manager clients
        # can abort when async processing resumes with destroyed registered actors.
        logger.info("Unregistering autopilot vehicles before cleanup")
        for actor in actors:
            if actor.type_id.startswith("vehicle."):
                try:
                    actor.set_autopilot(False, settings.carla_tm_port)
                except RuntimeError:
                    pass
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
            world.set_weather(original_weather)
            logger.info("Restoring world settings")
            world.apply_settings(original)
        finally:
            tm.set_synchronous_mode(False)
        logger.info("Capture cleanup complete")
