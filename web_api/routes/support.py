"""Support routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from web_api.contracts import json_success
from web_api.deps import get_current_session_context, get_support_service
from web_api.schemas.support import (
    SupportOptionsResponse,
    SupportRequestCreateRequest,
    SupportRequestCreateResponse,
)

router = APIRouter()


@router.get("/options")
async def get_support_options(
    request: Request,
    service=Depends(get_support_service),
):
    payload = SupportOptionsResponse(**(await service.get_options()))
    return json_success(payload.model_dump(mode="json"), request=request)


@router.post("/request")
async def create_support_request(
    payload: SupportRequestCreateRequest,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_support_service),
):
    result = await service.request_support(current["account"]["id"], payload.model_dump())
    response_model = SupportRequestCreateResponse(
        status=result["status"],
        support=SupportOptionsResponse(**result["support"]),
    )
    return json_success(response_model.model_dump(mode="json"), request=request)
