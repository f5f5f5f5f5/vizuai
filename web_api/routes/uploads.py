"""Upload route scaffold."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app_services.analytics.events import EVENT_UPLOAD_COMPLETED, EVENT_UPLOAD_INTENT_CREATED
from web_api.contracts import error_payload, json_success, success_payload
from web_api.deps import (
    get_analytics_service,
    get_current_session_context,
    get_idempotency_service,
    get_uploads_service,
)
from web_api.schemas.uploads import (
    UploadCompleteRequest,
    UploadCompleteResponse,
    UploadIntentRequest,
    UploadIntentResponse,
)

router = APIRouter()


@router.post("/image")
async def create_image_upload(
    payload: UploadIntentRequest,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_uploads_service),
    analytics=Depends(get_analytics_service),
):
    result = await service.create_intent(current["account"]["id"], payload.model_dump())
    if result.get("status") != "ok":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "UPLOAD_FAILED",
                    "message": "Upload intent could not be created.",
                    "details": {"status": result.get("status")},
                }
            },
        )
    await analytics.record_event(
        current["account"]["id"],
        event_type=EVENT_UPLOAD_INTENT_CREATED,
        screen_key="uploads",
        action_key="image_upload_intent",
        source="web_api",
        meta={"purpose": payload.purpose, "content_type": payload.content_type},
    )
    response_model = UploadIntentResponse(upload=result["upload"])
    return json_success(response_model.model_dump(mode="json"), request=request)


@router.post("/style-reference")
async def create_style_reference_upload(
    payload: UploadIntentRequest,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_uploads_service),
    analytics=Depends(get_analytics_service),
):
    result = await service.create_intent(current["account"]["id"], payload.model_dump())
    if result.get("status") != "ok":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "UPLOAD_FAILED",
                    "message": "Style reference upload intent could not be created.",
                    "details": {"status": result.get("status")},
                }
            },
        )
    await analytics.record_event(
        current["account"]["id"],
        event_type=EVENT_UPLOAD_INTENT_CREATED,
        screen_key="uploads",
        action_key="style_reference_upload_intent",
        source="web_api",
        meta={"purpose": payload.purpose, "content_type": payload.content_type},
    )
    response_model = UploadIntentResponse(upload=result["upload"])
    return json_success(response_model.model_dump(mode="json"), request=request)


@router.post("/{upload_id}/complete")
async def complete_upload(
    upload_id: str,
    payload: UploadCompleteRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current=Depends(get_current_session_context),
    service=Depends(get_uploads_service),
    analytics=Depends(get_analytics_service),
    idempotency=Depends(get_idempotency_service),
):
    idem = await idempotency.begin(
        current["account"]["id"],
        scope="uploads.complete",
        key=idempotency_key,
        payload={"upload_id": upload_id, **payload.model_dump()},
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
        result = await service.complete_intent(
            current["account"]["id"],
            upload_id,
            payload.storage_key,
        )
        if result.get("status") != "ok":
            error_body = {
                "error": {
                    "code": "UPLOAD_FAILED",
                    "message": "Upload completion failed.",
                    "details": {"status": result.get("status")},
                }
            }
            if record_id:
                await idempotency.complete(
                    record_id,
                    response_status=status.HTTP_400_BAD_REQUEST,
                    response_body=error_payload(
                        "UPLOAD_FAILED",
                        "Upload completion failed.",
                        request=request,
                        details={"status": result.get("status")},
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_body,
            )
        try:
            await analytics.record_event(
                current["account"]["id"],
                event_type=EVENT_UPLOAD_COMPLETED,
                screen_key="uploads",
                action_key="upload_complete",
                source="web_api",
                meta={"upload_id": upload_id, "storage_key": payload.storage_key},
            )
        except Exception:
            pass
        response_model = UploadCompleteResponse(file=result["file"])
        response_body = success_payload(response_model.model_dump(mode="json"), request=request)
        if record_id:
            await idempotency.complete(record_id, response_status=status.HTTP_200_OK, response_body=response_body)
        return json_success(response_model.model_dump(mode="json"), request=request)
    except HTTPException:
        raise
    except Exception:
        await idempotency.abandon(record_id)
        raise
