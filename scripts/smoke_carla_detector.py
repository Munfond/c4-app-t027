"""GPU detector smoke on a verified raw episode. No evaluation/training claim."""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from scripts.fetch_detector_checkpoint import CONTENT_SHA256, MODELS  # noqa: E402
from src.active_sensing.episode_inputs import RawEpisode  # noqa: E402
from src.active_sensing.lidar_adapter import (  # noqa: E402
    camera_to_lidar_calibration,
    predicted_boxes_to_ego,
    single_sweep_points,
)
from src.simulation.carla_rig import sha256_file  # noqa: E402

UPSTREAM_SHA = "fe25f7a51d36e3702f961e198894580d83c4387b"


def smoke(args):
    import numpy as np
    import torch
    from mmdet3d.apis import inference_detector, init_model
    from mmdet3d.utils import register_all_modules
    from mmengine.config import Config
    from mmengine.runner import load_checkpoint
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for this smoke")
    if not 0 < args.keep_fraction <= 1:
        raise ValueError("Keep fraction must be in (0,1]")
    if not 0 <= args.threshold <= 1:
        raise ValueError("Score threshold must be between 0 and 1")
    if not 1 <= args.frames <= 20:
        raise ValueError("Smoke is bounded to 1..20 frames")
    if args.output.exists():
        raise ValueError("Output already exists; choose a new directory")
    upstream = PROJECT / "data/runtime/mmdetection3d-v1.4.0"
    import subprocess
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=upstream, text=True).strip()
    if revision != UPSTREAM_SHA:
        raise ValueError("Unexpected detector source revision")
    if subprocess.run(['git', 'diff', '--quiet', 'HEAD'], cwd=upstream).returncode:
        raise ValueError('Detector tracked source has changed from the pinned revision')
    sys.path.insert(0, str(upstream))
    checkpoint = PROJECT / "data/runtime/detector-checkpoints" / MODELS[args.model]
    checkpoint_sha = CONTENT_SHA256[args.model]
    if sha256_file(checkpoint) != checkpoint_sha:
        raise ValueError("Checkpoint SHA mismatch")
    episode = RawEpisode(args.episode)
    if args.frames > len(episode.manifest["frames"]):
        raise ValueError("Insufficient episode frames")
    config_name = ('bevfusion_lidar-cam' if args.model == 'camera_lidar' else 'bevfusion_lidar')
    config_path = upstream / f"projects/BEVFusion/configs/{config_name}_voxel0075_second_secfpn_8xb4-cyclic-20e_nus-3d.py"
    config = Config.fromfile(config_path)
    # Remove multi-sweep padding: this experiment supplies one measured sweep, not 10 copies.
    config.test_dataloader.dataset.pipeline = [step for step in config.test_dataloader.dataset.pipeline
                                              if step["type"] != "LoadPointsFromMultiSweeps"]
    config.test_dataloader.dataset.pipeline[-1]["keys"] = (["img", "points"]
                                                         if args.model == 'camera_lidar' else ["points"])
    image_policy = None
    if args.model == 'camera_lidar':
        # All backbone keys are required by strict full-checkpoint loading below;
        # downloading an ImageNet initializer would be redundant and unmeasured.
        config.model.img_backbone.init_cfg = None
        # Upstream's fixed .48 resize assumes 1600x900 nuScenes images. Applied to
        # 640x360 it black-pads most of the input. Preserve measured K/extrinsics,
        # resize uniformly to cover 704x256, and record the same bottom/center crop.
        options = episode.manifest['rig_options']
        resize = max(704 / options['width'], 256 / options['height'])
        for step in config.test_dataloader.dataset.pipeline:
            if step['type'] == 'ImageAug3D':
                step['resize_lim'] = [resize, resize]
            elif step['type'] == 'BEVLoadMultiViewImageFromFiles':
                step['num_views'] = 6
            elif step['type'] == 'LoadPointsFromFile':
                step['type'] = 'LoadPointsFromDict'
        image_policy = {'resize': resize, 'final_hw': [256, 704],
                        'policy': 'uniform cover + bottom/center crop; upstream ImageAug3D updates img_aug_matrix',
                        'input_wh': [options['width'], options['height']],
                        'camera_order': ['CAM_FRONT', 'CAM_FRONT_RIGHT', 'CAM_FRONT_LEFT',
                                         'CAM_BACK', 'CAM_BACK_LEFT', 'CAM_BACK_RIGHT']}
    register_all_modules(init_default_scope=False)
    model = init_model(config, str(checkpoint), device="cuda:0")
    # Upstream init is permissive; require exact keys/shapes before collecting any evidence.
    load_checkpoint(model, str(checkpoint), map_location="cpu", strict=True)
    model.eval()
    args.output.mkdir(parents=True)
    torch.cuda.reset_peak_memory_stats()
    result_frames = []
    for index in range(args.frames):
        ref = episode.manifest["frames"][index]
        meta = json.loads(episode._artifact(ref["metadata"], "").read_text())
        sensor = meta["sensors"]["LIDAR_TOP"]
        with np.load(episode._artifact(sensor["artifact"], "inputs"), allow_pickle=False) as data:
            points = single_sweep_points(data["raw"], args.intensity_policy)
        if args.keep_fraction < 1:
            count = max(1, int(np.ceil(len(points) * args.keep_fraction)))
            selected_indices = np.sort(np.random.default_rng(args.seed + ref["frame_id"]).choice(
                len(points), size=count, replace=False))
            points = points[selected_indices]
        input_sha = hashlib.sha256(points.tobytes()).hexdigest()
        camera_artifacts = {}
        def infer():
            return inference_detector(model, points)[0]
        if args.model == 'camera_lidar':
            from mmdet3d.structures import get_box_type
            from mmengine.dataset import Compose, pseudo_collate
            images = {}
            for name in image_policy['camera_order']:
                camera = meta['sensors'][name]
                path = episode._artifact(camera['artifact'], 'inputs')
                images[name] = dict(camera_to_lidar_calibration(sensor, camera), img_path=str(path))
                camera_artifacts[name] = camera['artifact']
            pipeline = Compose(config.test_dataloader.dataset.pipeline)
            box_type, box_mode = get_box_type(config.test_dataloader.dataset.box_type_3d)

            def infer():
                data = pipeline(dict(points=points.copy(), images=images, timestamp=ref['timestamp'],
                                     box_type_3d=box_type, box_mode_3d=box_mode))
                return model.test_step(pseudo_collate([data]))[0]

        # First frame warmup is logged, not reused as timing/quality evidence.
        if index == 0:
            with torch.inference_mode(), torch.autocast("cuda", enabled=args.amp):
                infer()
            torch.cuda.synchronize()
        start, end = torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True)
        torch.cuda.synchronize()
        wall = time.perf_counter()
        start.record()
        with torch.inference_mode(), torch.autocast("cuda", enabled=args.amp):
            prediction = infer()
        end.record()
        torch.cuda.synchronize()
        elapsed = (time.perf_counter() - wall) * 1000
        kernel_work = None
        if args.measure_kernels:
            # Separate pass: profiler overhead must not inflate the wall-latency sample above.
            with torch.profiler.profile(activities=[torch.profiler.ProfilerActivity.CPU,
                                                     torch.profiler.ProfilerActivity.CUDA]) as prof:
                with torch.inference_mode(), torch.autocast("cuda", enabled=args.amp):
                    infer()
                torch.cuda.synchronize()
            activities = [event for event in prof.events() if event.device_type == torch.autograd.DeviceType.CUDA]
            if not activities:
                raise RuntimeError("CUPTI returned no CUDA activity; cannot record GPU work")
            kernel_work = {"cuda_activity_sum_ms": sum(e.self_cuda_time_total for e in activities) / 1000,
                           "cuda_activity_count": len(activities),
                           "scope": "detector forward pipeline kernels/copies only; separate profiled pass"}
        instances = prediction.pred_instances_3d
        scores = instances.scores_3d.cpu().numpy()
        labels = instances.labels_3d.cpu().numpy()
        native = instances.bboxes_3d
        boxes = predicted_boxes_to_ego(native.gravity_center.cpu().numpy(), native.dims.cpu().numpy(),
                                      native.yaw.cpu().numpy(), sensor)
        selected = []
        for box, score, label in zip(boxes, scores, labels):
            if float(score) >= args.threshold:
                selected.append(dict(box, score=float(score), class_name=config.class_names[int(label)]))
        row = {"index": index, "frame_id": ref["frame_id"], "timestamp": ref["timestamp"],
               "input_points": len(points), "input_sha256": input_sha, "cuda_work": kernel_work, "boxes": selected, "gpu_event_elapsed_ms": start.elapsed_time(end),
               "camera_artifacts": camera_artifacts,
               "wall_inference_ms": elapsed, "warmup_excluded": True}
        (args.output / f"frame_{index:05d}.json").write_text(json.dumps(row, indent=2, allow_nan=False))
        result_frames.append({k: v for k, v in row.items() if k != "boxes"} | {"boxes_above_threshold": len(selected)})
    resolved = config.pretty_text
    (args.output / "resolved-config.py").write_text(resolved)
    report = {"kind": "CARLA_single_sweep_detector_smoke", "status": "succeeded", "source_sha": revision,
              "model_variant": args.model, "checkpoint_sha256": checkpoint_sha,
              "tracked_upstream_source_clean": True,
              "upstream_filename_fingerprint_matches": checkpoint_sha.startswith(checkpoint.stem.rsplit('-', 1)[-1]),
              "source_config_sha256": sha256_file(config_path),
              "resolved_config_sha256": hashlib.sha256(resolved.encode()).hexdigest(),
              "capture_manifest_sha256": episode.verification["manifest_sha256"],
              "torch": torch.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
              "amp": args.amp, "intensity_policy": args.intensity_policy, "sweeps": 1,
              "image_policy": image_policy,
              "adapter_sha256": sha256_file(PROJECT / 'src/active_sensing/lidar_adapter.py'),
              "strict_checkpoint_loading": True, "keep_fraction": args.keep_fraction, "sampling_seed": args.seed,
              "sampling_algorithm": "numpy.default_rng(seed+frame_id), sorted subset indices",
              "cuda_activity_measurement": args.measure_kernels,
              "score_threshold": args.threshold, "frames": result_frames,
              "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
              "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
              "measured_perception_replay_ready": False,
              "limitations": ["No detection quality score: GT coverage/class mapping not validated",
                              "Single-sweep distribution differs from training; no fake padded history",
                              "CARLA intensity is not calibrated to nuScenes",
                              "CUDA event elapsed includes stream idle gaps/CPU dispatch; not total GPU work/window",
                              "Monitoring/profile switching/other tasks not timed; cannot claim agent GPU savings",
                              "Simulator stopped before inference to release VRAM; not closed-loop real-time performance"]}
    (args.output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument('--model', choices=MODELS, default='lidar')
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=1)
    parser.add_argument("--amp", action="store_true")
    parser.add_argument("--measure-kernels", action="store_true")
    parser.add_argument("--keep-fraction", type=float, default=1)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--threshold", type=float, default=.3)
    parser.add_argument("--intensity-policy", choices=("raw", "scale_255_approximation"), default="raw")
    args = parser.parse_args()
    os.environ.setdefault("MPLCONFIGDIR", "/tmp/p027-detector-matplotlib")
    print(json.dumps(smoke(args), indent=2))
