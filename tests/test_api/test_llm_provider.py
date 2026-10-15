import httpx
import pytest

from src.agents import experiment_agent, sensor_agent
from src.config import Settings


@pytest.mark.parametrize("provider,key,url", [
    ("openai", "openai-test", "https://api.openai.com/v1"),
    ("openrouter", "router-test", "https://openrouter.ai/api/v1"),
])
def test_provider_binds_only_its_own_key(provider, key, url):
    settings = Settings(_env_file=None, llm_provider=provider,
                        openai_api_key="openai-test", openrouter_api_key="router-test")
    assert settings.llm_api_key == key and settings.llm_base_url == url


def test_missing_router_key_never_falls_back_to_openai(monkeypatch):
    settings = Settings(_env_file=None, llm_provider="openrouter", openai_api_key="other-key",
                        experiment_agent_enabled=True)
    monkeypatch.setattr(sensor_agent, "get_settings", lambda: settings)
    assert settings.llm_api_key == ""
    with pytest.raises(RuntimeError, match="selected provider"):
        sensor_agent.enabled()


@pytest.mark.asyncio
@pytest.mark.parametrize("planner", [False, True])
async def test_agent_uses_router_host_and_never_sends_other_key(monkeypatch, planner):
    settings = Settings(_env_file=None, llm_provider="openrouter", openrouter_api_key="router-test",
                        openai_api_key="do-not-send", experiment_agent_enabled=True,
                        experiment_agent_model="openai/gpt-4o-mini")
    module = experiment_agent if planner else sensor_agent
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(experiment_agent, "registry", lambda: [])
    called = []

    def respond(request):
        called.append(request)
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer router-test"
        assert b"do-not-send" not in request.content
        return httpx.Response(200, json={"model": "openai/gpt-4o-mini", "usage": {}, "choices": [
            {"finish_reason": "tool_calls", "message": {"content": None, "tool_calls": [
                {"id": "call-test", "type": "function", "function": {
                    "name": "draft_experiment", "arguments": "{}"}}
            ]}}
        ]})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **kw: client_type(
        transport=httpx.MockTransport(respond), **kw))
    if planner:
        await experiment_agent.draft({"message": "Draft only"})
    else:
        await sensor_agent.completion([{"role": "user", "content": "Test"}])
    assert len(called) == 1


def test_langchain_uses_the_same_provider(monkeypatch):
    # The web/CI runtime uses HTTP directly; LangChain is an optional extra.
    pytest.importorskip("langchain_openai")
    from src.services import llm
    settings = Settings(_env_file=None, llm_provider="openrouter", openrouter_api_key="router-test")
    monkeypatch.setattr(llm, "get_settings", lambda: settings)
    monkeypatch.setattr(llm, "ChatOpenAI", lambda **kwargs: kwargs)
    result = llm.get_llm()
    assert result["api_key"] == "router-test"
    assert result["base_url"] == "https://openrouter.ai/api/v1"
