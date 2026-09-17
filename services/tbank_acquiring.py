"""T-Bank Internet Acquiring API client."""
from __future__ import annotations

import hashlib
import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import aiohttp

from config import Settings


@dataclass(frozen=True)
class TBankInitResult:
    payment_id: str
    payment_url: str
    status: str | None
    raw: dict[str, Any]


class TBankAcquiringService:
    _shared_session: aiohttp.ClientSession | None = None
    _shared_session_timeout_seconds: int | None = None
    _shared_session_lock = asyncio.Lock()

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def is_configured(self) -> bool:
        return bool(self._settings.TBANK_TERMINAL_KEY and self._settings.TBANK_PASSWORD)

    def accepted_statuses(self) -> set[str]:
        raw = str(self._settings.TBANK_ACCEPT_STATUSES or "")
        return {item.strip().upper() for item in raw.split(",") if item.strip()}

    def notification_url(self) -> str | None:
        if self._settings.WORKER_PUBLIC_BASE_URL:
            base = str(self._settings.WORKER_PUBLIC_BASE_URL).rstrip("/")
            path = str(self._settings.TBANK_NOTIFICATION_PATH or "/payments/tbank/notify")
            if not path.startswith("/"):
                path = "/" + path
            return f"{base}{path}"
        return None

    async def init_payment(
        self,
        *,
        order_id: str,
        amount_rub: Decimal,
        description: str,
        customer_key: str | None = None,
        success_url: str | None = None,
        fail_url: str | None = None,
    ) -> TBankInitResult:
        if not self.is_configured():
            raise RuntimeError("TBank acquiring is not configured")
        amount_kopecks = int((amount_rub * Decimal("100")).quantize(Decimal("1")))
        payload: dict[str, Any] = {
            "TerminalKey": str(self._settings.TBANK_TERMINAL_KEY),
            "Amount": amount_kopecks,
            "OrderId": str(order_id),
            "Description": str(description),
        }
        notification_url = self.notification_url()
        if notification_url:
            payload["NotificationURL"] = notification_url
        resolved_success_url = str(success_url or self._settings.TBANK_SUCCESS_URL or "").strip()
        resolved_fail_url = str(fail_url or self._settings.TBANK_FAIL_URL or "").strip()
        if resolved_success_url:
            payload["SuccessURL"] = resolved_success_url
        if resolved_fail_url:
            payload["FailURL"] = resolved_fail_url
        if customer_key:
            payload["CustomerKey"] = str(customer_key)
        receipt = self._build_receipt(
            amount_kopecks=amount_kopecks,
            item_fallback_name=description,
        )
        if receipt is not None:
            payload["Receipt"] = receipt
        payload["Token"] = self._build_token(payload, str(self._settings.TBANK_PASSWORD))
        data = await self._post("Init", payload)
        success = bool(data.get("Success"))
        payment_url = str(data.get("PaymentURL") or "").strip()
        payment_id = str(data.get("PaymentId") or "").strip()
        if not success or not payment_url or not payment_id:
            raise RuntimeError(
                "TBank Init failed: "
                f"success={success} code={data.get('ErrorCode')} "
                f"message={data.get('Message')} details={data.get('Details')}"
            )
        return TBankInitResult(
            payment_id=payment_id,
            payment_url=payment_url,
            status=str(data.get("Status") or "").strip() or None,
            raw=data,
        )

    async def get_state(self, *, payment_id: str) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("TBank acquiring is not configured")
        pid = str(payment_id or "").strip()
        if not pid:
            raise RuntimeError("payment_id is required")
        payload: dict[str, Any] = {
            "TerminalKey": str(self._settings.TBANK_TERMINAL_KEY),
            "PaymentId": pid,
        }
        payload["Token"] = self._build_token(payload, str(self._settings.TBANK_PASSWORD))
        data = await self._post("GetState", payload)
        return {
            "success": bool(data.get("Success")),
            "status": str(data.get("Status") or "").strip() or None,
            "payment_id": str(data.get("PaymentId") or "").strip() or pid,
            "raw": data,
        }

    async def cancel_payment(
        self,
        *,
        payment_id: str,
        amount_kopecks: int | None = None,
    ) -> dict[str, Any]:
        if not self.is_configured():
            raise RuntimeError("TBank acquiring is not configured")
        pid = str(payment_id or "").strip()
        if not pid:
            raise RuntimeError("payment_id is required")
        payload: dict[str, Any] = {
            "TerminalKey": str(self._settings.TBANK_TERMINAL_KEY),
            "PaymentId": pid,
        }
        if amount_kopecks is not None:
            payload["Amount"] = int(amount_kopecks)
        payload["Token"] = self._build_token(payload, str(self._settings.TBANK_PASSWORD))
        data = await self._post("Cancel", payload)
        return {
            "success": bool(data.get("Success")),
            "status": str(data.get("Status") or "").strip() or None,
            "payment_id": str(data.get("PaymentId") or "").strip() or pid,
            "error_code": str(data.get("ErrorCode") or "").strip() or None,
            "message": str(data.get("Message") or "").strip() or None,
            "details": str(data.get("Details") or "").strip() or None,
            "raw": data,
        }

    def verify_notification(self, payload: dict[str, Any]) -> bool:
        if not self.is_configured():
            return False
        expected = self._build_token(payload, str(self._settings.TBANK_PASSWORD))
        provided = str(payload.get("Token") or "").strip()
        if not provided:
            return False
        return provided.lower() == expected.lower()

    def _build_receipt(
        self,
        *,
        amount_kopecks: int,
        item_fallback_name: str,
    ) -> dict[str, Any] | None:
        if not bool(self._settings.TBANK_RECEIPT_ENABLED):
            return None
        email = str(self._settings.TBANK_RECEIPT_EMAIL or "").strip()
        phone = str(self._settings.TBANK_RECEIPT_PHONE or "").strip()
        if not email and not phone:
            raise RuntimeError(
                "TBank receipt is enabled but neither TBANK_RECEIPT_EMAIL nor TBANK_RECEIPT_PHONE is set"
            )
        item_name = str(self._settings.TBANK_RECEIPT_ITEM_NAME or "").strip()
        if not item_name:
            item_name = str(item_fallback_name or "VizuAI top-up").strip() or "VizuAI top-up"
        # T-Bank receipt item name is limited, keep it deterministic.
        item_name = item_name[:128]
        item: dict[str, Any] = {
            "Name": item_name,
            "Price": int(amount_kopecks),
            "Quantity": 1,
            "Amount": int(amount_kopecks),
            "Tax": str(self._settings.TBANK_RECEIPT_ITEM_TAX or "none"),
        }
        payment_method = str(self._settings.TBANK_RECEIPT_ITEM_PAYMENT_METHOD or "").strip()
        payment_object = str(self._settings.TBANK_RECEIPT_ITEM_PAYMENT_OBJECT or "").strip()
        if payment_method:
            item["PaymentMethod"] = payment_method
        if payment_object:
            item["PaymentObject"] = payment_object
        receipt: dict[str, Any] = {
            "Taxation": str(self._settings.TBANK_RECEIPT_TAXATION or "usn_income"),
            "Items": [item],
        }
        ffd_version = str(self._settings.TBANK_RECEIPT_FFD_VERSION or "").strip()
        if ffd_version:
            receipt["FfdVersion"] = ffd_version
        if email:
            receipt["Email"] = email
        if phone:
            receipt["Phone"] = phone
        return receipt

    async def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        base = str(self._settings.TBANK_API_BASE).rstrip("/")
        url = f"{base}/{method.lstrip('/')}"
        session = await self._get_session()
        async with session.post(url, json=payload) as response:
            if response.status >= 400:
                text = await response.text()
                raise RuntimeError(f"TBank HTTP {response.status}: {text}")
            data = await response.json()
            if not isinstance(data, dict):
                raise RuntimeError("Invalid TBank response")
            return data

    async def _get_session(self) -> aiohttp.ClientSession:
        timeout_seconds = int(self._settings.TBANK_TIMEOUT_SECONDS or 30)
        shared = self.__class__._shared_session
        if (
            shared is not None
            and not shared.closed
            and self.__class__._shared_session_timeout_seconds == timeout_seconds
        ):
            return shared
        async with self.__class__._shared_session_lock:
            shared = self.__class__._shared_session
            if (
                shared is not None
                and not shared.closed
                and self.__class__._shared_session_timeout_seconds == timeout_seconds
            ):
                return shared
            if shared is not None and not shared.closed:
                await shared.close()
            timeout = aiohttp.ClientTimeout(total=timeout_seconds)
            shared = aiohttp.ClientSession(timeout=timeout)
            self.__class__._shared_session = shared
            self.__class__._shared_session_timeout_seconds = timeout_seconds
            return shared

    @classmethod
    async def close_shared_session(cls) -> None:
        async with cls._shared_session_lock:
            if cls._shared_session is not None and not cls._shared_session.closed:
                await cls._shared_session.close()
            cls._shared_session = None
            cls._shared_session_timeout_seconds = None

    @staticmethod
    def _build_token(payload: dict[str, Any], password: str) -> str:
        parts: dict[str, str] = {}
        for key, value in payload.items():
            if key == "Token":
                continue
            if isinstance(value, (dict, list, tuple, set)):
                continue
            parts[str(key)] = TBankAcquiringService._stringify_for_token(value)
        parts["Password"] = password
        joined = "".join(parts[key] for key in sorted(parts))
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    @staticmethod
    def _stringify_for_token(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, Decimal):
            if value == value.to_integral():
                return str(int(value))
            return format(value, "f")
        return str(value)
