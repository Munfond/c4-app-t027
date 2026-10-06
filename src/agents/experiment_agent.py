"""One bounded LLM tool call to draft a plan. Execution is a separate explicit API action."""

import json

import httpx
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from src.config import get_settings
from src.models.experiments import ExperimentSpec
from src.services.experiment_registry import registry, validate_spec


class PlanState(TypedDict, total=False):
    message: str
    spec: dict
    usage: dict
    provider_model: str


def strict_schema(value):
    if isinstance(value, dict):
        value = {key: strict_schema(item) for key, item in value.items() if key != "default"}
        if value.get("type") == "object":
            value["additionalProperties"] = False
            value["required"] = list(value.get("properties", {}))
        return value
    if isinstance(value, list):
        return [strict_schema(item) for item in value]
    return value


async def draft(state):
    settings = get_settings()
    if not settings.experiment_agent_enabled or not settings.openai_api_key:
        raise RuntimeError("Agent disabled or OPENAI_API_KEY missing; use the experiment form/API")
    system = (
        "You draft bounded perception experiments for P-027 in Vietnamese. Call draft_experiment once. "
        "Do not invent model IDs, paths, maps, metrics or capabilities. CARLA only supports occupancy_lidar. "
        "nuScenes supports all registry models, requires scene-0103 or scene-0916; CARLA weather/actor settings "
        "do not alter nuScenes. Current models consume LiDAR/radar, never camera. "
        "For a new CARLA capture set capture_id and scene_id null; defaults: Town03, clear, vehicles=8, "
        "pedestrians=8, seed=42, frames=4, capture_interval=0.5, timestep=0.05, route_spawn_index=0. "
        "max_latency_ms must be null unless user specified. Map/spawn-index autopilot is not verified highway. "
        "scenario.lidar defaults channels32, points_per_second600000, range_m100, upper_fov10, "
        "lower_fov-30, mount_z2, pitch0. Sensor changes only apply to CARLA. "
        "This call only proposes a spec; it never starts a job. Available registry: "
        + json.dumps(registry(), ensure_ascii=False)
    )
    payload = {
        "model": settings.experiment_agent_model,
        "temperature": 0,
        "max_tokens": 700,
        "parallel_tool_calls": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": state["message"]}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "draft_experiment",
                    "description": "Draft an experiment for server-side validation; never execute.",
                    "strict": True,
                    "parameters": strict_schema(ExperimentSpec.model_json_schema()),
                },
            }
        ],
        "tool_choice": {"type": "function", "function": {"name": "draft_experiment"}},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        )
    if response.status_code != 200:
        raise RuntimeError(f"LLM provider returned HTTP {response.status_code}; no experiment was created")
    data = response.json()
    calls = data["choices"][0]["message"].get("tool_calls", [])
    if len(calls) != 1 or calls[0]["function"]["name"] != "draft_experiment":
        raise ValueError("Provider did not return exactly one draft_experiment call")
    return {
        "spec": json.loads(calls[0]["function"]["arguments"]),
        "usage": data.get("usage", {}),
        "provider_model": data.get("model", settings.experiment_agent_model),
    }


def validate(state):
    spec = ExperimentSpec.model_validate(state["spec"])
    validate_spec(spec)
    return {"spec": spec.model_dump()}


def build_planner():
    graph = StateGraph(PlanState)
    graph.add_node("draft", draft)
    graph.add_node("validate", validate)
    graph.set_entry_point("draft")
    graph.add_edge("draft", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


planner = build_planner()
