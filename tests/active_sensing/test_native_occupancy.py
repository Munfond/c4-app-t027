import copy

import numpy as np
import pytest

from src.active_sensing.native_occupancy import BASELINE, NativeOccupancyEnv, quality, sensor_context


def replay_fixture():
    # Synthetic transition tests only, not admission evidence or a measured dataset.
    return {
        "episodes": [
            {
                "id": "synthetic-test-only",
                "split": "train",
                "steps": [
                    {
                        "outcomes": [
                            {
                                "observation": [a / 12, frame / 20, 0.2, 0.1, 0.5, 0.4],
                                "latency_ms": 100 + a + frame,
                                "confusion": [[10, 0, 0], [0, 5, 0], [0, 0, 2]],
                            }
                            for a in range(12)
                        ]
                    }
                    for frame in range(20)
                ],
            }
        ]
    }


def test_current_profile_observation_and_next_frame_action_are_causal():
    env = NativeOccupancyEnv(replay_fixture())
    obs, info = env.reset(seed=27)
    assert obs.shape == (19,)
    assert obs[0] == pytest.approx(BASELINE / 12)
    assert obs[1] == 0
    assert obs[6] == pytest.approx(107 / 500)
    assert info["bootstrap_action"] == BASELINE and obs[7 + BASELINE] == 1
    obs, _, done, _, info = env.step(2)
    assert not done and info["frame"] == 1
    assert obs[0] == pytest.approx(2 / 12) and obs[1] == pytest.approx(1 / 20)
    assert obs[6] == pytest.approx(103 / 500) and obs[9] == 1


def test_counterfactual_current_frame_quality_does_not_leak():
    first, second = replay_fixture(), replay_fixture()
    second["episodes"][0]["steps"][0]["outcomes"][BASELINE]["confusion"] = [[17, 0, 0], [0, 0, 0], [0, 0, 0]]
    second["episodes"][0]["steps"][1]["outcomes"][4]["observation"] = [1.0] * 6
    second["episodes"][0]["steps"][1]["outcomes"][4]["latency_ms"] = 9900
    a, b = NativeOccupancyEnv(first), NativeOccupancyEnv(second)
    assert np.array_equal(a.reset()[0], b.reset()[0])
    left, right = a.step(2), b.step(2)
    assert np.array_equal(left[0], right[0]) and left[1] == right[1]


def test_bootstrap_and_terminal_have_nineteen_decisions_not_twenty():
    env = NativeOccupancyEnv(replay_fixture())
    env.reset()
    for _ in range(19):
        obs, _, done, _, info = env.step(BASELINE)
    assert done and info["frame"] == 19 and not obs.any()
    with pytest.raises(ValueError):
        env.step(BASELINE)
    assert env.reset()[0][7 + BASELINE] == 1


def test_selected_bad_outcome_reduces_reward_without_affecting_prior_observation():
    data = replay_fixture()
    worse = copy.deepcopy(data)
    worse["episodes"][0]["steps"][1]["outcomes"][1].update(latency_ms=900, confusion=[[10, 0, 0], [5, 0, 0], [2, 0, 0]])
    a, b = NativeOccupancyEnv(data), NativeOccupancyEnv(worse)
    assert np.array_equal(a.reset()[0], b.reset()[0])
    assert b.step(1)[1] < a.step(1)[1]


def test_partial_reference_does_not_score_unknown_cells_as_free():
    result = quality([[10, 0, 0], [0, 5, 0], [0, 0, 2]])
    assert result["occupied_iou"] == 1 and result["object_iou"] == 1
    for cm in ([[0] * 3] * 3, [[40001, 0, 0], [0, 0, 0], [0, 0, 0]], [[1.5, 0, 0], [0, 0, 0], [0, 0, 0]]):
        with pytest.raises(ValueError):
            quality(cm)


def test_raw_context_is_bounded_and_has_no_reference_inputs():
    points = np.array([[5.0, 0, 1], [10.0, 2, 0.5]])
    obs = sensor_context(points, np.array([30.0, 255.0]))
    assert len(obs) == 6 and all(0 <= x <= 1 for x in obs)
    with pytest.raises(ValueError):
        sensor_context(np.array([[np.nan, 0, 1]]), np.array([10]))
    with pytest.raises(ValueError):
        sensor_context(np.zeros((0, 3)), np.zeros(0))


