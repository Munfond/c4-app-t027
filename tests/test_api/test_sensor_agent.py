import json

import httpx
import pytest

from src.agents import sensor_agent
from src.config import PROJECT_ROOT, Settings
from src.models.experiments import ExperimentSpec, LidarSpec, SensorStudySpec
from src.services import experiment_store as store
from src.services import sensor_studies as studies


@pytest.fixture
def sensor_settings(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, experiment_root=tmp_path, lab_data_root=PROJECT_ROOT / "data/lab")
    for module in ("src.services.experiment_store", "src.services.experiment_registry", "src.agents.sensor_agent"):
        monkeypatch.setattr(f"{module}.get_settings", lambda: settings)
    return settings


def spec():
    return SensorStudySpec(
        scenarios=[{"map": "Town01", "vehicles": 2, "pedestrians": 0, "frames": 2}],
        profiles=[{"name": "half", "lidar": {"points_per_second": 300000}}],
    )


def finish_trial(result, status="succeeded"):
    job = store.claim("test-worker")
    assert job is not None
    store.finish(job["id"], "test-worker", status, result=result, error="sensor failed" if status == "failed" else None)


def result(iou=0.5, rate=1000, reference="paired-reference"):
    return {
        "manifest": {"reference_sha256": reference, "sensor_cost": {"estimated_lidar_bytes_per_second": rate}},
        "models": {"occupancy_lidar": {"metrics": {"occupied_iou": iou, "latency_model_only_ms": None}}},
    }


def completed(sensor_settings, candidate=None):
    study = studies.create(spec())
    finish_trial(result())
    studies.advance(study["id"])
    finish_trial(candidate or result(iou=0.49, rate=500))
    return studies.get(study["id"])


def test_sensor_bounds_and_nuscenes_contract(sensor_settings):
    with pytest.raises(ValueError):
        LidarSpec(channels=1000)
    with pytest.raises(ValueError):
        LidarSpec(lower_fov=0, upper_fov=-1)
    with pytest.raises(ValueError):
        SensorStudySpec(scenarios=[{"frames": 81}], profiles=spec().profiles)
    with pytest.raises(ValueError, match="require CARLA"):
        store.create(ExperimentSpec(source="nuscenes", scene_id="scene-0103", scenario={"lidar": {"channels": 16}}))


def test_study_only_enqueues_one_trial_and_advance_is_idempotent(sensor_settings):
    study = studies.create(spec())
    assert len(store.recent()) == 1
    assert studies.advance(study["id"])["jobs"][0]["id"] == study["jobs"][0]["id"]
    first = store.get(study["jobs"][0]["id"])["spec"]["request"]["scenario"]["lidar"]
    assert first["points_per_second"] == 600000
    finish_trial(result())
    advanced = studies.advance(study["id"])
    assert len(advanced["jobs"]) == 2
    second = store.get(advanced["jobs"][1]["id"])["spec"]["request"]["scenario"]["lidar"]
    assert second["points_per_second"] == 300000
    assert len(studies.advance(study["id"])["jobs"]) == 2


def test_cancellation_prevents_further_trials(sensor_settings):
    study = studies.create(spec())
    assert studies.cancel(study["id"])["status"] == "cancelled"
    assert studies.advance(study["id"])["jobs"][0]["status"] == "cancelled"
    assert len(store.recent()) == 1


def test_comparison_requires_quality_and_identical_reference(sensor_settings):
    study = completed(sensor_settings)
    report = studies.comparison(study["id"])["environments"][0]
    assert report["provisional_selected"] == "half"
    assert report["trials"][1]["data_reduction_fraction"] == 0.5
    mismatched = completed(sensor_settings, result(iou=0.99, rate=100, reference="different-world"))
    report = studies.comparison(mismatched["id"])["environments"][0]
    assert not report["trials"][1]["reference_matches_baseline"]
    assert report["provisional_selected"] == "baseline"
    degraded = completed(sensor_settings, result(iou=0.1, rate=100))
    assert studies.comparison(degraded["id"])["environments"][0]["provisional_selected"] == "baseline"


def test_failed_baseline_never_recommends_candidate(sensor_settings):
    study = studies.create(spec())
    finish_trial(None, "failed")
    studies.advance(study["id"])
    finish_trial(result(iou=0.9, rate=100))
    assert studies.comparison(study["id"])["environments"][0]["provisional_selected"] is None


@pytest.mark.asyncio
async def test_disabled_agent_does_not_create_study(client, sensor_settings):
    response = await client.post("/api/v1/experiments/sensor-agent/start", json={"message": "Thử LiDAR"})
    assert response.status_code == 503
    assert store.recent() == []


def tool_response(name, arguments):
    return {
        "model": "mock-provider",
        "usage": {"total_tokens": 10},
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"call_{name}",
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(arguments)},
                        }
                    ],
                },
            }
        ],
    }


@pytest.mark.asyncio
async def test_real_tool_dispatch_and_summary_cache(sensor_settings, monkeypatch):
    sensor_settings.experiment_agent_enabled = True
    sensor_settings.openai_api_key = "mock-key-never-sent"
    requests = []

    def provider(request):
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer mock-key-never-sent"
        payload = json.loads(request.content)
        messages, tools = payload["messages"], payload.get("tools")
        requests.append(payload)
        if tools:
            function = tools[0]["function"]
            name = function["name"]
            assert function["strict"] is True
            assert function["parameters"]["additionalProperties"] is False
            assert payload["parallel_tool_calls"] is False
            assert payload["tool_choice"]["function"]["name"] == name
            arguments = spec().model_dump() if name == "create_sensor_study" else {"study_id": study_id}
            return httpx.Response(200, json=tool_response(name, arguments))
        assert [item["role"] for item in messages].count("tool") == 2
        assert payload["max_tokens"] == 1400
        assert "180 từ" in messages[0]["content"]
        return httpx.Response(200, json={
            "model": "mock-provider",
            "usage": {},
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "Kết quả thử nghiệm: giảm lượng dữ liệu, chưa chứng minh tiết kiệm điện."},
                }
            ],
        })

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        sensor_agent.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(provider), **kwargs),
    )
    study = await sensor_agent.start("Thử cấu hình LiDAR")
    study_id = study["id"]
    assert len(store.recent()) == 1  # Real dispatcher wrote queue; provider alone is mocked.
    finish_trial(result())
    studies.advance(study_id)
    finish_trial(result(iou=0.49, rate=500))
    summary = await sensor_agent.summarize(study_id)
    assert summary["comparison"]["environments"][0]["provisional_selected"] == "half"
    assert [row["tool"] for row in summary["tool_trace"]] == ["read_sensor_study", "compare_sensor_configs"]
    assert len(requests) == 4
    assert await sensor_agent.summarize(study_id) == summary
    assert len(requests) == 4


@pytest.mark.asyncio
async def test_agent_rejects_unexpected_tool_without_side_effects(sensor_settings, monkeypatch):
    sensor_settings.experiment_agent_enabled = True
    sensor_settings.openai_api_key = "mock-key-never-sent"

    async def fake_completion(*args, **kwargs):
        return tool_response("execute_shell", {"command": "ignored"})

    monkeypatch.setattr(sensor_agent, "completion", fake_completion)
    with pytest.raises(ValueError, match="allowed tool"):
        await sensor_agent.start("test")
    assert store.recent() == []
