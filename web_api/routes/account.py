"""Account routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from web_api.contracts import json_success
from web_api.deps import get_accounts_service, get_current_session_context
from web_api.schemas.account import AccountUpdateRequest

router = APIRouter()


@router.get("")
async def get_account(
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_accounts_service),
):
    account = await service.get_account(current["account"]["id"])
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Account not found."}},
        )
    return json_success({"account": account}, request=request)


@router.patch("")
async def update_account(
    payload: AccountUpdateRequest,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_accounts_service),
):
    account = await service.update_account(
        current["account"]["id"],
        payload.model_dump(exclude_unset=True),
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Account not found."}},
        )
    return json_success({"account": account}, request=request)


@router.get("/balance")
async def get_balance(request: Request, current=Depends(get_current_session_context)):
    return json_success(current["balance"], request=request)


@router.get("/usage")
async def get_usage(
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_accounts_service),
):
    usage = await service.get_usage(current["account"]["id"])
    return json_success({"usage": usage}, request=request)
