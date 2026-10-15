"""Opt-in PostgreSQL contract, isolated in an ephemeral schema (no Lab data touched)."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from src.models.remote_worker import JobHeartbeat
from src.services import remote_database, remote_jobs
from src.services import sensor_studies as studies
from tests.test_api.test_remote_workers import (
    enqueue_study,
    register,
    stage,
)
from tests.test_api.test_remote_workers import (
    remote_settings as _remote_settings,
)

remote_settings = _remote_settings


@pytest.mark.skipif(not os.environ.get("P027_TEST_POSTGRES_URL"), reason="Set an isolated PostgreSQL test URL explicitly")
def test_postgresql_study_atomic_claim_and_artifacts(remote_settings):
    settings, blobs = remote_settings
    url = make_url(os.environ["P027_TEST_POSTGRES_URL"])
    admin = create_engine(url)
    schema = "p027_test_" + uuid.uuid4().hex
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped = url.update_query_dict({"options": "-csearch_path=" + schema})
    settings.remote_database_url = scoped.render_as_string(hide_password=False)
    target = remote_database.engine(settings.remote_database_url)
    try:
        remote_database.initialize()
        remote_database.initialize()  # Migration is additive/idempotent.
        study = enqueue_study()
        register("gpu-1")
        register("gpu-2")
        with ThreadPoolExecutor(max_workers=2) as pool:
            assigned = list(pool.map(remote_jobs.claim, ["gpu-1", "gpu-2"]))
        assert sum(job is not None for job in assigned) == 1
        index = next(i for i, job in enumerate(assigned) if job)
        worker = ["gpu-1", "gpu-2"][index]
        assignment = assigned[index]
        remote_jobs.heartbeat(worker, assignment["id"], JobHeartbeat(lease=assignment["lease"], completed_frames=1))
        body = stage(assignment, blobs, worker=worker)
        remote_jobs.complete(worker, assignment["id"], body)
        candidate = remote_jobs.claim("gpu-1")
        assert candidate is not None
        remote_jobs.complete("gpu-1", candidate["id"], stage(candidate, blobs))
        assert studies.get(study["id"])["status"] == "completed"
        assert studies.comparison(study["id"])["environments"][0]["provisional_selected"] == "half"
    finally:
        target.dispose()
        with admin.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
