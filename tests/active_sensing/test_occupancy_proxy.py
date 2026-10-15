import copy

import numpy as np
import pytest

from src.active_sensing.occupancy_proxy import OccupancyProxyEnv, lidar_features, quality


def measured_contract_fixture():
    # Software-only fixture: never handed to the measured dataset loader.
    return {
        "deadline_ms": 500,
        "episodes": [
            {
                "scene": "fixture",
                "split": "train",
                "steps": [
                    {
                        "observation": [0.5, 0.2, 0.1, 1.0, 0.5, 0.1],
                        "outcomes": [
                            {"confusion": [[39000, 0, 0], [0, 500, 0], [0, 0, 500]], "latency_ms": 100},
                            {"confusion": [[39000, 0, 0], [250, 250, 0], [250, 0, 250]], "latency_ms": 80},
                            {"confusion": [[39000, 0, 0], [500, 0, 0], [500, 0, 0]], "latency_ms": 60},
                        ],
                    }
                    for _ in range(2)
                ],
            }
        ],
    }


def test_counterfactual_quality_and_latency_are_not_in_actor_vector():
    first = measured_contract_fixture()
    second = copy.deepcopy(first)
    second["episodes"][0]["steps"][0]["outcomes"][1]["latency_ms"] = 9000
    second["episodes"][0]["steps"][0]["outcomes"][1]["confusion"] = [[40000, 0, 0], [0, 0, 0], [0, 0, 0]]
    env_a, env_b = OccupancyProxyEnv(first), OccupancyProxyEnv(second)
    a, _ = env_a.reset(seed=27)
    b, _ = env_b.reset(seed=27)
    assert np.array_equal(a, b)
    a, reward_a, _, _, _ = env_a.step(0)
    b, reward_b, _, _, _ = env_b.step(0)
    assert np.array_equal(a, b) and reward_a == reward_b
    assert a.shape == (10,) and a[6] == pytest.approx(0.2)


def test_selected_latency_and_terminal_reset_are_causal():
    env = OccupancyProxyEnv(measured_contract_fixture())
    env.reset(seed=27)
    first, _, done, _, info = env.step(2)
    assert not done and info["retention"] == 0.25
    assert first[6] == pytest.approx(0.12)
    terminal, _, done, _, _ = env.step(0)
    assert done and not terminal.any()
    reset, _ = env.reset(seed=27)
    assert reset[6] == 0 and reset[7] == 1


def test_wrong_label_counts_are_rejected():
    with pytest.raises(ValueError):
        quality([[1, 0, 0], [0, 0, 0], [0, 0, 0]])
    with pytest.raises(ValueError):
        quality([[40001, -1, 0], [0, 0, 0], [0, 0, 0]])


def test_raw_point_reduction_is_deterministic_and_preserves_full_input():
    points = np.array([[5.0, 0, 1], [8.0, 0, 2], [9.0, 2, 0.8], [12.0, 3, 1]])
    intensity = np.array([50.0, 80.0, 100.0, 120.0])
    full = lidar_features(points, intensity)
    half = lidar_features(points, intensity, 0.5, 27)
    assert np.array_equal(half, lidar_features(points, intensity, 0.5, 27))
    assert full.shape == (7, 200, 200) and not full[4:].any()
    assert np.count_nonzero(half[2]) < np.count_nonzero(full[2])
    with pytest.raises(ValueError):
        lidar_features(points, intensity, 0.1)


def test_full_features_match_existing_checkpoint_adapter_even_outside_grid():
    from legacy.streamlit_lab.tools.local.nuscenes_local import NuScenesMini

    points = np.array([[5.0, 0, 1], [8.0, 0, 2], [80.0, 2, 0.8], [0.0, 0, 1], [12.0, 3, 1]])
    intensity = np.array([50.0, 80.0, 100.0, 120.0, 60.0])
    original = object.__new__(NuScenesMini)
    original.keyframe_lidar = lambda token: (points, intensity)
    original.keyframe_radar = lambda token: []
    assert np.array_equal(lidar_features(points, intensity), original.bev_inputs("software-fixture"))
