"""A dataset export must preserve prompt/profile identity and never link missing output."""
import json

import pytest

from scripts.test_sensor_agent import save_dataset_index


def sample_study():
    return {"id": "study", "metadata": {"request": "Giảm dữ liệu LiDAR"},
            "checkpoint_sha256": "verified-digest", "jobs": [{
                "id": "job", "environment": 0, "profile": "lower_channels", "status": "succeeded",
                "result": {"manifest": {"scenario": {"lidar": {"channels": 16}},
                                        "frames": [{"id": "frame_0000", "frame_id": 42}]}}
            }]}


def test_export_maps_prompt_and_sensor_to_real_output(tmp_path):
    capture = tmp_path / "job/capture"
    prediction = tmp_path / "job/predictions/occupancy_lidar"
    capture.mkdir(parents=True)
    prediction.mkdir(parents=True)
    (capture / "frame_0000.npz").touch()
    (capture / "frame_0000.png").touch()
    (capture / "frame_0000.json").write_text('{}')
    (prediction / "0000.json").write_text('{"shape":[200,200]}')
    save_dataset_index(sample_study(), tmp_path)
    index = json.loads((tmp_path / "dataset-index.json").read_text(encoding="utf-8"))
    assert index["prompt"] == "Giảm dữ liệu LiDAR"
    record = index["records"][0]
    assert record["profile"] == "lower_channels"
    assert record["lidar"]["channels"] == 16
    assert record["frame"]["frame_id"] == 42
    assert (tmp_path / record["input_npz"]).is_file()
    assert (tmp_path / record["prediction_json"]).is_file()


def test_export_rejects_missing_prediction(tmp_path):
    capture = tmp_path / "job/capture"
    capture.mkdir(parents=True)
    (capture / "frame_0000.npz").touch()
    (capture / "frame_0000.png").touch()
    (capture / "frame_0000.json").write_text('{}')
    with pytest.raises(RuntimeError, match="Dataset artifact missing"):
        save_dataset_index(sample_study(), tmp_path)
    assert not (tmp_path / "dataset-index.json").exists()
