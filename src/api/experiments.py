import importlib.util
import json
from typing import Annotated, Literal
from zipfile import BadZipFile

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse

from src.config import get_settings
from src.models.experiments import AgentPlanRequest, EngineerReview, ExperimentSpec, SensorAgentRequest, SensorStudySpec
from src.models.replay import CAMERAS, OCCUPANCY_MODELS, RADARS, ReplayStudySpec
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


async def session_scope(request: Request):
    from src.services import experiment_sessions as sessions

    ident = request.headers.get("x-experiment-session") or request.query_params.get("session")
    if not ident:
        yield
        return
    try:
        root = sessions.acquire(ident)
    except (KeyError, ValueError) as exc:
        raise HTTPException(410, "Phiên đã kết thúc. Hãy bắt đầu phiên mới.") from exc
    try:
        with store.scope(root):
            yield
    finally:
        sessions.release(ident)


router = APIRouter(
    prefix="/experiments",
    tags=["experiments"],
    dependencies=[Depends(require_experiment_access), Depends(session_scope)],
)
ExperimentId = Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")]


@router.post("/sessions", status_code=201)
def create_session():
    from src.services.experiment_sessions import create

    return create()


@router.post("/sessions/{ident}/touch")
def touch_session(ident: ExperimentId):
    from src.services.experiment_sessions import touch

    try:
        touch(ident)
    except KeyError as exc:
        raise HTTPException(410, "Session expired or ended") from exc
    return {"active": True}


@router.post("/sessions/{ident}/suspend")
def suspend_session(ident: ExperimentId):
    from src.services.experiment_sessions import suspend

    suspend(ident)
    return {"active": False}


@router.post("/sessions/{ident}/end")
def end_session(ident: ExperimentId):
    from src.services.experiment_sessions import end

    end(ident)
    return {"ended": True}


@router.get("/runtime")
def experiment_runtime():
    from src.services.carla_runtime import snapshot

    return snapshot()


@router.get("/registry")
def experiment_registry():
    from src.inference.native_input import catalog

    settings = get_settings()
    return {
        "models": registry(),
        "native_input_adapters": catalog(),
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
def experiments(include_research: bool = False):
    return {"items": store.recent(include_research=include_research)}


@router.post("/sensor-agent/studies", status_code=201)
def create_native_study(spec: SensorStudySpec):
    try:
        # Validate before inserting a study; unavailable adapters must not create orphan records.
        for trial in studies.trials(spec):
            validate_spec(trial["spec"])
        return studies.create(
            spec, metadata={"request": "Manual measured sensor study; no LLM call", "llm_called": False}
        )
    except (ValueError, OSError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


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


@router.get("/replay/catalog")
def replay_catalog():
    from src.services.dataset_replay import catalog

    return catalog() | {"cameras": CAMERAS, "radars": RADARS, "models": OCCUPANCY_MODELS}


@router.get("/detector-pilot")
def detector_pilot(pilot: Literal["short", "sparse60"] = "short"):
    from src.services.detector_pilot_evidence import snapshot

    try:
        return snapshot(pilot)
    except FileNotFoundError:
        return {"available": False, "notice": "Detector pilot evidence is not packaged on this server"}
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, "Detector evidence integrity check failed") from exc


@router.get("/detector-pilot/artifacts/{name:path}")
def detector_pilot_artifact(name: str, pilot: Literal["short", "sparse60"] = "short"):
    from src.services.detector_pilot_evidence import artifact

    try:
        return FileResponse(artifact(name, pilot), filename=name.rsplit("/", 1)[-1])
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(404, "Evidence artifact not found") from exc
    except ValueError as exc:
        raise HTTPException(409, "Detector evidence integrity check failed") from exc


@router.get("/detector-pilot/reviews")
def detector_pilot_reviews(pilot: Literal["short", "sparse60"] = "short"):
    from src.services.detector_pilot_evidence import reviews

    try:
        return {"items": reviews(pilot)}
    except FileNotFoundError as exc:
        raise HTTPException(404, "Detector evidence is unavailable") from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, "Detector evidence integrity check failed") from exc


@router.post("/detector-pilot/reviews", status_code=201)
def review_detector_pilot(request: EngineerReview, pilot: Literal["short", "sparse60"] = "short"):
    from src.services.detector_pilot_evidence import save_review

    try:
        return save_review(request, pilot)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Detector evidence is unavailable") from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/replay/studies", status_code=201)
