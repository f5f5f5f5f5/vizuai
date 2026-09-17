"""Furniture route scaffold."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response

from app_services.analytics.events import EVENT_FURNITURE_JOB_CREATED
from web_api.contracts import error_payload, json_success, success_payload
from web_api.deps import (
    api_not_implemented,
    get_analytics_service,
    get_current_session_context,
    get_furniture_draft_service,
    get_idempotency_service,
    get_jobs_service,
    get_furniture_result_service,
)
from web_api.schemas.furniture import (
    FurnitureDraftCreateRequest,
    FurnitureDraftListResponse,
    FurnitureDraftResponse,
    FurnitureDraftSeedResponse,
    FurnitureDraftUpdateRequest,
    FurnitureJobCreateRequest,
)
from web_api.schemas.results import FurnitureResultResponse

router = APIRouter()


@router.get("/drafts")
async def list_furniture_drafts(
    request: Request,
    limit: int = 6,
    current=Depends(get_current_session_context),
    service=Depends(get_furniture_draft_service),
):
    drafts = await service.list_drafts(current["account"]["id"], limit=limit)
    response_model = FurnitureDraftListResponse(
        items=[FurnitureDraftResponse(**draft) for draft in drafts]
    )
    return json_success(response_model.model_dump(mode="json"), request=request)


@router.post("/drafts")
async def create_furniture_draft(
    payload: FurnitureDraftCreateRequest,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_furniture_draft_service),
):
    result = await service.create_draft(current["account"]["id"], payload.model_dump())
    if result.get("status") != "ok":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Furniture draft could not be created.",
                    "details": {"status": result.get("status")},
                }
            },
        )
    return json_success(FurnitureDraftResponse(**result["draft"]).model_dump(mode="json"), request=request)


@router.get("/drafts/{draft_id}")
async def get_furniture_draft(
    draft_id: str,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_furniture_draft_service),
):
    draft = await service.get_draft(current["account"]["id"], draft_id)
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Furniture draft not found."}},
        )
    return json_success(FurnitureDraftResponse(**draft).model_dump(mode="json"), request=request)


@router.patch("/drafts/{draft_id}")
async def update_furniture_draft(
    draft_id: str,
    payload: FurnitureDraftUpdateRequest,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_furniture_draft_service),
):
    draft = await service.update_draft(
        current["account"]["id"],
        draft_id,
        payload.model_dump(exclude_unset=True),
    )
    if draft is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Furniture draft not found."}},
        )
    return json_success(FurnitureDraftResponse(**draft).model_dump(mode="json"), request=request)


@router.delete("/drafts/{draft_id}")
async def delete_furniture_draft(
    draft_id: str,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_furniture_draft_service),
):
    deleted = await service.delete_draft(current["account"]["id"], draft_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Furniture draft not found."}},
        )
    return json_success({"status": "deleted"}, request=request)


@router.post("/jobs")
async def create_furniture_job(
    payload: FurnitureJobCreateRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current=Depends(get_current_session_context),
    service=Depends(get_jobs_service),
    analytics=Depends(get_analytics_service),
    idempotency=Depends(get_idempotency_service),
):
    idem = await idempotency.begin(
        current["account"]["id"],
        scope="furniture.job.create",
        key=idempotency_key,
        payload=payload.model_dump(),
    )
    record_id = idem.get("record_id")
    if idem.get("status") == "replay":
        return JSONResponse(status_code=idem["response_status"], content=idem["response_body"])
    if idem.get("status") == "payload_mismatch":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "IDEMPOTENCY_KEY_REUSED", "message": "Idempotency key was reused with a different payload."}},
        )
    if idem.get("status") == "in_progress":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "REQUEST_IN_PROGRESS", "message": "A request with this idempotency key is already in progress."}},
        )
    try:
        result = await service.create_job(
            current["account"]["id"],
            job_type="furniture_search",
            draft_id=payload.draft_id,
        )
        if result.get("status") == "insufficient_credits":
            error_envelope = error_payload(
                "INSUFFICIENT_CREDITS",
                "Not enough credits to start the furniture search.",
                request=request,
                details=result.get("balance") or {},
            )
            error_body = {
                "error": {
                    "code": "INSUFFICIENT_CREDITS",
                    "message": "Not enough credits to start the furniture search.",
                    "details": result.get("balance") or {},
                }
            }
            if record_id:
                await idempotency.complete(record_id, response_status=status.HTTP_402_PAYMENT_REQUIRED, response_body=error_envelope)
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=error_body,
            )
        if result.get("status") != "ok":
            error_envelope = error_payload(
                "VALIDATION_ERROR",
                "Furniture job could not be created.",
                request=request,
                details={"status": result.get("status")},
            )
            error_body = {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Furniture job could not be created.",
                    "details": {"status": result.get("status")},
                }
            }
            if record_id:
                await idempotency.complete(record_id, response_status=status.HTTP_400_BAD_REQUEST, response_body=error_envelope)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_body,
            )
        try:
            await service.enqueue_job(result["job"]["id"])
        except Exception:
            await service.cancel_job_before_start(
                result["job"]["id"],
                error_code="ENQUEUE_FAILED",
                error_message="Failed to enqueue furniture job.",
            )
            error_envelope = error_payload(
                "ENQUEUE_FAILED",
                "Furniture job queueing failed. Credits were released.",
                request=request,
            )
            error_body = {
                "error": {
                    "code": "ENQUEUE_FAILED",
                    "message": "Furniture job queueing failed. Credits were released.",
                }
            }
            if record_id:
                await idempotency.complete(record_id, response_status=status.HTTP_502_BAD_GATEWAY, response_body=error_envelope)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=error_body,
            )
        try:
            await analytics.record_event(
                current["account"]["id"],
                event_type=EVENT_FURNITURE_JOB_CREATED,
                screen_key="furniture",
                action_key="job_create",
                source="web_api",
                meta={
                    "job_id": result["job"]["id"],
                    "draft_id": payload.draft_id,
                    "units_reserved": result["job"].get("units_reserved"),
                },
            )
        except Exception:
            pass
        if record_id:
            await idempotency.complete(
                record_id,
                response_status=status.HTTP_200_OK,
                response_body=success_payload(result["job"], request=request),
            )
        return json_success(result["job"], request=request)
    except HTTPException:
        raise
    except Exception:
        await idempotency.abandon(record_id)
        raise


@router.get("/jobs/{job_id}")
async def get_furniture_job(
    job_id: str,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_jobs_service),
):
    job = await service.get_job(current["account"]["id"], job_id)
    if job is None or job["job_type"] != "furniture_search":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Furniture job not found."}},
        )
    return json_success(job, request=request)


@router.get("/results/{result_id}")
async def get_furniture_result(
    result_id: str,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_furniture_result_service),
):
    result = await service.get_result(current["account"]["id"], result_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Furniture result not found."}},
    )
    return json_success(FurnitureResultResponse(**result).model_dump(mode="json"), request=request)


@router.get("/results/{result_id}/download")
async def download_furniture_result(
    result_id: str,
    current=Depends(get_current_session_context),
    service=Depends(get_furniture_result_service),
):
    payload = await service.get_download_payload(current["account"]["id"], result_id)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Furniture result file not found."}},
        )
    return Response(
        content=payload["content"],
        media_type=payload["content_type"],
        headers={
            "Content-Disposition": f'attachment; filename="{payload["filename"]}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/results/{result_id}/reuse")
async def get_furniture_reuse_payload(
    result_id: str,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_furniture_draft_service),
):
    payload = await service.get_reuse_payload(current["account"]["id"], result_id)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "NOT_FOUND",
                    "message": "Reusable furniture payload not found.",
                }
            },
        )
    return json_success(FurnitureDraftSeedResponse(**payload).model_dump(mode="json"), request=request)
