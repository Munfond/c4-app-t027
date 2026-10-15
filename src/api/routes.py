from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from src.agents.graph import agent
from src.config import get_settings
from src.models.schemas import ChatRequest, ChatResponse
from src.services.anonymizer import InvalidImageError, UnavailableAnonymizerError, anonymize_bytes
from src.services.experiment_auth import require_operator

router = APIRouter()


@router.post("/anonymize")
async def anonymize_image(file: UploadFile = File(...)):
    if file.content_type not in {"image/jpeg", "image/png"}:
        raise HTTPException(415, "Only JPEG and PNG images are accepted")
    limit = get_settings().max_upload_bytes
    contents = await file.read(limit + 1)
    await file.close()
    if len(contents) > limit:
        raise HTTPException(413, "Image exceeds upload limit")
    try:
        result = await run_in_threadpool(anonymize_bytes, contents)
    except InvalidImageError as exc:
        raise HTTPException(400, str(exc)) from exc
    except UnavailableAnonymizerError as exc:
        raise HTTPException(503, "Anonymizer unavailable; original image is not served") from exc
    return Response(result, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(require_operator)])
async def chat(request: ChatRequest) -> ChatResponse:
    result = await agent.ainvoke({"query": request.message})
    return ChatResponse(response=result.get("response", ""), analysis=result.get("analysis", ""))


@router.get("/status")
async def agent_status():
    return {"status": "ready", "agent": "LangGraph Agent v1.0"}
