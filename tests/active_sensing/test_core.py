"""Dependency-free tests: python3 -B -m unittest discover -s tests/active_sensing -v."""
import copy
import unittest
from unittest.mock import patch

from src.active_sensing.core import (
    Box,
    Constraints,
    Observation,
    Profile,
    RulePolicy,
    Shield,
    carla_xyz_to_ego,
    default_profiles,
    evaluate,
    gate_points,
)
from src.active_sensing.fixtures import synthetic_replay
from src.active_sensing.gate import CAMERAS, RADARS, InferenceScheduler, gate_capture
from src.active_sensing.replay import Replay, summarize
from src.active_sensing.sync import FrameBarrier


def observation(**changes):
    values = {
        "timestamp_s": 0, "speed_mps": 8, "camera_health": "ok",
        "lidar_health": "ok", "radar_health": "ok",
    }
    return Observation(**dict(values, **changes))


class ContractsTests(unittest.TestCase):
    def setUp(self):
        self.profiles = default_profiles()
        self.shield = Shield(self.profiles, Constraints())

    def test_twenty_four_unique_profiles(self):
        self.assertEqual(len(self.profiles), 24)
        self.assertEqual(len({p.id for p in self.profiles}), 24)

    def test_partial_camera_rig_rejected(self):
        with self.assertRaisesRegex(ValueError, "Partial rigs"):
            Profile("bad", "official_cl", 10, cameras=3, lidar_channels=32)

    def test_model_sensor_contract(self):
        with self.assertRaisesRegex(ValueError, "requirements"):
            Profile("bad", "crn", 10, cameras=6)

    def test_gt_cannot_cross_actor_boundary(self):
        payload = observation().as_dict()
        payload["weather_gt"] = "fog"
        with self.assertRaisesRegex(ValueError, "Privileged"):
            Observation.from_mapping(payload)

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            observation(camera_contrast=float("nan"))

    def test_unknown_sensor_is_not_assumed_healthy(self):
        obs = Observation(timestamp_s=0, speed_mps=8)
        self.assertIsNone(self.shield.apply("fused-20hz", obs).executed)

    def test_failed_camera_not_reenabled_by_stale_fallback(self):
        obs = observation(camera_health="failed", valid=False)
        decision = self.shield.apply("fused-20hz", obs)
        executed = next(p for p in self.profiles if p.id == decision.executed)
        self.assertEqual(executed.model, "official_lidar")
        self.assertNotIn("camera", executed.sensors)

    def test_no_feasible_profile_is_explicit(self):
        obs = observation(camera_health="failed", lidar_health="failed", radar_health="failed")
        self.assertIsNone(self.shield.apply("fused-20hz", obs).executed)
        self.assertFalse(any(self.shield.mask(obs)))

    def test_highway_range_not_fixed_by_turning_on_radar(self):
        obs = observation(speed_mps=100 / 3.6)
        self.assertIsNone(self.shield.apply("fused-20hz", obs).executed)

    def test_hazard_masks_low_frequency(self):
        mask = self.shield.mask(observation(min_ttc_s=1))
        self.assertTrue(any(mask))
        self.assertTrue(all(p.model_hz == 20 for p, valid in zip(self.profiles, mask) if valid))

    def test_segmentation_tasks_are_not_replaced_by_detection(self):
        shield = Shield(self.profiles, Constraints(required_tasks=("detection", "camera_seg", "lidar_seg")))
        candidates = shield.eligible(observation())
        self.assertTrue(candidates)
        self.assertTrue(all("camera_seg" in p.tasks and "lidar_seg" in p.tasks for p in candidates))

    def test_rule_uses_observed_quality(self):
        choice = RulePolicy(self.shield).select(observation(camera_brightness=0.02))
        self.assertTrue(choice.startswith("official_lidar"))

    def test_sampling_reproducible_and_no_duplicate(self):
        points = [(i, 0, 0, 1) for i in range(100)]
        sample = gate_points(points, 0.25, 27)
        self.assertEqual(sample, gate_points(points, 0.25, 27))
        self.assertEqual(len(set(sample)), 25)

    def test_gate_validates_selected_frame(self):
        profile = next(p for p in self.profiles if p.id == "fused-10hz")
        streams = {
            "camera": {name: {"frame_id": 7, "image": name} for name in CAMERAS},
            "radar": {name: {"frame_id": 7, "points": []} for name in RADARS},
            "lidar": {"32": {"frame_id": 7, "points": [(1, 2, 3, 1)]}},
        }
        gated = gate_capture({"frame_id": 7, "streams": streams}, profile)
        self.assertEqual(set(gated["streams"]), {"camera", "lidar", "radar"})
        streams["camera"]["front"]["frame_id"] = 6
        with self.assertRaisesRegex(ValueError, "synchronized"):
            gate_capture({"frame_id": 7, "streams": streams}, profile)

    def test_inference_scheduler_rates(self):
        for hz in (5, 10, 20):
            scheduler = InferenceScheduler()
            profile = next(p for p in self.profiles if p.id == f"official_lidar-{hz}hz")
            count = sum(scheduler.should_process(tick * 0.05, profile) for tick in range(20))
            self.assertEqual(count, hz)

    def test_scheduler_switch_and_duplicate_timestamps(self):
        scheduler = InferenceScheduler()
        slow = next(p for p in self.profiles if p.id == "official_lidar-5hz")
        fast = next(p for p in self.profiles if p.id == "official_lidar-20hz")
        self.assertTrue(scheduler.should_process(0, slow))
        self.assertFalse(scheduler.should_process(0, fast))
        self.assertTrue(scheduler.should_process(0.05, fast))
        with self.assertRaises(ValueError):
            scheduler.should_process(0, fast)

    def test_multisweep_gate_cannot_claim_compensation(self):
        profile = Profile("history", "official_lidar", 10, lidar_channels=32, lidar_sweeps=3)
        with self.assertRaises(NotImplementedError):
            gate_capture({"frame_id": 7, "streams": {}}, profile)

    def test_coordinate_handedness(self):
        self.assertEqual(carla_xyz_to_ego((1, 2, 3)), (1, -2, 3))


