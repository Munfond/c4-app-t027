import importlib.util
import json
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query
from fastapi.responses import FileResponse

from src.config import get_settings
from src.models.experiments import AgentPlanRequest, ExperimentSpec, SensorAgentRequest
from src.services import experiment_store as store
from src.services import sensor_studies as studies
from src.services.experiment_registry import MODELS, registry, validate_spec
from src.simulation.carla_bridge import client_available


def require_experiment_access():
    settings = get_settings()
    if settings.app_env == "production" and not settings.experiment_api_enabled_in_production:
        raise HTTPException(
            503, "Experiments are opt-in in production; configure access control and writable storage first"
        )


router = APIRouter(prefix="/experiments", tags=["experiments"], dependencies=[Depends(require_experiment_access)])
ExperimentId = Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")]


@router.get("/registry")
def experiment_registry():
    settings = get_settings()
    return {
        "models": registry(),
        "carla_client_installed": client_available(settings),
        "torch_installed": importlib.util.find_spec("torch") is not None,
        "agent_enabled": settings.experiment_agent_enabled and bool(settings.openai_api_key),
        "agent_model": settings.experiment_agent_model,
        "maps": ["Town01", "Town02", "Town03", "Town04", "Town05"],
        "limitations": ["CARLA server/maps require separate setup", "Only LiDAR occupancy has a CARLA input adapter"],
    }


@router.post("/validate")
def validate_experiment(spec: ExperimentSpec):
    try:
        validate_spec(spec)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"valid": True, "spec": spec.model_dump()}


@router.post("/plan")
async def plan_experiment(request: AgentPlanRequest):
    from src.agents.experiment_agent import planner

    try:
        result = await planner.ainvoke({"message": request.message})
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(503, str(exc)) from exc
    except (ValueError, KeyError, IndexError) as exc:
        raise HTTPException(422, "Agent plan is invalid or incompatible; use the form") from exc
    return {"spec": result["spec"], "usage": result["usage"], "model": result["provider_model"], "executed": False}


@router.post("", status_code=201)
def create_experiment(spec: ExperimentSpec, idempotency_key: Annotated[str | None, Header(max_length=128)] = None):
    try:
        return store.create(spec, idempotency_key)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("")
def experiments():
    return {"items": store.recent()}


@router.post("/sensor-agent/start", status_code=201)
async def start_sensor_agent(request: SensorAgentRequest):
    from src.agents.sensor_agent import start

    try:
        return await start(request.message, max_iou_drop=request.max_iou_drop, frames=request.frames)
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(503, str(exc)) from exc
    except (ValueError, FileNotFoundError, KeyError, IndexError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/sensor-agent")
def recent_sensor_studies():
    return {"items": studies.recent()}


@router.get("/sensor-agent/{ident}/comparison")
def sensor_comparison(ident: ExperimentId):
    try:
        return studies.comparison(ident)
    except KeyError as exc:
        raise HTTPException(404, "Sensor study not found") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/sensor-agent/{ident}")
def sensor_study(ident: ExperimentId):
    try:
        return studies.get(ident)
    except KeyError as exc:
        raise HTTPException(404, "Sensor study not found") from exc


@router.post("/sensor-agent/{ident}/advance")
def advance_study(ident: ExperimentId):
    try:
        return studies.advance(ident)
    except KeyError as exc:
        raise HTTPException(404, "Sensor study not found") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/sensor-agent/{ident}/cancel")
def cancel_study(ident: ExperimentId):
    try:
        return studies.cancel(ident)
    except KeyError as exc:
        raise HTTPException(404, "Sensor study not found") from exc


@router.post("/sensor-agent/{ident}/summarize")
async def summarize_study(ident: ExperimentId):
    from src.agents.sensor_agent import summarize

    try:
        return await summarize(ident)
    except KeyError as exc:
        raise HTTPException(404, "Sensor study not found") from exc
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(503, str(exc)) from exc
    except (ValueError, IndexError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/{ident}")
def experiment(ident: ExperimentId):
    try:
        return store.get(ident)
    except KeyError as exc:
        raise HTTPException(404, "Experiment not found") from exc


@router.post("/{ident}/cancel")
def cancel_experiment(ident: ExperimentId):
    try:
        return store.cancel(ident)
    except KeyError as exc:
        raise HTTPException(404, "Experiment not found") from exc


@router.get("/{ident}/predictions/{model_id}/{index}")
def prediction(ident: ExperimentId, model_id: str, index: int = Path(ge=0, le=80)):
    job = experiment(ident)
    if model_id not in MODELS or model_id not in job["spec"]["request"]["model_ids"]:
        raise HTTPException(404, "Model not in experiment")
    path = get_settings().experiment_root / ident / "predictions" / model_id / f"{index:04d}.json"
    if not path.is_file():
        raise HTTPException(404, "Prediction not yet available")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/{ident}/camera")
def capture_camera(ident: ExperimentId, index: int = Query(default=0, ge=0, le=80)):
    job = experiment(ident)
    spec = job["spec"]["request"]
    if spec["source"] != "carla":
        raise HTTPException(404, "Use processed nuScenes camera endpoint")
    capture_id = spec.get("capture_id") or ident
    path = get_settings().experiment_root / capture_id / "capture" / f"frame_{index:04d}.png"
    if not path.is_file():
        raise HTTPException(404, "Camera capture not yet available")
    return FileResponse(path, media_type="image/png")


@router.get("/{ident}/capture/{index}/{kind}")
def capture_artifact(ident: ExperimentId, index: int = Path(ge=0, le=80), kind: str = "npz"):
    job = experiment(ident)
    spec = job["spec"]["request"]
    if spec["source"] != "carla" or kind not in ("npz", "json", "png"):
        raise HTTPException(404, "Capture artifact not found")
    capture_id = spec.get("capture_id") or ident
    path = get_settings().experiment_root / capture_id / "capture" / f"frame_{index:04d}.{kind}"
    if not path.is_file():
        raise HTTPException(404, "Capture artifact not yet available")
    return FileResponse(path, filename=path.name)
