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
