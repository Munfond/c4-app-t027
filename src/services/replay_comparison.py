"""Measured per-model and camera selection; image fidelity never called detection accuracy."""


def compare(study):
    environments = []
    spec = study["spec"]
    for index, scenario in enumerate(spec["scenarios"]):
        jobs = [j for j in study["jobs"] if j["environment"] == index]
        baseline = next(j for j in jobs if j["profile"] == "baseline")
        base = baseline["result"] if baseline["status"] == "succeeded" else None
        base_manifest = base["manifest"] if base else {}
        rows, choices, combined = [], {}, []
        base_metrics = base["models"] if base else {}
        base_ious = [m["metrics"]["occupied_iou"] for m in base_metrics.values() if m["metrics"]["occupied_iou"] is not None]
        best_baseline = max(base_ious) if base_ious else None
        for job in jobs:
            result = job["result"] if job["status"] == "succeeded" else None
            manifest = result["manifest"] if result else {}
            matched = bool(manifest.get("reference_sha256") and
                           manifest["reference_sha256"] == base_manifest.get("reference_sha256"))
            camera = manifest.get("camera", {})
            cost = manifest.get("sensor_cost", {})
            rows.append({"job_id": job["id"], "profile": job["profile"], "status": job["status"], "error": job["error"],
                         "reference_matches_baseline": matched, "sensor_cost": cost, "camera": camera,
                         "models": result["models"] if result else {}})
        for name in spec["model_ids"]:
            eligible = []
            base_iou = base_metrics.get(name, {}).get("metrics", {}).get("occupied_iou")
            keys = ["lidar_payload_bytes"] if name == "occupancy_lidar" else ["radar_payload_bytes"]
            if name == "occupancy_lidar_radar":
                keys = ["lidar_payload_bytes", "radar_payload_bytes"]
            for row in rows:
                iou = row["models"].get(name, {}).get("metrics", {}).get("occupied_iou")
                cost = row["sensor_cost"]
                if (row["reference_matches_baseline"] and iou is not None and base_iou is not None
                        and iou >= spec.get("min_occupied_iou", 0.3)
                        and base_iou - iou <= spec["max_iou_drop"] and all(k in cost for k in keys)):
                    payload = sum(cost[k] for k in keys)
                    entry = {"profile": row["profile"], "model": name, "occupied_iou": iou,
                             "iou_drop": base_iou - iou, "payload_bytes_per_frame": payload, "job_id": row["job_id"]}
                    eligible.append(entry)
                    if best_baseline - iou <= spec["max_iou_drop"]:
                        combined.append(entry)
            eligible.sort(key=lambda r: (r["payload_bytes_per_frame"], -r["occupied_iou"], r["profile"]))
            choices[name] = eligible[0] if eligible else None
        combined.sort(key=lambda r: (r["payload_bytes_per_frame"], -r["occupied_iou"], r["model"], r["profile"]))
        camera_eligible = []
        camera_mode = base_manifest.get("camera", {}).get("mode", "unavailable")
        for row in rows:
            camera, cost = row["camera"], row["sensor_cost"]
            if not row["reference_matches_baseline"] or camera.get("mean_psnr_db", 0) < spec["min_camera_psnr_db"]:
                continue
            if camera_mode == "detector_consistency" and (camera.get("detection_retention") is None or
                    camera["detection_retention"] < spec["min_detection_retention"]):
                continue
            if "camera_encoded_bytes" in cost:
                camera_eligible.append({"profile": row["profile"], "job_id": row["job_id"],
                    "encoded_bytes_per_frame": cost["camera_encoded_bytes"], "mean_psnr_db": camera["mean_psnr_db"],
                    "detection_retention": camera.get("detection_retention")})
        camera_eligible.sort(key=lambda r: (r["encoded_bytes_per_frame"], -r["mean_psnr_db"], r["profile"]))
        environments.append({"environment": index, "scenario": scenario, "trials": rows,
            "model_choices": choices, "provisional_selected": combined[0] if combined else None,
            "camera_evaluation_mode": camera_mode, "camera_choice": camera_eligible[0] if camera_eligible else None})
    return {"study_id": study["id"], "source": "dataset_replay", "environments": environments,
        "criterion": "Minimize relevant input payload above minimum IoU and within IoU drop of best baseline model; fixed reference",
        "limitations": ["Selections are provisional on recorded frames, not new sensor hardware recommendations",
            "Camera choice is separate: image fidelity or detector consistency, not GT detection accuracy or fusion",
            "No physical weather, sensor relocation, increased range/resolution, or training is simulated",
            "Byte counts exclude electricity, purchase price, network overhead and inference compute cost",
            "mini-val is small; model comparison needs held-out data, label review and more environments"]}
