"""Select checkpoint-compatible streams without pretending to simulate weather."""
from __future__ import annotations

from src.active_sensing.core import Profile, gate_points

CAMERAS = ("front", "front_left", "front_right", "back", "back_left", "back_right")
RADARS = ("front", "front_left", "front_right", "back_left", "back_right")


def gate_capture(capture: dict, profile: Profile, *, seed: int = 0) -> dict:
    """Input must already have calibrated sensor-local streams for one capture frame.

    Returns references to selected images and sampled point tuples. No image decode,
    radar-format conversion, model execution or unstated ego-motion compensation.
    """
    if profile.lidar_sweeps != 1:
        raise NotImplementedError("Multi-sweep aggregation requires a validated ego-motion/history adapter")
    frame_id = capture["frame_id"]
    streams = capture["streams"]
    output = {"frame_id": frame_id, "profile_id": profile.id, "streams": {}}
    for key in ("sensor_abi", "point_frame", "timestamp_s", "detector_adapter_validated"):
        if key in capture:
            output[key] = capture[key]
    if profile.cameras:
        if set(streams.get("camera", {})) != set(CAMERAS):
            raise ValueError("Expected the full six-camera rig")
        for name in CAMERAS:
            record = streams["camera"][name]
            if record["frame_id"] != frame_id:
                raise ValueError("Camera frame is not synchronized")
        output["streams"]["camera"] = streams["camera"]
    if profile.lidar_channels:
        lidar = streams.get("lidar", {}).get(str(profile.lidar_channels))
        if lidar is None or lidar["frame_id"] != frame_id:
            raise ValueError("Missing or unsynchronized LiDAR variant")
        output["streams"]["lidar"] = {
            "frame_id": frame_id, "channels": profile.lidar_channels,
            "points": gate_points(lidar["points"], profile.lidar_keep, seed),
        }
        for key in ("point_frame", "intensity_policy", "timestamp_s"):
            if key in lidar:
                output["streams"]["lidar"][key] = lidar[key]
    if profile.radars:
        if set(streams.get("radar", {})) != set(RADARS):
            raise ValueError("Expected the full five-radar rig")
        for name in RADARS:
            if streams["radar"][name]["frame_id"] != frame_id:
                raise ValueError("Radar frame is not synchronized")
        # Keep original CARLA radial velocity. Never fabricate nuScenes vx_comp/vy_comp.
        output["streams"]["radar"] = streams["radar"]
    return output


class InferenceScheduler:
    """Gate simulator timestamps at the chosen inference rate; no catch-up bursts."""
    def __init__(self):
        self.previous_timestamp = None
        self.previous_profile = None
        self.next_due = None

    def should_process(self, timestamp_s: float, profile: Profile) -> bool:
        from src.active_sensing.core import finite
        timestamp = finite(timestamp_s, "timestamp_s", 0)
        if self.previous_timestamp is not None and timestamp < self.previous_timestamp:
            raise ValueError("Time moved backwards; reset scheduler for a new episode")
        if timestamp == self.previous_timestamp:
            return False
        self.previous_timestamp = timestamp
        if profile.id != self.previous_profile:
            self.previous_profile = profile.id
            self.next_due = timestamp
        if timestamp + 1e-9 < self.next_due:
            return False
        self.next_due = timestamp + 1 / profile.model_hz
        return True
