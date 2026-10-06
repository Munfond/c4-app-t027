"""Bounded real function tools: create study, read results, compare, then explain.

Four LLM requests per study at most in the normal flow; polling is deterministic code.
No simulator or shell commands execute inside the LLM request handler.
"""

import json

import httpx

from src.agents.experiment_agent import strict_schema
from src.config import get_settings
from src.models.experiments import SensorStudySpec
from src.services import sensor_studies as studies


def enabled():
    settings = get_settings()
    if not settings.experiment_agent_enabled or not settings.openai_api_key:
        raise RuntimeError("Set EXPERIMENT_AGENT_ENABLED=true and OPENAI_API_KEY on the server to test the LLM agent")
    return settings


def tool(name, description, schema):
    return {
        "type": "function",
        "function": {"name": name, "description": description, "strict": True, "parameters": strict_schema(schema)},
    }


async def completion(messages, tools=None, choice=None, max_tokens=1800):
    settings = enabled()
    payload = {
        "model": settings.experiment_agent_model,
        "temperature": 0,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if tools:
        payload.update(tools=tools, parallel_tool_calls=False, tool_choice=choice)
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        )
    if response.status_code != 200:
        raise RuntimeError(f"LLM provider HTTP {response.status_code}; inspect account/model/credits, no auto retry")
    data = response.json()
    if data["choices"][0].get("finish_reason") == "length":
        raise ValueError("LLM output truncated; no tool executed")
    return data


def one_call(data, expected):
    message = data["choices"][0]["message"]
    calls = message.get("tool_calls", [])
    if len(calls) != 1 or calls[0]["function"]["name"] != expected:
        raise ValueError("LLM must call exactly the allowed tool")
    call = calls[0]
    arguments = json.loads(call["function"]["arguments"])
    # Preserve only supported assistant fields, not provider-specific metadata.
    assistant = {"role": "assistant", "content": message.get("content"), "tool_calls": calls}
    return assistant, call["id"], arguments


async def start(message):
    enabled()
    system = (
        "Bạn là agent lập thí nghiệm tối ưu lượng dữ liệu LiDAR P-027. Gọi create_sensor_study đúng một lần. "
        "Công cụ thực sự tạo job; worker riêng chạy CARLA. Chỉ occupancy_lidar, không camera/radar model. "
        "Chỉ chỉnh sensor trong miền schema; ưu tiên đổi points_per_second, channels, range_m. "
        "Tạo tối đa 3 environments và 3 profiles; baseline là lidar của từng scenario, được chạy tự động. "
        "Mặc định test nhẹ: Town01, clear, 2 vehicles, 0 pedestrians, 2 frames, seed42, spawn0, "
        "capture_interval0.5, timestep0.05. LiDAR baseline channels32 points600000 range100 "
        "upper_fov10 lower_fov-30 mount_z2 pitch0. Profiles tiết kiệm 300000 và 150000 points/sec nếu "
        "người dùng không chỉ định. max_iou_drop mặc định0.02 là chênh lệch IoU tuyệt đối. "
        "Mưa/sương mù chỉ thay RGB, chưa chứng minh suy giảm LiDAR; không khẳng định mô phỏng vật lý. "
        "Spawn route không phải tuyến cao tốc đã xác minh. Không hứa tiết kiệm điện hoặc chi phí tiền."
    )
    name = "create_sensor_study"
    data = await completion(
        [{"role": "system", "content": system}, {"role": "user", "content": message}],
        [
            tool(
                name,
                "Create a bounded sensor study and enqueue its first CARLA trial",
                SensorStudySpec.model_json_schema(),
            )
        ],
        {"type": "function", "function": {"name": name}},
    )
    _, call_id, arguments = one_call(data, name)
    spec = SensorStudySpec.model_validate(arguments)
    study = studies.create(
        spec,
        {
            "model": data.get("model"),
            "usage": data.get("usage", {}),
            "tool": name,
            "tool_call_id": call_id,
            "request": message,
        },
    )
    return study


async def summarize(ident):
    study = studies.get(ident)
    if study["summary"]:
        return study["summary"]
    if study["status"] != "completed":
        raise ValueError("Study is not completed; poll/advance without calling LLM")
    enabled()
    messages = [
        {
            "role": "system",
            "content": (
                "Bạn đọc báo cáo tối ưu LiDAR. Dùng các tool được chỉ định rồi giải thích bằng tiếng Việt. "
                "Chỉ dùng metrics của tool; không bịa, không đổi lựa chọn provisional_selected của Python. "
                "Nếu reference không khớp hoặc trial lỗi, nêu rõ chưa đủ bằng chứng. Không nói tối ưu điện/tiền "
                "từ byte rate. Nhãn proxy và weather RGB không chứng minh an toàn/robustness thực tế."
            ),
        },
        {"role": "user", "content": f"Đọc và so sánh study {ident}"},
    ]
    schema = {
        "type": "object",
        "properties": {"study_id": {"type": "string"}},
        "required": ["study_id"],
        "additionalProperties": False,
    }
    trace, usage = [], []
    comparison = None
    for name in ("read_sensor_study", "compare_sensor_configs"):
        data = await completion(
            messages,
            [tool(name, "Read measured sensor study results", schema)],
            {"type": "function", "function": {"name": name}},
            max_tokens=200,
        )
        assistant, call_id, arguments = one_call(data, name)
        if arguments != {"study_id": ident}:
            raise ValueError("Tool may only access the requested study")
        if name == "read_sensor_study":
            fresh = studies.get(ident)
            output = {
                "id": ident,
                "status": fresh["status"],
                "checkpoint_sha256": fresh["checkpoint_sha256"],
                "jobs": [
                    {key: job[key] for key in ("id", "environment", "profile", "status", "error")}
                    for job in fresh["jobs"]
                ],
            }
        else:
            comparison = studies.comparison(ident)
            output = comparison
        messages += [
            assistant,
            {"role": "tool", "tool_call_id": call_id, "content": json.dumps(output, ensure_ascii=False)},
        ]
        trace.append({"tool": name, "tool_call_id": call_id})
        usage.append(data.get("usage", {}))
    data = await completion(messages, max_tokens=700)
    message = data["choices"][0]["message"]
    if message.get("tool_calls") or not message.get("content"):
        raise ValueError("Expected final explanation, no further tools")
    summary = {
        "comparison": comparison,
        "explanation": message["content"],
        "tool_trace": trace,
        "usage": usage + [data.get("usage", {})],
        "model": data.get("model"),
    }
    studies.save_summary(ident, summary)
    return summary
