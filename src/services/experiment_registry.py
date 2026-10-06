"""Allowlisted checkpoint registry, independently verified against the repository manifest."""

import hashlib

from src.config import get_settings

MODELS = {
    "occupancy_lidar": ("occupancy/variants/our_occupancy_lidar.pth", "occupancy", [0, 1, 2, 3], 1, True),
    "occupancy_radar": ("occupancy/variants/our_occupancy_radar.pth", "occupancy", [4, 5, 6], 1, True),
    "occupancy_lidar_radar": ("occupancy/our_occupancy.pth", "occupancy", list(range(7)), 1, True),
    "flow_t1": ("temporal_flow/variants/our_flow_T1.pth", "flow", list(range(7)), 1, True),
    "flow_t2": ("temporal_flow/variants/our_flow_T2.pth", "flow", list(range(7)), 2, True),
    "flow_t4": ("temporal_flow/our_flow.pth", "flow", list(range(7)), 4, True),
    "flow_t4_nowarp": ("temporal_flow/variants/our_flow_T4_nowarp.pth", "flow", list(range(7)), 4, False),
}


def checkpoint_path(model_id):
    return get_settings().lab_data_root / "models" / MODELS[model_id][0]


def verified_hash(model_id):
    path = checkpoint_path(model_id)
    manifest = get_settings().lab_data_root / "models/CHECKPOINTS.sha256"
    expected = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, name = line.split(maxsplit=1)
            expected[name.lstrip("*").removeprefix("./")] = digest
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != expected.get(MODELS[model_id][0]):
        raise ValueError(f"Checkpoint checksum mismatch: {model_id}")
    return actual


def registry():
    return [
        {
            "id": name,
            "task": task,
            "channels": channels,
            "history": history,
            "available": checkpoint_path(name).is_file(),
            "sources": ["nuscenes", "dataset_replay", "carla"] if name == "occupancy_lidar" else
                (["nuscenes", "dataset_replay"] if task == "occupancy" else ["nuscenes"]),
            "limitations": ["BEV 2D; not 3D detection", "Training static labels are pseudo-GT"]
            + (["Experimental flow; known weak quality"] if task == "flow" else [])
            + (["CARLA radar RCS/compensated velocity adapter unavailable"] if name != "occupancy_lidar" else []),
        }
        for name, (_, task, channels, history, _) in MODELS.items()
    ]


def validate_spec(spec):
    if spec.source == "dataset_replay":
        from src.models.replay import OCCUPANCY_MODELS
        from src.services.dataset_replay import validate_trial

        if not set(spec.model_ids) <= set(OCCUPANCY_MODELS):
            raise ValueError("Dataset replay supports occupancy models only")
        validate_trial(spec.replay)
    if spec.source == "nuscenes":
        from src.models.experiments import LidarSpec

        if spec.scenario.lidar != LidarSpec():
            raise ValueError("Sensor configuration changes require CARLA, not stored nuScenes")
    for model_id in spec.model_ids:
        if model_id not in MODELS:
            raise ValueError(f"Unknown checkpoint: {model_id}")
        if not checkpoint_path(model_id).is_file():
            raise ValueError(f"Checkpoint missing: {model_id}")
        if spec.source == "carla" and model_id != "occupancy_lidar":
            raise ValueError("CARLA currently supports occupancy_lidar only; radar feature adapter is not calibrated")


def camera_fingerprint():
    settings = get_settings()
    path = settings.replay_camera_onnx
    if not path:
        return None
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"sha256": digest, "input_size": settings.replay_camera_input_size,
            "score_threshold": settings.replay_camera_score_threshold}
