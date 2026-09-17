"""Idempotency service for critical web actions."""
from __future__ import annotations

import asyncio
import hashlib
import json
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from models.api_idempotency_key_model import ApiIdempotencyKey
from services.db_connection import get_db_session
from utils.time import utcnow


class IdempotencyService:
    async def begin(self, account_id: str, *, scope: str, key: str | None, payload: dict) -> dict:
        return await asyncio.to_thread(
            self._begin_sync,
            account_id,
            scope=scope,
            key=key,
            payload=payload,
        )

    async def complete(self, record_id: str, *, response_status: int, response_body: dict) -> None:
        await asyncio.to_thread(
            self._complete_sync,
            record_id,
            response_status=response_status,
            response_body=response_body,
        )

    async def abandon(self, record_id: str | None) -> None:
        if not record_id:
            return
        await asyncio.to_thread(self._abandon_sync, record_id)

    def _begin_sync(self, account_id: str, *, scope: str, key: str | None, payload: dict) -> dict:
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return {"status": "bypass"}

        account_uuid = UUID(account_id)
        request_hash = _hash_payload(payload)

        with get_db_session() as session:
            existing = (
                session.query(ApiIdempotencyKey)
                .filter(
                    ApiIdempotencyKey.account_id == account_uuid,
                    ApiIdempotencyKey.scope == scope,
                    ApiIdempotencyKey.idempotency_key == normalized_key,
                )
                .with_for_update()
                .first()
            )
            if existing is not None:
                return _resolve_existing(existing, request_hash)

            record = ApiIdempotencyKey(
                account_id=account_uuid,
                scope=scope,
                idempotency_key=normalized_key,
                request_hash=request_hash,
                status="processing",
            )
            session.add(record)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = (
                    session.query(ApiIdempotencyKey)
                    .filter(
                        ApiIdempotencyKey.account_id == account_uuid,
                        ApiIdempotencyKey.scope == scope,
                        ApiIdempotencyKey.idempotency_key == normalized_key,
                    )
                    .first()
                )
                if existing is None:
                    raise
                return _resolve_existing(existing, request_hash)
            session.refresh(record)
            return {
                "status": "started",
                "record_id": str(record.id),
            }

    def _complete_sync(self, record_id: str, *, response_status: int, response_body: dict) -> None:
        with get_db_session() as session:
            record = (
                session.query(ApiIdempotencyKey)
                .filter(ApiIdempotencyKey.id == UUID(record_id))
                .with_for_update()
                .first()
            )
            if record is None:
                return
            record.status = "completed"
            record.response_status = int(response_status)
            record.response_body = json.dumps(response_body, ensure_ascii=True, default=str)
            record.completed_at = utcnow()
            session.commit()

    def _abandon_sync(self, record_id: str) -> None:
        with get_db_session() as session:
            record = (
                session.query(ApiIdempotencyKey)
                .filter(ApiIdempotencyKey.id == UUID(record_id))
                .with_for_update()
                .first()
            )
            if record is None:
                return
            if record.status == "processing":
                session.delete(record)
                session.commit()


def _hash_payload(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolve_existing(record: ApiIdempotencyKey, request_hash: str) -> dict:
    if record.request_hash != request_hash:
        return {"status": "payload_mismatch"}
    if record.status == "completed":
        return {
            "status": "replay",
            "response_status": int(record.response_status or 200),
            "response_body": json.loads(record.response_body or "{}"),
        }
    return {"status": "in_progress"}
