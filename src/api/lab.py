from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from src.config import get_settings
from src.models.lab import DetectionFrame, FrameList, ModelList, SceneList
from src.services import lab
from src.services.anonymizer import InvalidImageError, UnavailableAnonymizerError, anonymize_bytes

router = APIRouter(prefix="/lab", tags=["lab"])


def available(call, *args):
    try:
        return call(*args)
    except FileNotFoundError as exc:
        raise HTTPException(503, "Required dataset/artifact is not installed") from exc


@router.get("/capabilities")
def capabilities():
    settings = get_settings()
    raw = (settings.nusc_root / "v1.0-mini/sample_data.json").is_file()
    return {
        "schema_version": "1.0",
        "frame_catalog": (settings.lab_data_root / "exports/L3E/samples.csv").is_file(),
        "raw_metadata_present": raw,
        "anonymizer_enabled": settings.anonymizer_enabled,
        "plate_weights_present": settings.plate_weights.is_file(),
        "camera_policy": "processed-only; returns 503 if anonymizer unavailable",
        "live_inference": False,
        "matlab_live": False,
        "models": lab.models(),
        "coordinates": lab.COORDINATES,
    }


@router.get("/models", response_model=ModelList)
def models():
    return {
        "items": lab.models(),
        "limitations": [
            "mini_val: 81 frames, 2 scenes; not full nuScenes benchmark",
            "Official/mixed results overlap pretraining data",
            "Hybrid fusion is object-level late fusion",
        ],
    }


@router.get("/scenes", response_model=SceneList)
def scenes():
    items = available(lab.frames)
    names = sorted({item["scene"] for item in items})
    return {
        "items": [
            {"id": name, "split": "mini_val", "frame_count": sum(f["scene"] == name for f in items)} for name in names
        ]
    }


@router.get("/scenes/{scene_id}/frames", response_model=FrameList)
def scene_frames(scene_id: str):
    items = [item for item in available(lab.frames) if item["scene"] == scene_id]
    if not items:
        raise HTTPException(404, "Scene not found")
    return {"items": items}


@router.get("/frames/{token}/detections", response_model=DetectionFrame)
def detections(token: str, model: str = "our_lidar", threshold: float = Query(0.3, ge=0, le=1)):
    if model not in lab.DETECTORS:
        raise HTTPException(422, "Unknown model")
    try:
        return available(lab.detections, token, model, threshold)
    except KeyError as exc:
        raise HTTPException(404, "Frame not found") from exc


@router.get("/frames/{token}/cameras/{channel}")
def camera(token: str, channel: str):
    if channel not in lab.CAMERAS:
        raise HTTPException(422, "Unknown camera channel")
    if available(lab.frame, token) is None:
        raise HTTPException(404, "Frame not found")
    try:
        path = available(lab.camera_path, token, channel)
        if path.stat().st_size > get_settings().max_upload_bytes:
            raise HTTPException(413, "Camera image exceeds size limit")
        result = anonymize_bytes(path.read_bytes())
    except FileNotFoundError as exc:
        raise HTTPException(503, "Camera file missing") from exc
    except KeyError as exc:
        raise HTTPException(404, "Camera frame not found") from exc
    except (InvalidImageError, UnavailableAnonymizerError, ValueError) as exc:
        raise HTTPException(503, "Processed camera image unavailable") from exc
    return Response(result, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/benchmarks")
def benchmarks():
    root = get_settings().lab_data_root
    sources = {
        "detection": "models/our_bevfusion_mini/metrics.json",
        "occupancy": "models/occupancy/metrics.json",
        "flow": "models/temporal_flow/metrics.json",
        "risk": "stage_h/results/risk_metrics.json",
    }
    return {
        "split": "mini_val",
        "frame_count": 81,
        "sections": {
            name: {
                "available": (root / rel).is_file(),
                "source": rel,
                "data": lab.json_data(root / rel) if (root / rel).is_file() else None,
            }
            for name, rel in sources.items()
        },
        "limitations": [
            "Static occupancy uses pseudo-GT",
            "Learned flow quality insufficient",
            "Risk is an uncalibrated score, not collision probability",
            "Runtime measurements use different hardware",
        ],
    }