class MetricTests(unittest.TestCase):
    def metric(self, gt, pred, **kwargs):
        values = {
            "ground_truth": gt, "predictions": pred, "observation": observation(),
            "constraints": Constraints(), "gpu_ms": 10, "reference_gpu_ms": 20,
            "end_to_end_ms": 30, "switched": False, "intervened": False,
        }
        return evaluate(**dict(values, **kwargs))

    def test_one_prediction_cannot_match_two_targets(self):
        truth = [Box("a", "pedestrian", 8, 0), Box("b", "pedestrian", 8, 0.5)]
        result = self.metric(truth, [Box("p", "pedestrian", 8, 0)])
        self.assertEqual(result["matched_targets"], 1)
        self.assertEqual(result["constraint_cost"], 1)

    def test_duplicate_predictions_penalized(self):
        truth = [Box("a", "pedestrian", 8, 0)]
        result = self.metric(truth, [Box("p1", "pedestrian", 8, 0), Box("p2", "pedestrian", 8, 0)])
        self.assertEqual(result["false_positives"], 1)

    def test_late_output_not_counted_as_reliable(self):
        truth = [Box("a", "pedestrian", 8, 0)]
        result = self.metric(truth, truth, end_to_end_ms=151)
        self.assertEqual(result["effective_recall"], 0)
        self.assertEqual(result["constraint_cost"], 1)

    def test_work_above_reference_not_clamped(self):
        result = self.metric([], [], gpu_ms=30)
        self.assertEqual(result["gpu_ratio"], 1.5)
        self.assertIsNone(result["weighted_recall"])

    def test_stationary_vehicle_still_evaluates_nearby_target(self):
        result = self.metric(
            [Box("a", "pedestrian", 2, 0)], [], observation=observation(speed_mps=0),
        )
        self.assertEqual(result["constraint_cost"], 1)

    def test_wrong_class_does_not_match(self):
        result = self.metric([Box("a", "pedestrian", 8, 0)], [Box("p", "car", 8, 0)])
        self.assertEqual(result["matched_targets"], 0)


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.payload = synthetic_replay()

    def replay(self):
        return Replay(copy.deepcopy(self.payload), allow_synthetic=True)

    def test_synthetic_data_refused_by_default(self):
        with self.assertRaisesRegex(ValueError, "Synthetic"):
            Replay(self.payload)

    def test_current_prediction_not_visible_before_action(self):
        replay = self.replay()
        state = replay.reset("synthetic-test")
        self.assertIsNone(state["observation"]["nearest_detection_m"])
        self.assertNotIn("ground_truth", state)

    def test_only_chosen_previous_result_enters_actor_state(self):
        for result in self.payload["episodes"][2]["steps"][0]["profile_results"].values():
            result["actor_feedback"] = {"nearest_detection_m": 50}
        self.payload["episodes"][2]["steps"][0]["profile_results"]["official_lidar-10hz"]["actor_feedback"] = {
            "nearest_detection_m": 8,
        }
        replay = self.replay()
        replay.reset("synthetic-test")
        state, _, done, _ = replay.advance("official_lidar-10hz")
        self.assertFalse(done)
        self.assertEqual(state["observation"]["nearest_detection_m"], 8)

    def test_late_feedback_is_not_reused(self):
        self.payload["episodes"][2]["steps"][0]["profile_results"]["official_lidar-10hz"]["end_to_end_ms"] = 151
        replay = self.replay()
        replay.reset("synthetic-test")
        state, _, _, _ = replay.advance("official_lidar-10hz")
        self.assertIsNone(state["observation"]["nearest_detection_m"])

    def test_gt_cannot_change_same_step_actor_state(self):
        before = self.replay().reset("synthetic-test")
        self.payload["episodes"][2]["steps"][0]["ground_truth"] = []
        after = self.replay().reset("synthetic-test")
        self.assertEqual(before, after)

    def test_wrong_frame_result_rejected(self):
        self.payload["episodes"][0]["steps"][0]["profile_results"]["crn-10hz"]["frame_id"] = 99
        with self.assertRaisesRegex(ValueError, "different frame"):
            self.replay()

    def test_train_test_frame_leakage_rejected(self):
        self.payload["episodes"][2]["capture_id"] = self.payload["episodes"][0]["capture_id"]
        with self.assertRaisesRegex(ValueError, "split leakage"):
            self.replay()

    def test_adjacent_train_test_windows_from_one_capture_rejected(self):
        self.payload["episodes"][2]["capture_id"] = self.payload["episodes"][0]["capture_id"]
        for step in self.payload["episodes"][2]["steps"]:
            step["frame_id"] += 100
            for result in step["profile_results"].values():
                result["frame_id"] += 100
        with self.assertRaisesRegex(ValueError, "split leakage"):
            self.replay()

    def test_stateful_lookup_rejected(self):
        self.payload["provenance"]["history_mode"] = "tracking"
        with self.assertRaisesRegex(ValueError, "sequential replay"):
            self.replay()

    def test_missing_profile_result_rejected(self):
        del self.payload["episodes"][0]["steps"][0]["profile_results"]["crn-10hz"]
        with self.assertRaisesRegex(ValueError, "every declared profile"):
            self.replay()

    def test_missing_segmentation_metric_rejected(self):
        self.payload["episodes"][0]["steps"][0]["profile_results"]["official_cl-10hz-seg"]["task_metrics"] = {}
        with self.assertRaisesRegex(ValueError, "separately measured"):
            self.replay()

    def test_low_segmentation_metric_violates_constraint(self):
        self.payload["constraints"]["required_tasks"] = ["detection", "camera_seg", "lidar_seg"]
        result = self.payload["episodes"][2]["steps"][0]["profile_results"]["official_cl-10hz-seg"]
        result["task_metrics"]["camera_seg"]["iou"] = 0.1
        replay = self.replay()
        replay.reset("synthetic-test")
        _, _, _, info = replay.advance("official_cl-10hz-seg")
        self.assertTrue(info["metrics"]["segmentation_constraint_failed"])
        self.assertEqual(info["metrics"]["constraint_cost"], 1)

    def test_three_baselines_generate_complete_timeline(self):
        replay = self.replay()
        for policy in ("full", "minimum", "rule"):
            logs = replay.run("synthetic-test", policy)
            self.assertEqual(len(logs), 4)
            self.assertTrue(summarize(logs)["claim_complete_evaluation"])

    def test_infeasible_steps_are_not_hidden(self):
        obs = self.payload["episodes"][2]["steps"][1]["observation"]
        obs.update(camera_health="failed", lidar_health="failed", radar_health="failed")
        logs = self.replay().run("synthetic-test", "rule")
        summary = summarize(logs)
        self.assertEqual(summary["infeasible_steps"], 1)
        self.assertFalse(summary["claim_complete_evaluation"])

    def test_lagrange_penalty_changes_reward_not_observation(self):
        replay = self.replay()
        replay.reset("synthetic-test")
        self.payload["episodes"][2]["steps"][0]["profile_results"]["official_lidar-10hz"]["detections"] = []
        replay = self.replay()
        replay.reset("synthetic-test")
        _, reward, _, info = replay.advance("official_lidar-10hz", multiplier=2)
        self.assertEqual(reward, info["metrics"]["base_reward"] - 2)


class SyncTests(unittest.TestCase):
    def test_barrier_rejects_stale_and_duplicate_frames(self):
        barrier = FrameBarrier(7, {"camera", "lidar"})
        self.assertFalse(barrier.push("camera", 6, object()))
        with self.assertRaises(LookupError):
            barrier.collect()
        barrier.push("camera", 7, "image")
        with self.assertRaises(ValueError):
            barrier.push("camera", 7, "duplicate")
        barrier.push("lidar", 7, "points")
        self.assertEqual(barrier.collect(), {"camera": "image", "lidar": "points"})

    def test_timeout_is_explicit(self):
        with patch("src.active_sensing.sync.time.monotonic", return_value=0):
            barrier = FrameBarrier(7, {"camera"}, 1)
        with patch("src.active_sensing.sync.time.monotonic", return_value=2):
            with self.assertRaises(TimeoutError):
                barrier.collect()


if __name__ == "__main__":
    unittest.main()
