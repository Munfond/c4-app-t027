"""Audit a physical CARLA profile pilot; never promotes it into a training dataset."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from src.evaluation.bev import BevEvaluator
from src.inference.bev import lidar_features
from src.inference.native_input import apply, fingerprint
from src.services import experiment_store as store
from src.services import sensor_studies as studies
from src.services.agent_evidence import evidence
from src.services.experiment_registry import verified_hash


def audit(study_ids):
    reports, profiles, errors = [], {}, []
    checkpoint = verified_hash("occupancy_lidar")
    adapter = fingerprint("intensity_mean_experimental")
    for ident in study_ids:
        study = studies.get(ident)
        if study["status"] != "completed":
            raise ValueError(f"Pilot incomplete: {ident} is {study['status']}")
        reports.append(evidence(ident))
        for entry in study["jobs"]:
            job = store.get(entry["id"])
            if job["status"] != "succeeded":
                errors.append({"job_id": job["id"], "error": job["error"]})
                continue
            result = job["result"]
            request, manifest = job["spec"]["request"], result["manifest"]
            if len(manifest["frames"]) != request["scenario"]["frames"]:
                raise ValueError("Incomplete native capture")
            if (
                job["spec"]["checkpoints"]["occupancy_lidar"] != checkpoint
                or manifest.get("native_input_adapter") != adapter
            ):
                raise ValueError("Mixed checkpoint or input adapter")
            lidar = request["scenario"]["lidar"]
            attrs = manifest["sensor_specs"]["lidar"][1]
            if (
                float(attrs["channels"]) != lidar["channels"]
                or float(attrs["points_per_second"]) != lidar["points_per_second"]
            ):
                raise ValueError("Requested profile differs from sensor attributes")
            evaluator, raw_hashes, counts = BevEvaluator(), {}, []
            digest, reference_digest = hashlib.sha256(), hashlib.sha256()
            for index, item in enumerate(manifest["frames"]):
                name = f"frame_{index:04d}"
                if item["id"] != name:
                    raise ValueError("Invalid frame catalog")
                capture = store.root() / job["id"] / "capture" / f"{name}.npz"
                raw_hashes[name] = hashlib.sha256(capture.read_bytes()).hexdigest()
                with np.load(capture, allow_pickle=False) as data:
                    x = lidar_features(data["feature_points"], data["feature_intensity"])
                    if not np.array_equal(x, data["x"]):
                        raise ValueError("Raw points/intensity do not reproduce saved features")
                    counts.append(len(data["feature_points"]))
                    frame = {key: data[key] for key in ("x", "labels", "valid", "rotation", "translation")}
                frame.update(flow=np.zeros((2, 200, 200), np.float32), flow_valid=np.zeros((200, 200), bool))
                adjusted = apply([frame], adapter)[0]
                for key in ("x", "labels", "valid", "flow", "flow_valid", "rotation", "translation"):
                    digest.update(np.ascontiguousarray(adjusted[key]).tobytes())
                for key in ("labels", "valid", "rotation", "translation"):
                    reference_digest.update(np.ascontiguousarray(frame[key]).tobytes())
                prediction = json.loads(
                    (store.root() / job["id"] / f"predictions/occupancy_lidar/{index:04d}.json").read_text()
                )
                cells = np.asarray(prediction["cells"])
                if cells.size != 40000 or not np.isin(cells, [0, 1, 2]).all():
                    raise ValueError("Invalid prediction grid")
                evaluator.add(frame, {"occupancy": cells.reshape(200, 200).astype(np.uint8), "flow": None})
            recomputed = evaluator.report([])
            if float(np.mean(counts)) != manifest["sensor_cost"]["mean_points_per_tick"]:
                raise ValueError("Raw point count differs from capture manifest")
            metrics = result["models"]["occupancy_lidar"]["metrics"]
            if (
                digest.hexdigest() != manifest["input_sha256"]
                or reference_digest.hexdigest() != manifest["reference_sha256"]
                or recomputed["confusion"] != metrics["confusion"]
            ):
                raise ValueError("Input/reference/confusion audit mismatch")
            key = f"channels{lidar['channels']}_{lidar['points_per_second'] // 1000}k"
            row = {
                "profile": key,
                "job_id": job["id"],
                "channels": lidar["channels"],
                "points_per_second": lidar["points_per_second"],
                "frames": len(counts),
                "raw_point_counts": counts,
                "metrics": metrics,
                "raw_npz_sha256": raw_hashes,
                "reference_sha256": manifest["reference_sha256"],
                "input_sha256": manifest["input_sha256"],
                "sampled_lidar_bytes_per_second": manifest["sensor_cost"]["estimated_lidar_bytes_per_second"],
            }
            if key in profiles and profiles[key]["reference_sha256"] != row["reference_sha256"]:
                raise ValueError("Repeated baseline has a different reference")
            profiles.setdefault(key, row)
    if len({p["reference_sha256"] for p in profiles.values()}) != 1:
        raise ValueError("Profiles cannot be paired: reference mismatch")
    expected = {f"channels{c}_{r}k" for c in (16, 32, 64) for r in (150, 300, 450, 600)}
    complete = not errors and set(profiles) == expected
    return {
        "kind": "audited_native_12_profile_integration_pilot",
        "status": "complete_pilot" if complete else "incomplete",
        "checkpoint_sha256": checkpoint,
        "adapter": adapter,
        "profiles": list(profiles.values()),
        "errors": errors,
        "study_evidence": reports,
        "native_rl_admitted": False,
        "limitations": [
            "One Town01 route and four frames per profile: no independent training/validation/test split",
            "Only LiDAR occupancy proxy; no full sensor fusion, real-world safety or weather robustness claim",
            "Cache hits are reported; absent model timing must not be filled from a different trial",
            "Physical sensor settings verified; no upsampling of 16/32-channel returns into 64 channels",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path, help="JSON with registered study_ids")
    parser.add_argument("--plan", type=Path, required=True, help="Sealed plan written before the additional captures")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Preserve prior evidence; choose a new output")
    catalog = json.loads(args.catalog.read_text())
    actual = hashlib.sha256(args.plan.read_bytes()).hexdigest()
    if actual != catalog["plan_sha256"] or actual != args.plan.with_suffix(".sha256").read_text().strip():
        raise ValueError("Registered plan changed")
    plan = json.loads(args.plan.read_text())
    if catalog["study_ids"][0] != plan["existing_study"] or len(catalog["study_ids"]) != 1 + len(
        plan["additional_studies"]
    ):
        raise ValueError("Study catalog differs from registered plan")
    for ident, expected in zip(catalog["study_ids"][1:], plan["additional_studies"], strict=True):
        if studies.get(ident)["spec"] != expected:
            raise ValueError("Study spec differs from registered plan")
    report = audit(catalog["study_ids"])
    report["plan_sha256"] = catalog["plan_sha256"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    args.output.with_suffix(".sha256").write_text(hashlib.sha256(args.output.read_bytes()).hexdigest() + "\n")
    print(json.dumps({"status": report["status"], "profiles": len(report["profiles"]), "native_rl_admitted": False}))


if __name__ == "__main__":
    main()
