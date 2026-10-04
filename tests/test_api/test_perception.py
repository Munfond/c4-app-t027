import json

import pytest

from tests.test_api import test_lab

lab_settings = test_lab.lab_settings


def save(lab_settings, task, **values):
    root = lab_settings.lab_data_root / "cache/perception" / task
    root.mkdir(parents=True, exist_ok=True)
    data = {
        "task": task,
        "sample_token": "token-a",
        "coordinates": {"frame": "ego", "x": "forward", "y": "left", "z": "up", "length_unit": "m"},
        "model": "test model",
        "source": "test artifact",
        "sensors": ["lidar"],
        **values,
    }
    (root / "token-a.json").write_text(json.dumps(data))


@pytest.mark.asyncio
async def test_catalog_and_missing_task_do_not_substitute_boxes(client, lab_settings):
    catalog = (await client.get("/api/v1/lab/perception/tasks")).json()["items"]
    assert all(t["frame_count"] == 0 and t["total_frames"] == 2 for t in catalog)
    assert (await client.get("/api/v1/lab/frames/token-a/perception/seg3d")).status_code == 503
    assert (await client.get("/api/v1/lab/frames/unknown/perception/seg3d")).status_code == 404
    assert (await client.get("/api/v1/lab/frames/token-a/perception/fake")).status_code == 422


@pytest.mark.asyncio
async def test_segmented_points_need_matching_labels_and_provenance(client, lab_settings):
    save(
        lab_settings,
        "seg3d",
        kind="prediction",
        classes=[{"id": 7, "name": "road", "color": "#80abaa"}],
        points=[[1, 2, 3, 7]],
    )
    url = "/api/v1/lab/frames/token-a/perception/seg3d"
    assert (await client.get(url)).json()["points"] == [[1, 2, 3, 7]]
    save(
        lab_settings,
        "seg3d",
        kind="prediction",
        classes=[{"id": 7, "name": "road", "color": "#80abaa"}],
        points=[[1, 2, 3, 99]],
    )
    assert (await client.get(url)).status_code == 503
    save(
        lab_settings,
        "seg3d",
        kind="prediction",
        classes=[{"id": 7, "name": "road", "color": "#80abaa"}],
        points=[[1, 2, 3, 7]],
        coordinates={"frame": "ego", "x": "forward", "y": "right", "z": "up", "length_unit": "m"},
    )
    assert (await client.get(url)).status_code == 503
    save(
        lab_settings,
        "seg3d",
        kind="prediction",
        classes=[{"id": 7, "name": "road", "color": "#80abaa"}],
        points=[[1, 2, 3, 7]],
        sample_token="token-b",
    )
    assert (await client.get(url)).status_code == 503


@pytest.mark.asyncio
async def test_occupancy_geometry_and_flow_finiteness(client, lab_settings):
    save(lab_settings, "occupancy", shape=[200, 200], resolution_m=0.5, extent_m=50, cells=[0] * 39999 + [2])
    assert (await client.get("/api/v1/lab/frames/token-a/perception/occupancy")).status_code == 200
    save(lab_settings, "occupancy", shape=[200, 200], resolution_m=0.5, extent_m=50, cells=[0] * 39999)
    assert (await client.get("/api/v1/lab/frames/token-a/perception/occupancy")).status_code == 503
    save(lab_settings, "flow", vectors=[[10, 2, float("nan"), 0]])
    assert (await client.get("/api/v1/lab/frames/token-a/perception/flow")).status_code == 503
    save(lab_settings, "radar", sensors=["radar"], points=[[10, 2, 1, 3, -4]])
    assert (await client.get("/api/v1/lab/frames/token-a/perception/radar")).json()["points"][0] == [10, 2, 1, 3, -4]
