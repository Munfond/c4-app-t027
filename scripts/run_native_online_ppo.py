"""Frozen PPO sensor-gate smoke on fresh CARLA; no training and no vehicle-control action."""

import argparse
import hashlib
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from src.active_sensing.native_occupancy import BASELINE, PROFILES, read_sealed
from src.active_sensing.native_online import NativeOnlineController
from src.config import PROJECT_ROOT, get_settings
from src.evaluation.bev import BevEvaluator
from src.inference.current import CurrentCheckpoint
from src.inference.native_input import fingerprint
from src.models.experiments import ScenarioSpec
from src.services.native_rl_evidence import read_report, report_path
from src.simulation.carla_capture import simulator_lock
from src.simulation.carla_server import fresh_server


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def protocol(args):
    evidence = read_report()
    if not evidence["ready"]:
        raise ValueError("Verified frozen native PPO evidence required")
    if args.route in (0, 5, 17, 22, 31, 48, 72):
        raise ValueError("Use a fresh route, not training/validation/test or prior calibration routes")
    return {
        "kind": "native_online_selector_smoke_plan_v1",
        "mode": args.mode,
        "route": args.route,
        "seed": args.seed,
        "frames": args.frames,
        "map": "Town01",
        "weather": "clear",
        "vehicles": 2,
        "pedestrians": 0,
        "profiles": PROFILES,
        "initial_action": BASELINE,
        "native_report_sha256": evidence["evidence_sha256"],
        "policy_sha256": evidence["policy_file_sha256"],
        "checkpoint_sha256": evidence["report"]["checkpoint_sha256"],
        "adapter": evidence["report"]["adapter"],
        "selection": "Current selected raw signal and measured CPU latency -> next capture profile; no GT or other streams in actor",
        "deployment_ready": False,
        "training": False,
        "limits": [
            "All12 sensor variants stay spawned; select model input only, no physical power saving",
            "Sim-time2Hz is not real-time wall-clock guarantee",
            "No weather degradation/radar/model switching or ROS2 claim",
            "One fresh route smoke, not performance/generalization evidence",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("ppo", "full_baseline", "diagnostic_schedule_not_policy"), default="ppo")
    parser.add_argument("--route", type=int, default=110)
    parser.add_argument("--seed", type=int, default=210)
    parser.add_argument("--frames", type=int, choices=(4, 20), default=4)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--run-sealed-plan", action="store_true")
    args = parser.parse_args()
    plan = protocol(args)
    plan_path = args.output / "plan.json"
    if args.plan_only:
        if args.output.exists():
            parser.error("Preserve existing output")
        args.output.mkdir(parents=True)
        write(plan_path, plan)
        plan_path.with_suffix(".sha256").write_text(sha(plan_path) + "\n")
        print(json.dumps({"planned": True, "mode": args.mode, "frames": args.frames, "training": False}))
        return
    if not args.run_sealed_plan:
        parser.error("Seal plan with --plan-only before running")
    original, _ = read_sealed(plan_path)
    if original != plan or (args.output / "status.json").exists():
        parser.error("Plan changed or previous execution exists; choose a new output")
    capture = args.output.resolve() / "capture"
    capture.mkdir()
    ipc = capture / "ipc"
    ipc.mkdir()
    settings = get_settings()
    if not settings.carla_server_executable or settings.carla_python_executable:
        raise ValueError("Matching managed Linux simulator/runtime required")
    model = CurrentCheckpoint("occupancy_lidar", "cpu")
    if model.digest != plan["checkpoint_sha256"] or fingerprint("intensity_mean_experimental") != plan["adapter"]:
        raise ValueError("Changed frozen model/input adapter")
    policy = None
    if args.mode == "ppo":
        from stable_baselines3 import PPO

        selected = read_report()["report"]["selected_policy"]
        policy = PPO.load(report_path().parent / selected, device="cpu")
        if policy.observation_space.shape != (19,) or policy.action_space.n != 12:
            raise ValueError("Policy observation/action ABI mismatch")

        def choose(obs, index):
            return int(policy.predict(obs, deterministic=True)[0])
    elif args.mode == "full_baseline":

        def choose(obs, index):
            return BASELINE
    else:

        def choose(obs, index):
            return (0, 11, 7)[index % 3]

    controller = NativeOnlineController(model, choose, plan["adapter"], mode=args.mode)
    scenario = ScenarioSpec(
        map="Town01",
        weather="clear",
        vehicles=2,
        pedestrians=0,
        frames=args.frames,
        route_spawn_index=args.route,
        seed=args.seed,
        traffic_placement="nearest_spawn",
    )
    request = {
        "mode": "capture_online",
        "scenario": scenario.model_dump(),
        "root": str(capture),
        "client_path": None,
        "settings": {
            k: getattr(settings, k)
            for k in (
                "carla_host",
                "carla_port",
                "carla_tm_port",
                "carla_timeout_seconds",
                "carla_follow_ego",
                "carla_realtime_capture",
            )
        },
    }
    request_file = capture / "client-request.json"
    write(request_file, request)
    process = None
    started = time.perf_counter()

    def interrupt(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        write(args.output / "status.json", {"status": "running", "frames": 0, "training": False})
        with simulator_lock(settings), fresh_server(settings, capture, lambda: None) as pulse:
            with (capture / "client.log").open("w") as log:
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-u",
                        "-X",
                        "faulthandler",
                        str(PROJECT_ROOT / "scripts/carla_legacy_client.py"),
                        "--request",
                        str(request_file),
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                try:
                    deadline = time.monotonic() + settings.carla_bridge_timeout_seconds
                    while process.poll() is None:
                        pulse()
                        if time.monotonic() > deadline:
                            raise TimeoutError("Online capture timed out")
                        index = controller.next_index
                        signal_file = ipc / f"request-{index:04d}.json"
                        if signal_file.is_file():
                            value = json.loads(signal_file.read_text())
                            response = controller.process(value, ipc)
                            write(ipc / f"response-{index:04d}.json", response)
                            write(
                                args.output / "status.json",
                                {
                                    "status": "running",
                                    "frames": controller.next_index,
                                    "total": args.frames,
                                    "training": False,
                                },
                            )
                            print(
                                json.dumps(
                                    {
                                        "captured": controller.next_index,
                                        "next_action": controller.current,
                                        "mode": args.mode,
                                    }
                                ),
                                flush=True,
                            )
                        time.sleep(0.01)
                    if process.returncode:
                        raise RuntimeError(
                            f"Isolated online capture failed ({process.returncode}); inspect capture/client.log"
                        )
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait()
        manifest = json.loads((capture / "manifest.json").read_text())
        if len(manifest["frames"]) != args.frames or controller.next_index != args.frames:
            raise ValueError("Incomplete online capture/decision trace")
        evaluator = BevEvaluator()
        reference = hashlib.sha256()
        for index, row in enumerate(controller.trace):
            with np.load(capture / f"frame_{index:04d}.npz", allow_pickle=False) as frame:
                fields = {k: frame[k] for k in ("labels", "valid", "rotation", "translation")}
                # The sensor signal passed to the actor must match the captured selected input exactly.
                with np.load(ipc / f"signal-{index:04d}.npz", allow_pickle=False) as raw:
                    if not np.array_equal(raw["points"], frame["feature_points"]) or not np.array_equal(
                        raw["intensity"], frame["feature_intensity"]
                    ):
                        raise ValueError("Online actor signal differs from selected capture")
            for key in ("labels", "valid", "rotation", "translation"):
                reference.update(fields[key].tobytes())
            fields.update(flow=np.zeros((2, 200, 200), np.float32), flow_valid=np.zeros((200, 200), bool))
            artifact = capture / "online-predictions" / f"{index:04d}.npz"
            if sha(artifact) != row["prediction_sha256"]:
                raise ValueError("Online prediction changed")
            with np.load(artifact, allow_pickle=False) as pred:
                evaluator.add(fields, {"occupancy": pred["prediction"], "flow": None})
            if row["frame_id"] != manifest["frames"][index]["frame_id"]:
                raise ValueError("Online frame synchronization failed")
            metadata = json.loads((capture / f"frame_{index:04d}.json").read_text())
            if metadata["selected_lidar_action"] != row["current_action"]:
                raise ValueError("Requested selector not applied to captured signal")
            if index and controller.trace[index - 1]["next_action"] != row["current_action"]:
                raise ValueError("Action not applied to next capture")
        elapsed = time.perf_counter() - started
        report = {
            "kind": "native_online_sensor_selector_evidence_v1",
            "status": "completed",
            "mode": args.mode,
            "plan_sha256": sha(plan_path),
            "policy_sha256": plan["policy_sha256"] if policy else None,
            "frames": args.frames,
            "decisions": args.frames - 1,
            "trace": controller.trace,
            "warmup_perception_ms": controller.warmup_ms,
            "timing_scope": "model_only=CPU forward;feature_model=CPU featurization+adapter+model;policy=CPU selector;wall includes simulator/IO/warmup",
            "cpu_feature_model_latency_ms": {
                "p50": float(np.percentile([r["cpu_feature_model_ms"] for r in controller.trace], 50)),
                "p95": float(np.percentile([r["cpu_feature_model_ms"] for r in controller.trace], 95)),
            },
            "wall_total_seconds": elapsed,
            "metrics": evaluator.report(
                [r["cpu_model_only_ms"] for r in controller.trace if r["cpu_model_only_ms"] is not None]
            ),
            "reference_sha256": reference.hexdigest(),
            "native_policy_report_sha256": plan["native_report_sha256"],
            "deployment_ready": False,
            "training": False,
            "limits": plan["limits"],
        }
        write(args.output / "report.json", report)
        (args.output / "report.sha256").write_text(sha(args.output / "report.json") + "\n")
        from src.services.native_online_evidence import seal_artifacts

        seal_artifacts(args.output.resolve())
        write(args.output / "status.json", {"status": "completed", "frames": args.frames, "training": False})
        print(
            json.dumps({"status": "completed", "mode": args.mode, "frames": args.frames, "deployment_ready": False}),
            flush=True,
        )
    except BaseException as exc:
        write(
            args.output / "status.json",
            {
                "status": "incomplete",
                "frames": controller.next_index,
                "error_type": type(exc).__name__,
                "training": False,
            },
        )
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
