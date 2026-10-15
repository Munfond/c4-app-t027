"""Outbound-only worker protocol, independent from browser and LLM credentials."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path

from src.models.remote_worker import JobComplete, JobFailure, JobHeartbeat, Lease, UploadRequest, WorkerHello
from src.services import remote_jobs
from src.services.experiment_auth import authenticate_worker
from src.services.remote_storage import StorageUnavailableError

router = APIRouter(prefix="/remote-workers", tags=["remote-workers"])
Identity = Annotated[str, Depends(authenticate_worker)]
JobId = Annotated[str, Path(pattern=r"^[a-f0-9]{32}$")]


def invoke(operation, *args):
    try:
        return operation(*args)
    except (PermissionError, InterruptedError) as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, "Remote job rejected: " + str(exc)[:300]) from exc
    except OSError as exc:
        raise HTTPException(422, "Unreadable remote artifact") from exc
    except StorageUnavailableError as exc:
        raise HTTPException(503, "Remote storage unavailable") from exc


@router.post("/heartbeat")
def hello(body: WorkerHello, worker: Identity):
    return invoke(remote_jobs.hello, worker, body)


@router.post("/claim")
def claim(worker: Identity):
    return {"job": invoke(remote_jobs.claim, worker)}


@router.post("/jobs/{ident}/heartbeat")
def heartbeat(ident: JobId, body: JobHeartbeat, worker: Identity):
    return invoke(remote_jobs.heartbeat, worker, ident, body)


@router.post("/jobs/{ident}/uploads")
def uploads(ident: JobId, body: UploadRequest, worker: Identity):
    return invoke(remote_jobs.uploads, worker, ident, body)


@router.post("/jobs/{ident}/complete")
def complete(ident: JobId, body: JobComplete, worker: Identity):
    return invoke(remote_jobs.complete, worker, ident, body)


@router.post("/jobs/{ident}/fail")
def fail(ident: JobId, body: JobFailure, worker: Identity):
    return invoke(remote_jobs.fail, worker, ident, body)


@router.post("/jobs/{ident}/status")
def status(ident: JobId, body: Lease, worker: Identity):
    return invoke(remote_jobs.status, worker, ident, body.lease)