@pytest.fixture
def sealed_native_fixture(tmp_path):
    import hashlib
    import json

    from src.active_sensing.native_occupancy import ABI, PROFILES, REWARD
    from src.inference.bev import lidar_features

    def digest(data):
        return hashlib.sha256(data).hexdigest()

    data = {
        "kind": "native_occupancy_measured_replay_v1",
        "status": "measured",
        "observation_abi": ABI,
        "profiles": PROFILES,
        "baseline_action": BASELINE,
        "reward": REWARD,
        "deadline_ms": 500,
        "timing_scope": "cpu_wall_feature_preprocessing_and_inference",
        "deployment_ready": False,
        "adapter": {"gain": 0.1},
        "episodes": [],
    }
    for episode, split in enumerate(("train", "train", "validation", "test")):
        item = {"route": episode, "seed": 100 + episode, "split": split, "steps": []}
        for frame in range(20):
            points = np.array([[5.0, 0, 1], [10.0, 2, 0.5]])
            intensity = np.array([30.0, 255.0], np.float32)
            x = lidar_features(points, intensity)[:4]
            x[3] *= 0.1
            labels, valid = np.zeros((200, 200), np.uint8), np.zeros((200, 200), bool)
            labels[100, 100], valid[100, 100] = 2, True
            prediction = labels.copy()
            rotation, translation = np.eye(3), np.array([float(episode * 1000 + frame), 0, 0])
            name = f"e{episode}-f{frame}.npz"
            np.savez_compressed(
                tmp_path / name,
                x=x,
                points=points,
                intensity=intensity,
                labels=labels,
                valid=valid,
                prediction=prediction,
                rotation=rotation,
                translation=translation,
            )
            outcome = {
                "confusion": [[0, 0, 0], [0, 0, 0], [0, 0, 1]],
                "latency_ms": 10.0,
                "observation": sensor_context(points, intensity),
                "artifact": name,
                "artifact_sha256": digest((tmp_path / name).read_bytes()),
                "input_sha256": digest(x.tobytes()),
            }
            item["steps"].append(
                {
                    "frame": frame,
                    "reference_sha256": digest(
                        labels.tobytes() + valid.tobytes() + rotation.tobytes() + translation.tobytes()
                    ),
                    "outcomes": [copy.deepcopy(outcome) for _ in range(12)],
                }
            )
        data["episodes"].append(item)
    path = tmp_path / "replay.json"

    def write(value):
        path.write_text(json.dumps(value))
        path.with_suffix(".sha256").write_text(digest(path.read_bytes()))
        return path

    return data, write


def test_loader_recomputes_raw_context_masked_confusion_and_inputs(sealed_native_fixture):
    from src.active_sensing.native_occupancy import load_dataset

    data, write = sealed_native_fixture
    assert len(load_dataset(write(data))["episodes"]) == 4
    # Even a re-sealed JSON cannot invent actor observations or full-grid evaluation counts.
    data["episodes"][0]["steps"][0]["outcomes"][0]["observation"] = [0.9] * 6
    with pytest.raises(ValueError, match="sensor-derived"):
        load_dataset(write(data))


def test_loader_rejects_reference_pairing_and_split_leakage(sealed_native_fixture):
    from src.active_sensing.native_occupancy import load_dataset

    data, write = sealed_native_fixture
    data["episodes"][2]["route"] = data["episodes"][0]["route"]
    data["episodes"][2]["seed"] = data["episodes"][0]["seed"]
    with pytest.raises(ValueError, match="Duplicated context"):
        load_dataset(write(data))
    data["episodes"][2]["route"] = 2
    data["episodes"][2]["seed"] = 102
    data["episodes"][0]["steps"][0]["reference_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Unpaired"):
        load_dataset(write(data))


def test_loader_rejects_modified_files_and_incomplete_actions(sealed_native_fixture):
    from src.active_sensing.native_occupancy import load_dataset

    data, write = sealed_native_fixture
    data["episodes"][0]["steps"][0]["outcomes"].pop()
    with pytest.raises(ValueError, match="Incomplete action"):
        load_dataset(write(data))
    data["episodes"][0]["steps"][0]["outcomes"].append(copy.deepcopy(data["episodes"][0]["steps"][0]["outcomes"][0]))
    path = write(data)
    (path.parent / "e0-f0.npz").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Changed perception"):
        load_dataset(path)


def test_aggregate_reference_count_uses_episode_bound_not_frame_bound():
    cm = [[80000, 0, 0], [0, 10000, 0], [0, 0, 5000]]
    assert quality(cm, max_cells=19 * 40000)["occupied_iou"] == 1
    with pytest.raises(ValueError):
        quality(cm)
