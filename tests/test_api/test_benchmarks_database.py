"""Keep the benchmark HTTP contract compatible with database and file sources."""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base
from src.models.db_models import BenchmarkReportDB
from src.services import lab
from tests.test_api import test_lab

lab_settings = test_lab.lab_settings


@pytest.fixture
def benchmark_settings(lab_settings, tmp_path, monkeypatch):
    monkeypatch.setattr(lab, "PROJECT_ROOT", tmp_path)
    lab_settings.lab_data_root = tmp_path / "data/lab"
    return lab_settings


@pytest.mark.asyncio
async def test_benchmark_database_preserves_response_contract(client, benchmark_settings, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(lab, "SessionLocal", sessions)
    data = {"fixture_metric": 0.42}
    with sessions() as session:
        session.add(BenchmarkReportDB(section="occupancy", source="fixture/metrics.json", data_json=json.dumps(data)))
        session.commit()
    try:
        response = await client.get("/api/v1/lab/benchmarks")
        assert response.status_code == 200
        assert response.json()["sections"]["occupancy"] == {
            "available": True,
            "source": "fixture/metrics.json",
            "data": data,
        }
        assert not response.json()["sections"]["flow"]["available"]
        assert response.json()["limitations"]
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_benchmark_files_work_when_database_unavailable(client, benchmark_settings, monkeypatch):
    def unavailable():
        raise RuntimeError("Database unavailable in this test")

    monkeypatch.setattr(lab, "SessionLocal", unavailable)
    file = benchmark_settings.lab_data_root / "models/occupancy/metrics.json"
    file.parent.mkdir(parents=True)
    file.write_text(json.dumps({"fixture_metric": 0.4}), encoding="utf-8")
    response = await client.get("/api/v1/lab/benchmarks")
    assert response.status_code == 200
    section = response.json()["sections"]["occupancy"]
    assert section["available"] and section["data"] == {"fixture_metric": 0.4}
    assert section["source"] == "models/occupancy/metrics.json"
