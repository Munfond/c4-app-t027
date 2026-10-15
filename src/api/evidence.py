"""Public read-only simulator evidence. Interactive experiment guards remain separate."""

from fastapi import APIRouter, Request

from src.api import experiments
from src.config import get_settings

router = APIRouter(prefix="/evidence", tags=["recorded-evidence"])


@router.get("/capabilities")
def capabilities(request: Request):
    settings = get_settings()
    from src.services.experiment_auth import operator_authenticated

    return {
        "execution_mode": settings.experiment_execution_mode,
        "access_required": bool(settings.experiment_access_token) or settings.experiment_execution_mode == "remote",
        "authenticated": operator_authenticated(request),
        "interactive_enabled": settings.app_env != "production" or settings.experiment_api_enabled_in_production,
        "playback_only": settings.app_env == "production" and not settings.experiment_api_enabled_in_production,
        "notice": "Recorded simulator output; not a live CARLA server or a real-world safety guarantee",
    }


# Reuse the bounded readers and integrity/error handling. Only these GET routes
# are available without the production opt-in; no job, review or LLM endpoint.
for path, endpoint in (
    ("/native-online", experiments.native_online_catalog),
    ("/native-online/{run}/report", experiments.native_online_report),
    ("/native-online/{run}/predictions/occupancy_lidar/{index}", experiments.native_online_prediction),
    ("/native-online/{run}/reference/{index}", experiments.native_online_reference),
    ("/native-online/{run}/camera", experiments.native_online_camera),
    ("/native-rl", experiments.native_rl_report),
    ("/native-rl/report", experiments.native_rl_download),
):
    router.add_api_route(path, endpoint, methods=["GET"])
