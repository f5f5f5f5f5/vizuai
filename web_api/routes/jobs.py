"""Jobs route scaffold."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from web_api.contracts import json_success
from web_api.deps import get_current_session_context, get_jobs_service

router = APIRouter()


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_jobs_service),
):
    job = await service.get_job(current["account"]["id"], job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Job not found."}},
        )
    return json_success(job, request=request)
