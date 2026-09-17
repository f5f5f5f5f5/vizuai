"""Billing routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app_services.analytics.events import EVENT_CHECKOUT_CREATED
from web_api.contracts import error_payload, json_success, success_payload
from web_api.deps import (
    get_analytics_service,
    get_checkout_service,
    get_current_session_context,
    get_idempotency_service,
)
from web_api.schemas.billing import (
    BillingCheckoutCreateRequest,
    BillingCheckoutResponse,
    BillingPaymentResponse,
    BillingPlanResponse,
    BillingPromocodeCheckRequest,
    BillingPromocodeCheckResponse,
)

router = APIRouter()


def _promocode_reason_message(reason: str) -> str:
    mapping = {
        "empty_code": "Введите промокод.",
        "not_found": "Промокод не найден.",
        "code_inactive": "Промокод неактивен.",
        "code_not_started": "Промокод ещё не активен.",
        "code_expired": "Срок действия промокода истёк.",
        "code_exhausted": "Промокод закончился.",
        "new_users_only": "Промокод доступен только новым пользователям.",
        "max_uses_per_user_reached": "Лимит использования промокода уже исчерпан.",
        "unsupported_discount_type": "Тип скидки по промокоду не поддерживается.",
        "invalid_discount": "Промокод не даёт скидку для выбранного пакета.",
        "invalid_checkout_amounts": "Пакет для применения промокода выбран некорректно.",
        "invalid_plan": "Выберите корректный пакет.",
        "unsupported_provider": "Этот способ оплаты не поддерживается.",
    }
    return mapping.get(reason, "Не удалось применить промокод.")


@router.get("/plans")
async def get_billing_plans(
    request: Request,
    service=Depends(get_checkout_service),
):
    plans = await service.list_plans()
    response_models = [BillingPlanResponse(**plan).model_dump(mode="json") for plan in plans]
    return json_success(response_models, request=request)


@router.post("/promocode/check")
async def check_promocode(
    payload: BillingPromocodeCheckRequest,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_checkout_service),
):
    result = await service.preview_promocode(current["account"]["id"], payload.model_dump())
    status_name = str(result.get("status") or "")
    if status_name == "unsupported_provider":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "VALIDATION_ERROR", "message": "Unsupported billing provider."}},
        )
    if status_name == "invalid_plan":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "VALIDATION_ERROR", "message": "Invalid billing plan."}},
        )
    if status_name != "ok":
        reason = str(result.get("reason") or "invalid")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": {
                    "code": "PROMOCODE_INVALID",
                    "message": _promocode_reason_message(reason),
                    "details": {"reason": reason},
                }
            },
        )
    response_model = BillingPromocodeCheckResponse(**result)
    return json_success(response_model.model_dump(mode="json"), request=request)


@router.post("/checkout")
async def create_checkout(
    payload: BillingCheckoutCreateRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    current=Depends(get_current_session_context),
    service=Depends(get_checkout_service),
    analytics=Depends(get_analytics_service),
    idempotency=Depends(get_idempotency_service),
):
    idem = await idempotency.begin(
        current["account"]["id"],
        scope="billing.checkout.create",
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
        result = await service.create_checkout(current["account"]["id"], payload.model_dump())
        status_name = str(result.get("status") or "")
        if status_name == "unsupported_provider":
            error_body = {"error": {"code": "VALIDATION_ERROR", "message": "Unsupported billing provider."}}
            if record_id:
                await idempotency.complete(
                    record_id,
                    response_status=status.HTTP_400_BAD_REQUEST,
                    response_body=error_payload(
                        "VALIDATION_ERROR",
                        "Unsupported billing provider.",
                        request=request,
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_body,
            )
        if status_name == "invalid_plan":
            error_body = {"error": {"code": "VALIDATION_ERROR", "message": "Invalid billing plan."}}
            if record_id:
                await idempotency.complete(
                    record_id,
                    response_status=status.HTTP_400_BAD_REQUEST,
                    response_body=error_payload(
                        "VALIDATION_ERROR",
                        "Invalid billing plan.",
                        request=request,
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_body,
            )
        if status_name == "invalid_promocode":
            reason = str(result.get("reason") or "invalid")
            message = _promocode_reason_message(reason)
            error_body = {
                "error": {
                    "code": "PROMOCODE_INVALID",
                    "message": message,
                    "details": {"reason": reason},
                }
            }
            if record_id:
                await idempotency.complete(
                    record_id,
                    response_status=status.HTTP_400_BAD_REQUEST,
                    response_body=error_payload(
                        "PROMOCODE_INVALID",
                        message,
                        request=request,
                        details={"reason": reason},
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_body,
            )
        if status_name == "init_failed":
            error_body = {"error": {"code": "CHECKOUT_INIT_FAILED", "message": "Checkout init failed."}}
            if record_id:
                await idempotency.complete(
                    record_id,
                    response_status=status.HTTP_502_BAD_GATEWAY,
                    response_body=error_payload(
                        "CHECKOUT_INIT_FAILED",
                        "Checkout init failed.",
                        request=request,
                    ),
                )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=error_body,
            )
        try:
            await analytics.record_event(
                current["account"]["id"],
                event_type=EVENT_CHECKOUT_CREATED,
                screen_key="billing",
                action_key="checkout_create",
                source="web_api",
                meta={
                    "checkout_id": result.get("id"),
                    "provider": payload.provider,
                    "credits": payload.credits,
                },
            )
        except Exception:
            pass
        response_model = BillingCheckoutResponse(**result)
        response_body = success_payload(response_model.model_dump(mode="json"), request=request)
        if record_id:
            await idempotency.complete(record_id, response_status=status.HTTP_200_OK, response_body=response_body)
        return json_success(response_model.model_dump(mode="json"), request=request)
    except HTTPException:
        raise
    except Exception:
        await idempotency.abandon(record_id)
        raise


@router.get("/checkout/{checkout_id}")
async def get_checkout(
    checkout_id: str,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_checkout_service),
):
    checkout = await service.get_checkout(current["account"]["id"], checkout_id)
    if checkout is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Checkout not found."}},
        )
    return json_success(BillingCheckoutResponse(**checkout).model_dump(mode="json"), request=request)


@router.get("/payments")
async def get_payments(
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_checkout_service),
):
    payments = await service.list_payments(current["account"]["id"])
    response_models = [BillingPaymentResponse(**payment).model_dump(mode="json") for payment in payments]
    return json_success(response_models, request=request)


@router.get("/payments/{payment_id}")
async def get_payment(
    payment_id: str,
    request: Request,
    current=Depends(get_current_session_context),
    service=Depends(get_checkout_service),
):
    payment = await service.get_payment(current["account"]["id"], payment_id)
    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": "Payment not found."}},
        )
    return json_success(BillingPaymentResponse(**payment).model_dump(mode="json"), request=request)
