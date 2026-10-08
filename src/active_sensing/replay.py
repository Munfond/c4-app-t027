"""Causal replay of measured, stateless per-profile perception windows."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.active_sensing.core import (
    Box,
    Constraints,
    Decision,
    Observation,
    Profile,
    RulePolicy,
    Shield,
    evaluate,
    finite,
)


class Replay:
    def __init__(self, payload: dict[str, Any], *, allow_synthetic: bool = False):
        if payload.get("schema_version") != 1:
            raise ValueError("Replay schema_version must be 1")
        self.provenance = payload.get("provenance", {})
        kind = self.provenance.get("kind")
        if kind not in ("measured_perception", "synthetic_contract_fixture"):
            raise ValueError("Unknown provenance kind")
        if kind == "synthetic_contract_fixture" and not allow_synthetic:
            raise ValueError("Synthetic fixtures are not experimental evidence; pass allow_synthetic explicitly")
        if self.provenance.get("history_mode") != "stateless_independent_windows":
            raise ValueError("Tracking/flow/profile-dependent history needs sequential replay, not this lookup")
        if kind == "measured_perception":
            required = ("capture_id", "model_manifest_sha256", "hardware", "timing_scope", "monitoring_cost_included")
            if any(not self.provenance.get(key) for key in required):
                raise ValueError("Measured replay needs capture/model/hardware/timing provenance and monitoring cost")
            if self.provenance["timing_scope"] != "total_gpu_work_per_window":
                raise ValueError("Timing must include ALL inference in each window, not ms per call")
            if self.provenance['monitoring_cost_included'] is not True:
                raise ValueError('Monitoring cost must be explicitly measured, not a truthy string')
            # A successful detector invocation or partial positive geometry audit
            # must never become RL evidence merely by renaming its provenance.
            for flag in ('validated_detection_quality', 'usable_for_rl_reward', 'validated_profile_catalog'):
                if self.provenance.get(flag) is not True:
                    raise ValueError(f'Measured replay admission requires {flag}=true')
            protocol_hash = self.provenance.get('evaluation_protocol_sha256', '')
            if not isinstance(protocol_hash, str) or len(protocol_hash) != 64 or any(c not in '0123456789abcdef' for c in protocol_hash):
                raise ValueError('Measured replay requires a pinned evaluation protocol SHA256')
        self.window_s = finite(payload["window_s"], "window_s", 0)
        if self.window_s <= 0:
            raise ValueError("window_s must be positive")
        self.profiles = tuple(Profile(**dict(p, tasks=tuple(p.get("tasks", ["detection"])))) for p in payload["profiles"])
        self.by_id = {p.id: p for p in self.profiles}
        self.constraints = Constraints(**dict(
            payload.get("constraints", {}),
            required_tasks=tuple(payload.get("constraints", {}).get("required_tasks", ["detection"])),
        ))
        self.shield = Shield(self.profiles, self.constraints)
        self.rule = RulePolicy(self.shield)
        self.reference = payload["reference_profile"]
        if self.reference not in self.by_id:
            raise ValueError("Unknown reference profile")
        self.episodes = payload["episodes"]
        if not self.episodes or len({e["id"] for e in self.episodes}) != len(self.episodes):
            raise ValueError("Episodes must be nonempty and have unique ids")
        seen_frames = set()
        capture_splits = {}
        for episode in self.episodes:
            if episode["split"] not in ("train", "validation", "test") or not episode["steps"]:
                raise ValueError("Episode requires a valid split and steps")
            capture_id = episode["capture_id"]
            if capture_id in capture_splits and capture_splits[capture_id] != episode["split"]:
                raise ValueError("Capture split leakage: adjacent windows must remain in one split")
            capture_splits[capture_id] = episode["split"]
            previous = None
            for step in episode["steps"]:
                obs = Observation.from_mapping(step["observation"])
                if previous is not None and abs(obs.timestamp_s - previous - self.window_s) > 1e-6:
                    raise ValueError("Observation windows must be ordered with exact window_s spacing")
                previous = obs.timestamp_s
                frame_key = (episode["capture_id"], step["frame_id"])
                if frame_key in seen_frames:
                    raise ValueError("A captured frame occurs more than once; split leakage is forbidden")
                seen_frames.add(frame_key)
                if set(step["profile_results"]) != set(self.by_id):
                    raise ValueError("Every frame requires measured results for every declared profile")
                for box in step["ground_truth"]:
                    Box(**box)
                for profile_id, result in step["profile_results"].items():
                    if kind == 'measured_perception' and (
                            result.get('validated_detection_quality') is not True
                            or result.get('usable_for_rl_reward') is not True):
                        raise ValueError('Partial/unvalidated profile results cannot be used as RL reward')
                    if result["frame_id"] != step["frame_id"]:
                        raise ValueError("Perception result belongs to a different frame")
                    for key in ("gpu_ms", "end_to_end_ms"):
                        finite(result[key], key, 0)
                    if "detection" not in self.by_id[profile_id].tasks:
                        raise ValueError("Detection results need a detection profile")
                    for box in result["detections"]:
                        Box(**box)
                    required_seg = set(self.by_id[profile_id].tasks) - {"detection"}
                    task_metrics = result.get("task_metrics", {})
                    if not required_seg <= set(task_metrics):
                        raise ValueError("Segmentation profiles need separately measured task metrics")
                    for task in required_seg:
                        metric = task_metrics[task]
                        if metric.get("reference_kind") != "ground_truth":
                            raise ValueError("Segmentation constraints need true reference labels, not pseudo-GT")
                        if not 0 <= finite(metric["iou"], "segmentation IoU") <= 1:
                            raise ValueError("Invalid segmentation IoU")
                        if metric.get("evaluated_elements", 0) <= 0:
                            raise ValueError("Segmentation metric needs evaluated pixel/point count")
                    feedback = result.get("actor_feedback", {})
                    if not set(feedback) <= {"nearest_detection_m", "min_ttc_s", "new_near_target"}:
                        raise ValueError("Actor feedback must be observable, not ground truth")
                    Observation.from_mapping(dict(step["observation"], **feedback))
                if step["profile_results"][self.reference]["gpu_ms"] <= 0:
                    raise ValueError("Reference GPU work must be positive")
        self.index = 0
        self.current_profile = self.reference
        self.last_feedback: dict[str, Any] = {}
        self.switches = 0

    @classmethod
    def load(cls, path: str | Path, *, allow_synthetic: bool = False) -> Replay:
        return cls(json.loads(Path(path).read_text()), allow_synthetic=allow_synthetic)

    def reset(self, episode_id: str) -> dict[str, Any]:
        self.episode = next(e for e in self.episodes if e["id"] == episode_id)
        self.index = 0
        self.current_profile = self.reference
        self.last_feedback = {}
        self.switches = 0
        return self.actor_state()

    def observation(self) -> Observation:
        monitor = dict(self.episode["steps"][self.index]["observation"])
        # Predictions in the CURRENT window cannot affect its own action.
        for key in ("nearest_detection_m", "min_ttc_s", "new_near_target"):
            monitor.pop(key, None)
        return Observation.from_mapping(dict(monitor, **self.last_feedback))

    def actor_state(self) -> dict[str, Any]:
        return {
            "observation": self.observation().as_dict(),
            "current_profile": self.current_profile,
            "action_mask": self.shield.mask(self.observation()),
        }

    def advance(self, requested: str, multiplier: float = 0.0) -> tuple[dict[str, Any] | None, float | None, bool, dict[str, Any]]:
        finite(multiplier, "multiplier", 0)
        step = self.episode["steps"][self.index]
        observation = self.observation()
        decision: Decision = self.shield.apply(requested, observation)
        log = {
            "episode_id": self.episode["id"], "frame_id": step["frame_id"],
            "timestamp_s": observation.timestamp_s, "decision": {
                "requested": decision.requested, "executed": decision.executed,
                "intervened": decision.intervened, "reasons": list(decision.reasons),
            },
            "provenance_kind": self.provenance["kind"],
        }
        reward = None
        if decision.executed is None:
            log["status"] = "infeasible"
            self.last_feedback = {}
        else:
            result = step["profile_results"][decision.executed]
            switched = decision.executed != self.current_profile
            self.switches += int(switched)
            metrics = evaluate(
                [Box(**b) for b in step["ground_truth"]],
                [Box(**b) for b in result["detections"]],
                observation, self.constraints, result["gpu_ms"],
                step["profile_results"][self.reference]["gpu_ms"],
                result["end_to_end_ms"], switched, decision.intervened,
            )
            required_seg = set(self.constraints.required_tasks) - {"detection"}
            seg_failed = any(
                result["task_metrics"][task]["iou"] < self.constraints.min_segmentation_iou
                for task in required_seg
            )
            metrics["segmentation_constraint_failed"] = seg_failed
            metrics["constraint_cost"] = max(metrics["constraint_cost"], float(seg_failed))
            # All GT-derived values remain in info; never merge them into actor_state.
            reward = metrics["base_reward"] - multiplier * metrics["constraint_cost"]
            log.update(status="evaluated", metrics=metrics, lagrange_multiplier=multiplier)
            log["task_metrics"] = result.get("task_metrics", {})
            self.last_feedback = result.get("actor_feedback", {}) if not metrics["late"] else {}
            self.current_profile = decision.executed
        self.index += 1
        done = self.index == len(self.episode["steps"])
        return (None if done else self.actor_state()), reward, done, log

    def run(self, episode_id: str, policy: str) -> list[dict[str, Any]]:
        if policy not in ("full", "minimum", "rule"):
            raise ValueError("Unknown baseline")
        self.reset(episode_id)
        logs = []
        done = False
        while not done:
            obs = self.observation()
            candidates = self.shield.eligible(obs)
            if policy == "full":
                requested = self.reference
            elif policy == "minimum":
                requested = min(
                    candidates or list(self.profiles),
                    key=lambda p: (p.model_hz, len(p.tasks), len(p.sensors), p.id),
                ).id
            else:
                requested = self.rule.select(obs)
            _, _, done, info = self.advance(requested)
            logs.append(info)
        return logs


def summarize(logs: list[dict[str, Any]]) -> dict[str, Any]:
    evaluated = [row["metrics"] for row in logs if row["status"] == "evaluated"]
    total = len(logs)
    return {
        "steps": total, "evaluated_steps": len(evaluated),
        "infeasible_steps": total - len(evaluated),
        "constraint_cost_sum": sum(m["constraint_cost"] for m in evaluated),
        "constraint_rate_evaluated": (
            sum(m["constraint_cost"] for m in evaluated) / len(evaluated) if evaluated else None
        ),
        "gpu_ms": sum(m["gpu_ms"] for m in evaluated),
        "target_steps": sum(m["required_targets"] > 0 for m in evaluated),
        "target_conditional_constraint_rate": (
            sum(m["constraint_cost"] for m in evaluated if m["required_targets"] > 0)
            / sum(m["required_targets"] > 0 for m in evaluated)
            if any(m["required_targets"] > 0 for m in evaluated) else None
        ),
        "shield_interventions": sum(row["decision"]["intervened"] for row in logs),
        "claim_complete_evaluation": bool(total) and total == len(evaluated),
    }
