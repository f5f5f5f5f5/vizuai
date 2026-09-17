"""History route scaffold."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from web_api.contracts import json_success
from web_api.deps import get_current_session_context, get_history_service
from web_api.schemas.history import (
    HistoryFiltersResponse,
    HistoryItemResponse,
    HistoryListResponse,
    HistoryPaginationResponse,
)

router = APIRouter()


@router.get("")
async def get_history(
    request: Request,
    mode: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    query: str | None = Query(default=None, alias="q"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50),
    current=Depends(get_current_session_context),
    service=Depends(get_history_service),
):
    payload = await service.list_history(
        current["account"]["id"],
        mode=mode,
        status=status_filter,
        query=query,
        page=page,
        page_size=page_size,
    )
    response_model = HistoryListResponse(
        items=[HistoryItemResponse(**item) for item in payload["items"]],
        pagination=HistoryPaginationResponse(**payload["pagination"]),
        filters=HistoryFiltersResponse(**payload["filters"]),
    )
    return json_success(response_model.model_dump(mode="json"), request=request)


@router.get("/{item_id}")
async def get_history_item(
    item_id: str,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_history_service),
):
    item = await service.get_item(current["account"]["id"], item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "History item not found."}},
        )
    return json_success({"item": HistoryItemResponse(**item).model_dump(mode="json")}, request=request)
