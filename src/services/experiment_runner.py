"""Explicit worker execution; no heavy inference or simulator imports in the API."""

import hashlib
import json
import logging
import platform
import uuid

import numpy as np

from src.config import get_settings
from src.evaluation.bev import BevEvaluator, recommend
from src.models.experiments import ExperimentSpec
from src.services import experiment_store as store
from src.services.experiment_registry import camera_fingerprint, verified_hash

logger = logging.getLogger(__name__)


def nuscenes_frames(spec, pulse):
    from legacy.streamlit_lab.tools.local.nuscenes_local import NuScenesMini

    ds = NuScenesMini(str(get_settings().nusc_root))
    tokens = [
        token for token in ds.by_split["val"] if ds.scene[ds.sample[token]["scene_token"]]["name"] == spec.scene_id
    ]
    if not tokens:
        raise ValueError("Scene is not in nuScenes mini-val")
    frames = []
    for token in tokens[: spec.scenario.frames]:
        pulse()
        rotation, translation = ds.pose(token)
        flow, flow_valid = ds.gt_flow(token)
        frames.append(
            {
                "id": token,
                "x": ds.bev_inputs(token),
                "labels": ds.labels(token),
                "valid": np.ones((200, 200), bool),
                "flow": flow,
                "flow_valid": flow_valid,
                "rotation": rotation,
                "translation": translation,
            }
        )
    return frames, {
        "source": "nuscenes",
        "scene_id": spec.scene_id,
        "frames": [{"id": frame["id"]} for frame in frames],
        "limitations": [
            "Static labels use LiDAR-derived pseudo-GT; class free includes unobserved cells",
            "Original nuScenes data only; CARLA weather/actor settings do not modify this source",
            "History at scene start repeats earliest frame, matching project temporal adapter",
        ],
    }


def replay_capture(spec):
    root = store.root() / spec.capture_id / "capture"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["scenario"] != spec.scenario.model_dump():
        from src.models.experiments import ScenarioSpec

        if ScenarioSpec.model_validate(manifest["scenario"]) != spec.scenario:
            raise ValueError("Replay scenario must match original capture exactly")
    frames = []
    for item in manifest["frames"]:
        # Only worker-created frame names, not paths obtained from arbitrary JSON.
        name = f"frame_{len(frames):04d}"
        if item["id"] != name:
            raise ValueError("Invalid capture frame catalog")
        with np.load(root / f"{name}.npz", allow_pickle=False) as data:
            frames.append(
                {
                    "id": name,
                    "x": data["x"],
                    "labels": data["labels"],
                    "valid": data["valid"],
                    "flow": np.zeros((2, 200, 200), np.float32),
                    "flow_valid": np.zeros((200, 200), bool),
                    "rotation": data["rotation"] if "rotation" in data else np.eye(3),
                    "translation": data["translation"] if "translation" in data else np.zeros(3),
                }
            )
    manifest["reused_from"] = spec.capture_id
    return frames, manifest


