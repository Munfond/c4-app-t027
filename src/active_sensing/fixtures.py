"""Explicitly synthetic software-contract fixture. NEVER a perception benchmark."""
from dataclasses import asdict

from src.active_sensing.core import default_profiles


def synthetic_replay():
    profiles = default_profiles()
    episodes = []
    for split in ("train", "validation", "test"):
        steps = []
        for frame_id in range(4):
            obs = {
                "timestamp_s": frame_id * 0.5, "speed_mps": 8.0,
                "camera_brightness": 0.05 if frame_id >= 2 else 0.6,
                "camera_contrast": 0.5, "lidar_return_ratio": 1.0,
                "radar_targets": 2, "camera_health": "ok",
                "lidar_health": "ok", "radar_health": "ok",
            }
            truth = [{"id": "person-1", "label": "pedestrian", "x": 8.0, "y": 0.0}]
            results = {}
            for profile in profiles:
                # Deliberately fabricated values to exercise branches and parsing only.
                results[profile.id] = {
                    "frame_id": frame_id,
                    "detections": [dict(truth[0], score=0.9)],
                    "gpu_ms": float(profile.model_hz * (len(profile.sensors) + len(profile.tasks))),
                    "end_to_end_ms": 30.0,
                    "actor_feedback": {"nearest_detection_m": 8.0},
                    "task_metrics": {
                        task: {"iou": 0.8, "reference_kind": "ground_truth", "evaluated_elements": 10}
                        for task in profile.tasks if task != "detection"
                    },
                }
            steps.append({
                "frame_id": frame_id, "observation": obs, "ground_truth": truth, "profile_results": results,
            })
        episodes.append({
            "id": f"synthetic-{split}", "capture_id": f"fixture-{split}", "split": split, "steps": steps,
        })
    return {
        "schema_version": 1, "window_s": 0.5,
        "provenance": {
            "kind": "synthetic_contract_fixture",
            "history_mode": "stateless_independent_windows",
            "notice": "ALL predictions, labels and timing are invented for software tests; NOT CARLA evidence.",
        },
        "profiles": [asdict(profile) for profile in profiles],
        "reference_profile": "fused-20hz-seg",
        "constraints": {"required_tasks": ["detection"]},
        "episodes": episodes,
    }
