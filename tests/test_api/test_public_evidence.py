import pytest

from src.config import Settings


@pytest.mark.asyncio
async def test_production_playback_does_not_enable_mutation_or_llm(client, tmp_path, monkeypatch):
    settings = Settings(_env_file=None, app_env="production", experiment_root=tmp_path,
                        experiment_api_enabled_in_production=False)
    for module in ("src.api.evidence", "src.api.experiments"):
        monkeypatch.setattr(f"{module}.get_settings", lambda: settings)
    from src.services import native_online_evidence

    monkeypatch.setattr(native_online_evidence, "catalog", lambda: {"items": [], "unavailable": [], "pending": []})
    response = await client.get("/api/v1/evidence/capabilities")
    assert response.status_code == 200
    assert response.json()["playback_only"] is True
    assert response.json()["interactive_enabled"] is False
    assert (await client.get("/api/v1/evidence/native-online")).status_code == 200
    for endpoint in ("", "/plan", "/sensor-agent/start", "/sessions", "/native-rl/reviews"):
        assert (await client.post(f"/api/v1/experiments{endpoint}", json={})).status_code == 503
    assert (await client.post("/api/v1/evidence/native-online", json={})).status_code == 405
    assert (await client.get("/api/v1/evidence/native-online/../../etc/passwd/report")).status_code == 404
    assert list(tmp_path.iterdir()) == []
