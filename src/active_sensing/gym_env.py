"""Optional Gymnasium adapter. Install requirements-active-sensing.txt separately."""
from __future__ import annotations

import gymnasium as gym
import numpy as np

from src.active_sensing.replay import Replay


class ReplayEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, replay: Replay, split: str = "train"):
        self.replay = replay
        self.episodes = [e for e in replay.episodes if e["split"] == split]
        if not self.episodes:
            raise ValueError(f"No {split} episodes")
        self.action_space = gym.spaces.Discrete(len(replay.profiles))
        size = 15 + len(replay.profiles)
        self.observation_space = gym.spaces.Box(-1, 1, shape=(size,), dtype=np.float32)
        self.multiplier = 1.0
        self.previous_gpu_ratio = 0.0

    def _vector(self):
        obs = self.replay.observation()
        health = {"ok": 1, "degraded": 0, "failed": -1, "unknown": -1}
        values = [
            min(obs.speed_mps / 40, 1), obs.camera_brightness, obs.camera_contrast,
            obs.lidar_return_ratio, min(obs.radar_targets / 100, 1),
            health[obs.camera_health], health[obs.lidar_health], health[obs.radar_health],
            min(obs.nearest_detection_m / 100, 1) if obs.nearest_detection_m is not None else -1,
            min(obs.min_ttc_s / 10, 1) if obs.min_ttc_s is not None else -1,
            float(obs.new_near_target), min(obs.age_ms / 1000, 1), float(obs.valid),
            min(self.previous_gpu_ratio, 1), min(self.replay.switches / 100, 1),
        ]
        values += [float(p.id == self.replay.current_profile) for p in self.replay.profiles]
        return np.asarray(values, dtype=np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        episode = self.episodes[int(self.np_random.integers(len(self.episodes)))]
        self.replay.reset(episode["id"])
        self.previous_gpu_ratio = 0.0
        return self._vector(), {"episode_id": episode["id"]}

    def action_masks(self):
        mask = self.replay.shield.mask(self.replay.observation())
        if not any(mask):
            raise RuntimeError("No feasible profile; do not train on an all-invalid action distribution")
        return np.asarray(mask, dtype=bool)

    def step(self, action):
        profile_id = self.replay.profiles[int(action)].id
        _, reward, done, info = self.replay.advance(profile_id, self.multiplier)
        if reward is None:
            raise RuntimeError("Infeasible configuration: cannot fabricate reward or GPU measurement")
        self.previous_gpu_ratio = info["metrics"]["gpu_ratio"]
        # Terminal observation is not a future row and cannot leak GT.
        vector = np.zeros(self.observation_space.shape, dtype=np.float32) if done else self._vector()
        return vector, float(reward), done, False, info

    def set_multiplier(self, multiplier: float):
        self.multiplier = max(0.0, float(multiplier))