def run_once():
    owner = uuid.uuid4().hex
    job = store.claim(owner)
    if job is None:
        return None
    ident = job["id"]
    root = store.root() / ident
    root.mkdir(parents=True, exist_ok=True)

    def pulse(stage="capture"):
        store.touch(ident, owner, stage)

    try:
        spec = ExperimentSpec.model_validate(job["spec"]["request"])
        for name, expected in job["spec"]["checkpoints"].items():
            if verified_hash(name) != expected:
                raise ValueError("Checkpoint changed after enqueue")
        if spec.source == "dataset_replay":
            from src.services.dataset_replay import frames as replay_frames

            if camera_fingerprint() != job["spec"].get("camera_detector"):
                raise ValueError("Camera detector/settings changed after enqueue")
            frames, manifest = replay_frames(spec.replay, root / "capture", pulse)
        elif spec.source == "nuscenes":
            frames, manifest = nuscenes_frames(spec, pulse)
        elif spec.capture_id:
            pulse()
            frames, manifest = replay_capture(spec)
        else:
            from src.simulation.carla_capture import capture

            frames, manifest = capture(spec.scenario, root / "capture", pulse)
        digest = hashlib.sha256()
        reference_digest = hashlib.sha256()
        reference_digest.update(manifest.get("dataset_reference_sha256", "").encode())
        for frame in frames:
            for key in ("x", "labels", "valid", "flow", "flow_valid", "rotation", "translation"):
                digest.update(np.ascontiguousarray(frame[key]).tobytes())
            for key in ("labels", "valid", "rotation", "translation"):
                reference_digest.update(np.ascontiguousarray(frame[key]).tobytes())
        manifest["input_sha256"] = digest.hexdigest()
        manifest["reference_sha256"] = reference_digest.hexdigest()
        (root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        results = {}
        for name in spec.model_ids:
            pulse(f"inference:{name}")
            from src.inference.current import CurrentCheckpoint

            adapter = CurrentCheckpoint(name, get_settings().experiment_device)
            evaluator = BevEvaluator()
            cache_identity = json.dumps(
                {
                    "input": digest.hexdigest(),
                    "checkpoint": adapter.digest,
                    "pipeline": "bev-v2",
                    "torch": adapter.torch.__version__,
                    "device": adapter.device,
                },
                sort_keys=True,
            )
            cache_key = hashlib.sha256(cache_identity.encode()).hexdigest()
            cache = store.root() / "cache" / cache_key
            cache.mkdir(parents=True, exist_ok=True)
            hits = 0
            for index, frame in enumerate(frames):
                pulse(f"inference:{name}:{index + 1}/{len(frames)}")
                path = cache / f"{index:04d}.npz"
                if path.is_file():
                    with np.load(path, allow_pickle=False) as data:
                        prediction = {
                            "occupancy": data["occupancy"],
                            "flow": data["flow"] if adapter.task == "flow" else None,
                        }
                    hits += 1
                else:
                    prediction = adapter.predict(frames, index)
                    temp = path.with_suffix(".tmp.npz")
                    np.savez_compressed(
                        temp,
                        occupancy=prediction["occupancy"],
                        flow=prediction["flow"] if prediction["flow"] is not None else np.empty(0),
                    )
                    temp.replace(path)
                output_dir = root / "predictions" / name
                output_dir.mkdir(parents=True, exist_ok=True)
                # Small per-frame occupancy artifacts can be inspected via the API.
                (output_dir / f"{index:04d}.json").write_text(
                    json.dumps(
                        {
                            "frame_id": frame["id"],
                            "shape": [200, 200],
                            "cells": prediction["occupancy"].reshape(-1).tolist(),
                            "classes": ["free", "static", "object"],
                            "resolution_m": 0.5,
                            "extent_m": 50,
                            "source": spec.source,
                            "model": name,
                            "checkpoint_sha256": adapter.digest,
                        }
                    ),
                    encoding="utf-8",
                )
                evaluator.add(frame, prediction)
            metrics = evaluator.report(adapter.timing)
            results[name] = {
                "metrics": metrics,
                "cache_hits": hits,
                "checkpoint_sha256": adapter.digest,
                "device": adapter.device,
                "torch": adapter.torch.__version__,
                "hardware": platform.platform(),
                "timing_note": "Fresh inference frames only; no latency claim for cached predictions",
            }
            del adapter
        pulse("evaluate")
        store.finish(
            ident,
            owner,
            "succeeded",
            result={
                "manifest": manifest,
                "models": results,
                "recommendation": recommend(results, spec.max_latency_ms),
                "limitations": manifest["limitations"]
                + [
                    "BEV 2D, not 3D boxes; no mAP/NDS or pedestrian detection recall",
                    "Current checkpoints do not consume camera; RGB weather alone is not a model robustness test",
                ],
            },
        )
    except InterruptedError as exc:
        store.finish(ident, owner, "cancelled", error=str(exc))
    except KeyboardInterrupt:
        store.finish(ident, owner, "cancelled", error="Worker interrupted")
        raise
    except Exception as exc:
        logger.exception("Experiment %s failed", ident)
        store.finish(ident, owner, "failed", error=f"{type(exc).__name__}: {exc}")
    return store.get(ident)
