"""Bounded raw sensor episodes, opt-in CLI only. No detector inference or policy training."""
import argparse
import json
import logging
import math
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import get_settings  # noqa: E402
from src.models.experiments import ScenarioSpec  # noqa: E402
from src.simulation.carla_bridge import run_client  # noqa: E402
from src.simulation.carla_capture import simulator_lock  # noqa: E402
from src.simulation.carla_rig import COMPACT_STORAGE, LEGACY_STORAGE, verify_episode  # noqa: E402
from src.simulation.carla_server import fresh_server  # noqa: E402


def capture_request(args):
    """Validate before starting simulator; the API's 0.5 s cadence remains untouched."""
    if not 0.1 <= args.seconds <= 120:
        raise ValueError("seconds must be between 0.1 and 120")
    if args.hz not in (2, 20):
        raise ValueError("hz must be 2 or 20; profile frequency comparison requires 20")
    if args.width not in (640, 1280) or args.height != round(args.width * 9 / 16):
        raise ValueError("supported camera dimensions are 640x360 and 1280x720")
    scenario = ScenarioSpec(map=args.map, weather=args.weather, vehicles=args.vehicles,
                            pedestrians=args.pedestrians, seed=args.seed,
                            route_spawn_index=args.spawn, route_kind=args.route, frames=1).model_dump()
    scenario.update(frames=math.ceil(args.seconds * args.hz), capture_interval=1 / args.hz)
    options = {"width": args.width, "height": args.height, "fov": 100,
               "include_64": args.include_64, "traffic_placement": args.traffic_placement,
               'record_environment_inventory': getattr(args, 'record_environment_inventory', False),
               "storage_encoding": getattr(args, 'storage_encoding', LEGACY_STORAGE)}
    budget = getattr(args, 'disk_budget_gib', None)
    if budget is not None:
        if not math.isfinite(budget) or not .1 <= budget <= 200 or options['storage_encoding'] != COMPACT_STORAGE:
            raise ValueError('disk-budget-gib must be .1..200 and requires compact storage')
        options['disk_budget_bytes'] = math.floor(budget * 1024 ** 3)
    return {"mode": "capture_rig", "scenario": scenario, "rig_options": options}


def disk_reserve(request):
    """Conservative raw size + logs/headroom, not a promise of compressed size."""
    options = request["rig_options"]
    images = 6 * options["width"] * options["height"] * 4 + 6 * options["width"] * options["height"]
    # Raw and transformed points (float64 XYZ), semantic structured records + XYZ.
    derived = 24 if options['storage_encoding'] == LEGACY_STORAGE else 0
    lidar = 600000 / 20 * (16 + derived) + 1200000 / 20 * (24 + derived)
    if options["include_64"]:
        lidar += 1200000 / 20 * (16 + derived)
    if 'disk_budget_bytes' in options:
        # Explicit bounded capture: limit bytes as they are written and preserve
        # worst-case next-frame reserve plus one GiB. Compression is not promised.
        return options['disk_budget_bytes'] + math.ceil((images + lidar + 200000) * 1.2) + 1024 ** 3
    return math.ceil((images + lidar + 200000) * request["scenario"]["frames"] * 1.2 + 1024 ** 3)


def collect(args, settings=None):
    request = capture_request(args)
    settings = settings or get_settings()
    root = args.output.expanduser().resolve()
    root.parent.mkdir(parents=True, exist_ok=True)
    # A completed/partial directory must never be silently mixed with a new episode.
    if root.exists():
        raise ValueError("Output already exists; choose a new episode directory")
    required = disk_reserve(request)
    available = shutil.disk_usage(root.parent).free
    if available < required:
        raise ValueError(f"Insufficient disk: reserve {required / 1024 ** 3:.2f} GiB; available {available / 1024 ** 3:.2f} GiB")
    request["root"] = str(root)
    with simulator_lock(settings):
        root.mkdir()
        try:
            if settings.carla_server_executable:
                isolated = settings.model_copy(update={"carla_python_executable": Path(sys.executable),
                                                        "carla_client_path": None})
                with fresh_server(settings, root, lambda: None) as managed_pulse:
                    run_client(request, root, managed_pulse, isolated)
                lifecycle = "fresh_server_and_isolated_matching_client"
            else:
                isolated = settings if settings.carla_python_executable else settings.model_copy(
                    update={"carla_python_executable": Path(sys.executable)})
                run_client(request, root, lambda: None, isolated)
                lifecycle = "external_server_isolated_client"
            report = verify_episode(root)
            report["server_lifecycle"] = lifecycle
            report["disk_reserve_bytes"] = required
            (root / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            return report
        except BaseException as exc:
            # A complete-looking file after cancellation/failed verification must not be consumed.
            manifest = root / "manifest.json"
            if manifest.exists():
                manifest.replace(root / "manifest.failed.json")
            # A partial directory stays useful for audit without becoming an
            # admissible episode. Do not summarize it as a verified capture.
            failure = {
                'status': 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                'complete': False, 'exception_type': type(exc).__name__,
                'recorded_at': datetime.now(UTC).isoformat(),
                'requested_frames': request['scenario']['frames'],
                'recorded_frame_metadata_files': sum(1 for _ in root.glob('frame_*.json')),
                'scenario': request['scenario'], 'rig_options': request['rig_options'],
                'artifacts_preserved': True, 'partial_artifact_checksums_verified': False,
                'resume_note': 'Use a new output directory; a new simulator session cannot append to this timeline.',
            }
            try:
                temporary = root / 'capture-failure.json.tmp'
                temporary.write_text(json.dumps(failure, indent=2, allow_nan=False), encoding='utf-8')
                temporary.replace(root / 'capture-failure.json')
            except OSError:
                logging.exception('Could not save capture failure metadata; partial data remains unchanged')
            raise


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--seconds", type=float, default=2)
    capture.add_argument("--hz", type=int, choices=(2, 20), default=20)
    capture.add_argument("--map", choices=("Town01", "Town02", "Town03", "Town04", "Town05"), default="Town01")
    capture.add_argument("--weather", choices=("clear", "rain", "fog"), default="clear")
    capture.add_argument("--vehicles", type=int, default=8)
    capture.add_argument("--pedestrians", type=int, default=0)
    capture.add_argument("--seed", type=int, default=42)
    capture.add_argument("--spawn", type=int, default=0)
    capture.add_argument("--route", choices=("spawn", "highway"), default="spawn")
    capture.add_argument("--width", type=int, default=640)
    capture.add_argument("--height", type=int, default=360)
    capture.add_argument("--include-64", action="store_true")
    capture.add_argument('--storage-encoding', choices=(LEGACY_STORAGE, COMPACT_STORAGE), default=COMPACT_STORAGE)
    capture.add_argument('--disk-budget-gib', type=float,
                         help='Compact-only bounded capture; aborts incomplete on quota/headroom exhaustion, never shortens an episode')
    capture.add_argument('--record-environment-inventory', action=argparse.BooleanOptionalAction, default=True)
    capture.add_argument("--traffic-placement", choices=("nearest_spawn", "spawn_random"), default="nearest_spawn")
    check = sub.add_parser("verify")
    check.add_argument("episode", type=Path)
    args = parser.parse_args()
    try:
        report = collect(args) if args.command == "capture" else verify_episode(args.episode)
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, str(exc) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
