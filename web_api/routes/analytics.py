"""Analytics routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from web_api.contracts import json_success
from web_api.deps import (
    get_analytics_service,
    get_current_session_context,
    get_public_analytics_service,
)
from web_api.schemas.analytics import AnalyticsEventRequest, AnalyticsEventResponse

public_router = APIRouter()
router = APIRouter()


@public_router.post("/events")
async def track_public_event(
    payload: AnalyticsEventRequest,
    request: Request,
    service=Depends(get_public_analytics_service),
):
    anon_id = await service.record_event(
        anon_id=payload.anon_id,
        event_type=payload.event_type,
        screen_key=payload.screen_key,
        action_key=payload.action_key,
        source=payload.source or "frontend_public",
        path=payload.path,
        referrer=payload.referrer,
        host=request.url.hostname,
        meta=payload.meta,
    )
    response_model = AnalyticsEventResponse(status="accepted", anon_id=anon_id)
    return json_success(response_model.model_dump(mode="json"), request=request)


@router.post("/events")
async def track_account_event(
    payload: AnalyticsEventRequest,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_analytics_service),
):
    await service.record_event(
        current["account"]["id"],
        event_type=payload.event_type,
        screen_key=payload.screen_key,
        action_key=payload.action_key,
        source=payload.source or "frontend_app",
        meta={
            **(payload.meta or {}),
            **({"path": payload.path} if payload.path else {}),
            **({"referrer": payload.referrer} if payload.referrer else {}),
        },
    )
    response_model = AnalyticsEventResponse(status="accepted")
    return json_success(response_model.model_dump(mode="json"), request=request)