def create_replay_study(spec: ReplayStudySpec):
    try:
        return studies.create(spec)
    except (ValueError, FileNotFoundError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/replay/studies")
def replay_studies():
    return {"items": [s for s in studies.recent() if s["source"] == "dataset_replay"]}


@router.post("/replay/agent/start", status_code=201)
async def start_replay_agent(request: AgentPlanRequest):
    from src.agents.replay_agent import start

    try:
        return await start(request.message)
    except (RuntimeError, httpx.HTTPError) as exc:
        raise HTTPException(503, str(exc)) from exc
    except (ValueError, FileNotFoundError, KeyError, IndexError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/sensor-agent/{ident}/comparison")
def compare_study(ident: ExperimentId):
    try:
        return studies.comparison(ident)
    except KeyError as exc:
        raise HTTPException(404, "Sensor study not found") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/sensor-agent/{ident}/evidence")
def study_evidence(ident: ExperimentId):
    from src.services.agent_evidence import evidence

    try:
        return evidence(ident)
    except KeyError as exc:
        raise HTTPException(404, "Study not found") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/sensor-agent/{ident}/reviews")
def study_reviews(ident: ExperimentId):
    from src.services.agent_evidence import reviews

    try:
        return {"items": reviews(ident)}
    except KeyError as exc:
        raise HTTPException(404, "Study not found") from exc


@router.post("/sensor-agent/{ident}/reviews", status_code=201)
def review_study(ident: ExperimentId, request: EngineerReview):
    from src.services.agent_evidence import save_review

    try:
        return save_review(ident, request)
    except KeyError as exc:
        raise HTTPException(404, "Study not found") from exc
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


@router.get("/native-profile-pilot")
def native_profile_pilot():
    from src.services.native_profile_evidence import read_report

    try:
        return read_report()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Native profile evidence unavailable or failed integrity check") from exc


@router.get("/native-profile-pilot/report")
def native_profile_pilot_report():
    snapshot = native_profile_pilot()
    if not snapshot["ready"]:
        raise HTTPException(404, snapshot["notice"])
    return FileResponse(
        get_settings().native_profile_pilot_report,
        media_type="application/json",
        filename="native-12-profile-audit.json",
    )


@router.get("/native-online")
def native_online_catalog():
    from src.services.native_online_evidence import catalog

    return catalog()


@router.get("/native-online/{run}/report")
def native_online_report(run: str):
    from src.services.native_online_evidence import snapshot

    try:
        return snapshot(run)
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(404, "Completed online capture unavailable") from exc
    except (OSError, ValueError, TypeError) as exc:
        raise HTTPException(503, "Online capture evidence failed integrity checks") from exc


@router.get("/native-online/{run}/predictions/occupancy_lidar/{index}")
def native_online_prediction(run: str, index: int = Path(ge=0, le=19)):
    from src.services.native_online_evidence import frame_prediction

    native_online_report(run)
    try:
        return frame_prediction(run, index)
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(404, "Online frame unavailable") from exc
    except (OSError, ValueError, TypeError, EOFError, BadZipFile) as exc:
        raise HTTPException(503, "Online frame failed integrity checks") from exc


@router.get("/native-online/{run}/reference/{index}")
def native_online_reference(run: str, index: int = Path(ge=0, le=19)):
    from src.services.capture_reference import read_reference
    from src.services.native_online_evidence import artifact

    native_online_report(run)
    try:
        artifact(run, index, "json")  # Bind optional actor geometry too.
        return read_reference(artifact(run, index, "npz"))
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(404, "Online reference unavailable") from exc
    except (OSError, ValueError, TypeError) as exc:
        raise HTTPException(503, "Online reference failed integrity checks") from exc


@router.get("/native-online/{run}/camera")
def native_online_camera(run: str, index: int = Query(default=0, ge=0, le=19)):
    from src.services.native_online_evidence import artifact

    native_online_report(run)
    try:
        return FileResponse(artifact(run, index, "png"), media_type="image/png")
    except (FileNotFoundError, KeyError) as exc:
        raise HTTPException(404, "Online camera unavailable") from exc
    except (OSError, ValueError, TypeError) as exc:
        raise HTTPException(503, "Online camera failed integrity checks") from exc


@router.get("/native-rl")
def native_rl_report():
    from src.services.native_rl_evidence import read_report

    try:
        return read_report()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Native RL evidence chưa qua kiểm tra toàn vẹn") from exc


@router.get("/native-rl/report")
def native_rl_download():
    from src.services.native_rl_evidence import report_path

    value = native_rl_report()
    if not value["ready"]:
        raise HTTPException(404, "Chưa có báo cáo native PPO hoàn tất")
    return FileResponse(report_path(), media_type="application/json", filename="native-occupancy-ppo-report.json")


@router.get("/native-rl/reviews")
def native_rl_reviews():
    from src.services.occupancy_rl_evidence import list_reviews

    return {"items": list_reviews(evidence=native_rl_report(), root=get_settings().native_rl_root)}


@router.post("/native-rl/reviews")
def review_native_rl(body: EngineerReview):
    from src.services.occupancy_rl_evidence import add_review

    snapshot = native_rl_report()
    try:
        return add_review(body, evidence=snapshot, root=get_settings().native_rl_root)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/occupancy-rl")
def occupancy_rl_report():
    from src.services.occupancy_rl_evidence import read_report

    try:
        return read_report()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Báo cáo RL chưa qua kiểm tra toàn vẹn") from exc


@router.get("/occupancy-rl/report")
def download_occupancy_rl_report():
    from src.services.occupancy_rl_evidence import read_report, report_path

    try:
        if not read_report()["ready"]:
            raise HTTPException(404, "Chưa có báo cáo")
        return FileResponse(report_path(), media_type="application/json", filename="p027-occupancy-rl-report.json")
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Báo cáo RL chưa qua kiểm tra toàn vẹn") from exc


@router.get("/occupancy-rl/reviews")
def occupancy_rl_reviews():
    from src.services.occupancy_rl_evidence import list_reviews

    try:
        return {"items": list_reviews()}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise HTTPException(503, "Báo cáo RL chưa qua kiểm tra toàn vẹn") from exc


@router.post("/occupancy-rl/reviews")
def review_occupancy_rl(body: EngineerReview):
    from src.services.occupancy_rl_evidence import add_review

    try:
        return add_review(body)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


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
    path = store.root() / ident / "predictions" / model_id / f"{index:04d}.json"
    if not path.is_file():
        raise HTTPException(404, "Prediction not yet available")
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/{ident}/camera")
def capture_camera(
    ident: ExperimentId,
    index: int = Query(default=0, ge=0, le=80),
    channel: str = Query(default="CAM_FRONT"),
    reference: bool = False,
):
    job = experiment(ident)
    spec = job["spec"]["request"]
    if spec["source"] == "dataset_replay":
        if channel not in spec["replay"]["cameras"]:
            raise HTTPException(404, "Camera not in replay")
        suffix = "_reference" if reference else ""
        path = store.root() / ident / "capture" / f"{index:04d}_{channel}{suffix}.jpg"
        if not path.is_file():
            raise HTTPException(404, "Camera preview not yet available")
        return FileResponse(path, media_type="image/jpeg")
    if spec["source"] != "carla":
        raise HTTPException(404, "Use processed nuScenes camera endpoint")
    capture_id = spec.get("capture_id") or ident
    path = store.root() / capture_id / "capture" / f"frame_{index:04d}.png"
    if not path.is_file():
        raise HTTPException(404, "Camera capture not yet available")
    return FileResponse(path, media_type="image/png")


@router.get("/{ident}/reference/{index}")
def capture_reference(ident: ExperimentId, index: int = Path(ge=0, le=80)):
    job = experiment(ident)
    spec = job["spec"]["request"]
    if spec["source"] != "carla" or job["status"] != "succeeded" or not job.get("result"):
        raise HTTPException(404, "Completed native reference not available")
    if index >= len(job["result"]["manifest"]["frames"]):
        raise HTTPException(404, "Reference frame not available")
    capture_id = spec.get("capture_id") or ident
    path = store.root() / capture_id / "capture" / f"frame_{index:04d}.npz"
    from src.services.capture_reference import read_reference

    try:
        return read_reference(path)
    except FileNotFoundError as exc:
        raise HTTPException(404, "Reference was not preserved for this capture") from exc
    except ValueError as exc:
        raise HTTPException(503, "Native reference failed integrity validation") from exc


@router.get("/{ident}/capture/{index}/{kind}")
def capture_artifact(ident: ExperimentId, index: int = Path(ge=0, le=80), kind: str = "npz"):
    job = experiment(ident)
    spec = job["spec"]["request"]
    if spec["source"] != "carla" or kind not in ("npz", "json", "png"):
        raise HTTPException(404, "Capture artifact not found")
    capture_id = spec.get("capture_id") or ident
    path = store.root() / capture_id / "capture" / f"frame_{index:04d}.{kind}"
    if not path.is_file():
        raise HTTPException(404, "Capture artifact not yet available")
    return FileResponse(path, filename=path.name)


@router.get("/{ident}/sensor-preview")
def sensor_preview(ident: ExperimentId, index: int = Query(default=0, ge=0, le=19)):
    """Bounded visualization from actual captured inputs; never re-run inference."""
    import numpy as np

    job = experiment(ident)
    if job["spec"]["request"]["source"] != "dataset_replay":
        raise HTTPException(422, "Sensor preview currently supports dataset replay")
    path = store.root() / ident / "capture" / f"{index:04d}.npz"
    if not path.is_file() or not job.get("result"):
        raise HTTPException(404, "Sensor preview not yet available")
    manifest = job["result"]["manifest"]
    if index >= len(manifest["frames"]):
        raise HTTPException(404, "Frame not available")
    with np.load(path, allow_pickle=False) as data:
        output = {}
        for name, key in (("lidar", "points"), ("radar", "radar_points")):
            points = data[key]
            indices = np.linspace(0, len(points) - 1, min(len(points), 6000), dtype=int)
            selected = points[indices]
            finite = np.isfinite(selected).all(axis=1)
            rows = selected[finite].tolist()
            output[name] = {"count": len(points), "displayed": len(rows), "points": rows}
            if name == "radar":
                output[name]["speed"] = np.nan_to_num(data["radar_speed"][indices][finite]).tolist()
                output[name]["rcs"] = np.nan_to_num(data["radar_rcs"][indices][finite]).tolist()
    return {
        "frame_id": manifest["frames"][index]["id"],
        "index": index,
        "profile": manifest["replay"]["profile"],
        "sensors": output,
        "camera": [row for row in manifest["camera"]["rows"] if row["frame"] == index],
        "note": "BEV ego coordinates: forward up, left left; display capped at 6000 points per sensor",
    }
