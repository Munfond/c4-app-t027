import io
import json

import pytest
from PIL import Image

from src.config import Settings, get_settings
from src.main import app


@pytest.fixture
def lab_settings(tmp_path, monkeypatch):
    settings = Settings(_env_file=None, lab_data_root=tmp_path / "lab", nusc_root=tmp_path / "nusc")
    root = settings.lab_data_root / "exports/L3E"
    root.mkdir(parents=True)
    (root / "samples.csv").write_text(
        "sample_idx,sample_token,scene,timestamp_s\n0,token-a,scene-a,1.0\n1,token-b,scene-a,1.5\n"
    )
    (root / "pred_our_lidar_ego.csv").write_text(
        "sample_idx,class,x,y,z,w,l,h,yaw,vx,vy,score\n"
        "0,car,10,2,0,2,4,1.5,0,3,0,0.8\n0,car,20,2,0,2,4,1.5,0,3,0,0.1\n"
        "1,car,30,2,0,2,4,1.5,0,3,0,0.9\n"
    )
    # Modules import the cached settings function directly.
    for module in ("src.api.routes", "src.api.lab", "src.services.lab", "src.services.anonymizer"):
        monkeypatch.setattr(f"{module}.get_settings", lambda: settings)
    app.dependency_overrides[get_settings] = lambda: settings
    yield settings
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_frame_mapping_and_threshold(client, lab_settings):
    response = await client.get("/api/v1/lab/frames/token-a/detections?model=our_lidar&threshold=0.5")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["boxes"]) == 1
    assert payload["boxes"][0]["x"] == 10
    assert payload["coordinates"]["yaw_unit"] == "rad"
    assert (await client.get("/api/v1/lab/frames/missing/detections")).status_code == 404
    assert (await client.get("/api/v1/lab/frames/token-a/detections?model=unknown")).status_code == 422
    assert (await client.get("/api/v1/lab/frames/token-a/detections?threshold=2")).status_code == 422


@pytest.mark.asyncio
async def test_missing_artifacts_are_explicit(client, lab_settings):
    response = await client.get("/api/v1/lab/frames/token-a/detections?model=crn")
    assert response.status_code == 503
    models = (await client.get("/api/v1/lab/models")).json()["items"]
    assert next(m for m in models if m["id"] == "our_lidar")["available"]
    assert not next(m for m in models if m["id"] == "crn")["available"]
    assert (await client.get("/api/v1/lab/scenes")).json()["items"][0]["frame_count"] == 2


@pytest.mark.asyncio
async def test_upload_validation_and_fail_closed(client, lab_settings):
    assert (await client.post("/api/v1/anonymize", files={"file": ("x.txt", b"x", "text/plain")})).status_code == 415
    assert (await client.post("/api/v1/anonymize", files={"file": ("x.png", b"bad", "image/png")})).status_code == 400
    image = io.BytesIO()
    Image.new("RGB", (4, 4)).save(image, format="PNG")
    response = await client.post("/api/v1/anonymize", files={"file": ("x.png", image.getvalue(), "image/png")})
    assert response.status_code == 503
    assert response.content != image.getvalue()
    lab_settings.max_upload_bytes = 2
    assert (await client.post("/api/v1/anonymize", files={"file": ("x.png", b"123", "image/png")})).status_code == 413


@pytest.mark.asyncio
async def test_camera_never_returns_raw_when_disabled(client, lab_settings):
    root = lab_settings.nusc_root
    (root / "v1.0-mini").mkdir(parents=True)
    (root / "samples/CAM_FRONT").mkdir(parents=True)
    image = root / "samples/CAM_FRONT/a.jpg"
    Image.new("RGB", (4, 4)).save(image)
    (root / "v1.0-mini/sample_data.json").write_text(
        json.dumps([{"sample_token": "token-a", "is_key_frame": True, "filename": "samples/CAM_FRONT/a.jpg"}])
    )
    response = await client.get("/api/v1/lab/frames/token-a/cameras/CAM_FRONT")
    assert response.status_code == 503
    assert response.content != image.read_bytes()
    assert (await client.get("/api/v1/lab/frames/token-a/cameras/INVALID")).status_code == 422


@pytest.mark.asyncio
async def test_camera_cache_hit_and_headers(client, lab_settings):
    cache_dir = lab_settings.resolved_camera_cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIFfake-anonymized-image"
    (cache_dir / "token-a_CAM_FRONT.jpg").write_bytes(cached_bytes)

    response = await client.get("/api/v1/lab/frames/token-a/cameras/CAM_FRONT")
    assert response.status_code == 200
    assert response.content == cached_bytes
    assert response.headers["x-camera-cache"] == "HIT"
    assert response.headers["x-anonymized"] == "true"

    cap_res = await client.get("/api/v1/lab/capabilities")
    assert cap_res.status_code == 200
    assert cap_res.json()["camera_cache_present"] is True


@pytest.mark.asyncio
async def test_precomputed_risk_heatmap(client, lab_settings, monkeypatch):
    monkeypatch.setattr("src.services.lab.risk_heatmap_png", lambda token, system, vmax: b"\x89PNG\r\n\x1a\nmock")
    response = await client.get("/api/v1/lab/frames/token-a/risk?system=classical&vmax=0.3")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-risk-system"] == "classical"
    assert response.headers["x-risk-uncalibrated"] == "true"
    assert (await client.get("/api/v1/lab/frames/token-a/risk?system=unknown")).status_code == 422
    assert (await client.get("/api/v1/lab/frames/missing/risk")).status_code == 404


@pytest.mark.asyncio
async def test_benchmarks_provenance_and_limitations(client, lab_settings):
    # 1. When benchmark files are absent, available is False and data is None (fail-safe, no 500)
    response = await client.get("/api/v1/lab/benchmarks")
    assert response.status_code == 200
    payload = response.json()
    assert payload["split"] == "mini_val"
    assert payload["frame_count"] == 81
    assert "limitations" in payload
    assert len(payload["limitations"]) == 4
    assert payload["sections"]["detection"]["available"] is False
    assert payload["sections"]["detection"]["data"] is None

    # 2. When benchmark file is present, available is True and data is loaded correctly
    det_path = lab_settings.lab_data_root / "models/our_bevfusion_mini/metrics.json"
    det_path.parent.mkdir(parents=True, exist_ok=True)
    det_path.write_text(json.dumps({"rows": [{"model": "our_bevfusion", "mAP": 0.54}]}))

    response = await client.get("/api/v1/lab/benchmarks")
    assert response.status_code == 200
    payload = response.json()
    assert payload["sections"]["detection"]["available"] is True
    assert payload["sections"]["detection"]["source"] == "models/our_bevfusion_mini/metrics.json"
    assert payload["sections"]["detection"]["data"]["rows"][0]["model"] == "our_bevfusion"
    assert payload["sections"]["detection"]["data"]["rows"][0]["mAP"] == 0.54


@pytest.mark.asyncio
async def test_deploy_health_and_readonly_cache(client, lab_settings, monkeypatch):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    cap_res = await client.get("/api/v1/lab/capabilities")
    assert cap_res.status_code == 200
    caps = cap_res.json()
    assert caps["schema_version"] == "1.0"
    assert "processed-only" in caps["camera_policy"]

    from src.services import lab

    def failing_mkdir(*args, **kwargs):
        raise OSError("Read-only file system")

    monkeypatch.setattr("pathlib.Path.mkdir", failing_mkdir)
    # save_cached_camera should catch OSError gracefully without crashing
    lab.save_cached_camera("token-x", "CAM_FRONT", b"test-bytes")
