"""Read-only sealed live-selector evidence; actor input is RAW only, evaluation is post-capture."""

import hashlib
import json
import math

import numpy as np

from src.active_sensing.native_contract import ABI, BASELINE, PROFILES, read_sealed, sensor_context
from src.config import get_settings
from src.evaluation.bev import BevEvaluator
from src.services.native_rl_evidence import read_report as frozen_policy
from src.simulation.online_sensor_gate import sensor_name

# Explicit registry: no user-supplied path or arbitrary filesystem browse.
RUNS = {
    "ppo-smoke": "native-online-ppo-smoke-20261014",
    "gate-smoke": "native-online-gate-smoke-20261014",
    "full20": "native-online-full20-20261014",
    "full20-retry1": "native-online-full20-retry1-20261014",
    "ppo20": "native-online-ppo20-20261014",
}
MODES = {"ppo", "full_baseline", "diagnostic_schedule_not_policy"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def root(run):
    return get_settings().native_online_root / RUNS[run]


def bounded_sealed(path):
    if path.stat().st_size > 2_000_000:
        raise ValueError("Online evidence too large")
    return read_sealed(path)


def read_core(directory):
    report, report_hash = bounded_sealed(directory / "report.json")
    plan, plan_hash = bounded_sealed(directory / "plan.json")
    manifest = json.loads((directory / "capture/manifest.json").read_text())
    n = report["frames"]
    if (
        report.get("kind") != "native_online_sensor_selector_evidence_v1"
        or report.get("status") != "completed"
        or report.get("training") is not False
        or report.get("deployment_ready") is not False
        or report["mode"] not in MODES
        or type(n) is not int
        or n not in (4, 20)
        or report["decisions"] != n - 1
        or len(report["trace"]) != n
        or len(manifest["frames"]) != n
        or plan["frames"] != n
        or plan["mode"] != report["mode"]
        or plan_hash != report["plan_sha256"]
        or plan["profiles"] != PROFILES
        or plan["initial_action"] != BASELINE
        or report["native_policy_report_sha256"] != plan["native_report_sha256"]
        or report["policy_sha256"] != (plan["policy_sha256"] if report["mode"] == "ppo" else None)
        or manifest.get("online_sensor_selector") is not True
        or manifest["scenario"]["route_spawn_index"] != plan["route"]
        or manifest["scenario"]["seed"] != plan["seed"]
        or manifest["scenario"]["map"] != plan["map"]
        or manifest["scenario"]["weather"] != plan["weather"]
    ):
        raise ValueError("Online selector protocol mismatch")
    for action, profile in enumerate(PROFILES):
        attrs = manifest["online_sensor_bank_actual_attributes"][sensor_name(action)]
        if any(float(attrs[k]) != v for k, v in profile.items()):
            raise ValueError("Actual sensor bank mismatch")
    prior = BASELINE
    for i, row in enumerate(report["trace"]):
        a, b = row["current_action"], row["next_action"]
        obs = np.asarray(row["observation"], dtype=float)
        if (
            type(a) is not int
            or not 0 <= a < 12
            or type(b) is not int
            or not 0 <= b < 12
            or row["index"] != i
            or a != prior
            or row["current_profile"] != PROFILES[a]
            or row["mode"] != report["mode"]
            or row["observation_abi"] != ABI
            or row["frame_id"] != manifest["frames"][i]["frame_id"]
            or row["applies_to_capture_index"] != (None if i == n - 1 else i + 1)
            or obs.shape != (19,)
            or not np.isfinite(obs).all()
            or not np.array_equal(obs[7:], [float(k == a) for k in range(12)])
            or (report["mode"] == "full_baseline" and (a != BASELINE or b != BASELINE))
            or (i == n - 1 and b != a)
        ):
            raise ValueError("Online causal action/observation mismatch")
        for field in ("cpu_feature_model_ms", "cpu_policy_ms", "cpu_model_only_ms"):
            value = row.get(field)
            if value is None:
                if field == "cpu_feature_model_ms" or (field == "cpu_policy_ms" and i < n - 1):
                    raise ValueError("Missing online timing")
            elif type(value) not in (float, int) or not math.isfinite(value) or value < 0:
                raise ValueError("Invalid online timing")
        prior = b
    return report, report_hash, plan, manifest


def files_for(index):
    return [f"capture/frame_{index:04d}.{ext}" for ext in ("npz", "json", "png")] + [
        f"capture/online-predictions/{index:04d}.npz",
        f"capture/ipc/signal-{index:04d}.npz",
    ]


def seal_artifacts(directory):
    """Explicit audit/seal, never called by GET and never rewrites a completed report."""
    target = directory / "artifacts.json"
    if target.exists():
        raise ValueError("Preserve existing artifact seal")
    report, report_hash, _, manifest = read_core(directory)
    reference_hash = hashlib.sha256()
    evaluator = BevEvaluator()
    files = {"capture/manifest.json": digest(directory / "capture/manifest.json")}
    for i, row in enumerate(report["trace"]):
        for name in files_for(i):
            files[name] = digest(directory / name)
        if (
            files[f"capture/online-predictions/{i:04d}.npz"] != row["prediction_sha256"]
            or files[f"capture/ipc/signal-{i:04d}.npz"] != row["signal_sha256"]
        ):
            raise ValueError("Changed recorded prediction or actor signal")
        meta = json.loads((directory / f"capture/frame_{i:04d}.json").read_text())
        if (
            meta["selected_lidar_action"] != row["current_action"]
            or meta["simulation_frame_id"] != row["frame_id"]
            or meta["camera_frame_id"] != row["frame_id"]
        ):
            raise ValueError("Camera/selector frame synchronization mismatch")
        with (
            np.load(directory / f"capture/frame_{i:04d}.npz", allow_pickle=False) as data,
            np.load(directory / f"capture/ipc/signal-{i:04d}.npz", allow_pickle=False) as raw,
            np.load(directory / f"capture/online-predictions/{i:04d}.npz", allow_pickle=False) as pred,
        ):
            if (
                set(raw.files) != {"points", "intensity"}
                or not np.array_equal(raw["points"], data["feature_points"])
                or not np.array_equal(raw["intensity"], data["feature_intensity"])
            ):
                raise ValueError("Actor signal must match selected RAW only")
            if not np.allclose(
                row["observation"][:6], sensor_context(raw["points"], raw["intensity"]), atol=1e-7, rtol=0
            ) or not np.isclose(row["observation"][6], min(row["cpu_feature_model_ms"] / 500, 1), atol=1e-7):
                raise ValueError("Observation differs from current raw signal/timing")
            labels, valid, prediction = data["labels"], data["valid"], pred["prediction"]
            if (
                labels.shape != (200, 200)
                or valid.shape != labels.shape
                or valid.dtype != np.bool_
                or prediction.shape != labels.shape
                or not np.isin(labels, [0, 1, 2]).all()
                or not np.isin(prediction, [0, 1, 2]).all()
            ):
                raise ValueError("Invalid online occupancy/reference grid")
            for k in ("labels", "valid", "rotation", "translation"):
                reference_hash.update(data[k].tobytes())
            evaluator.add({"labels": labels, "valid": valid}, {"occupancy": prediction, "flow": None})
    recomputed = evaluator.report([])
    for k in ("confusion", "evaluated_cells", "occupied_iou", "class_iou", "frame_count"):
        if recomputed[k] != report["metrics"][k]:
            raise ValueError("Online metrics differ from observed-cell predictions")
    if reference_hash.hexdigest() != report["reference_sha256"]:
        raise ValueError("Online reference hash mismatch")
    value = {
        "kind": "native_online_artifact_audit_v1",
        "report_sha256": report_hash,
        "files": files,
        "reference_sha256": reference_hash.hexdigest(),
        "frames": len(manifest["frames"]),
    }
    target.write_text(json.dumps(value, indent=2) + "\n")
    target.with_suffix(".sha256").write_text(digest(target) + "\n")
    return value


def snapshot(run):
    directory = root(run)
    report, report_hash, plan, manifest = read_core(directory)
    native = frozen_policy()
    if (
        not native.get("ready")
        or native["evidence_sha256"] != plan["native_report_sha256"]
        or native["policy_file_sha256"] != plan["policy_sha256"]
        or native["report"]["checkpoint_sha256"] != plan["checkpoint_sha256"]
        or native["report"]["adapter"] != plan["adapter"]
    ):
        raise ValueError("Online capture differs from frozen policy/model/input adapter")
    ledger, ledger_hash = bounded_sealed(directory / "artifacts.json")
    expected = {"capture/manifest.json", *[name for i in range(report["frames"]) for name in files_for(i)]}
    if (
        ledger.get("kind") != "native_online_artifact_audit_v1"
        or ledger["report_sha256"] != report_hash
        or set(ledger["files"]) != expected
        or ledger["reference_sha256"] != report["reference_sha256"]
        or ledger["frames"] != report["frames"]
        or ledger["files"]["capture/manifest.json"] != digest(directory / "capture/manifest.json")
    ):
        raise ValueError("Online artifact audit differs from report")
    # First diagnostic predates timing separation. Preserve its original bytes;
    # never display the old mislabeled feature+model value as model-only latency.
    metrics = dict(report["metrics"])
    legacy_timing = "timing_scope" not in report
    if legacy_timing:
        metrics["latency_model_only_ms"] = None
    return {
        "id": run,
        "ready": True,
        "report_sha256": report_hash,
        "artifact_audit_sha256": ledger_hash,
        "mode": report["mode"],
        "frames": report["frames"],
        "decisions": report["decisions"],
        "trace": report["trace"],
        "metrics": metrics,
        "reference_sha256": report["reference_sha256"],
        "policy_sha256": report["policy_sha256"],
        "policy_report_sha256": report["native_policy_report_sha256"],
        "checkpoint_sha256": plan["checkpoint_sha256"],
        "timestamps": [r["timestamp"] for r in manifest["frames"]],
        "interval": manifest["scenario"]["capture_interval"],
        "route": plan["route"],
        "seed": plan["seed"],
        "legacy_timing": legacy_timing,
        "limits": report["limits"],
        "training": False,
        "deployment_ready": False,
    }


def catalog():
    items, unavailable, pending = [], [], []
    for run in RUNS:
        try:
            if not (root(run) / "report.json").exists():
                status = root(run) / "status.json"
                plan = root(run) / "plan.json"
                if status.is_file() and status.stat().st_size < 2000:
                    value = json.loads(status.read_text())
                    pending.append({"id": run, "status": value.get("status"), "frames": value.get("frames", 0)})
                elif plan.is_file():
                    pending.append({"id": run, "status": "planned", "frames": 0})
                continue
            items.append(snapshot(run))
        except (OSError, ValueError, KeyError, TypeError):
            unavailable.append(run)
    return {"items": items, "unavailable": unavailable, "pending": pending}


def artifact(run, index, kind):
    value = snapshot(run)
    if type(index) is not int or not 0 <= index < value["frames"]:
        raise FileNotFoundError("Frame outside completed capture")
    directory = root(run)
    if kind == "prediction":
        name = f"capture/online-predictions/{index:04d}.npz"
    elif kind in ("npz", "json", "png"):
        name = f"capture/frame_{index:04d}.{kind}"
    else:
        raise KeyError("Unsupported online artifact")
    ledger, _ = bounded_sealed(directory / "artifacts.json")
    path = directory / name
    if not path.resolve().is_relative_to(directory.resolve()) or digest(path) != ledger["files"][name]:
        raise ValueError("Changed online frame artifact")
    return path


def frame_prediction(run, index):
    with np.load(artifact(run, index, "prediction"), allow_pickle=False) as data:
        pred = data["prediction"]
        if pred.shape != (200, 200) or not np.isin(pred, [0, 1, 2]).all():
            raise ValueError("Invalid occupancy prediction")
        return {"cells": pred.reshape(-1).tolist()}
