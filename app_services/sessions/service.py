"""Sessions application service scaffold."""
from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import secrets
from datetime import timedelta
from email.utils import parseaddr
from urllib.parse import urlencode

import aiohttp

from app_services.analytics.acquisition_service import bind_web_acquisition_to_account
from config import Settings
from models.account_identity_model import AccountIdentity
from models.account_magic_link_token_model import AccountMagicLinkToken
from models.account_model import Account
from models.account_session_model import AccountSession
from utils.observability import emit_observability_event
from utils.time import utcnow


logger = logging.getLogger("sessions")


def _normalize_locale(locale: str | None) -> str:
    normalized = str(locale or "").strip().lower()
    if normalized.startswith("en"):
        return "en"
    return "ru"


def _normalize_email(email: str) -> str:
    _, parsed = parseaddr(str(email or "").strip())
    return parsed.strip().lower()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _format_magic_link_sender(raw_sender: str) -> str:
    display_name, email = parseaddr(str(raw_sender or "").strip())
    normalized_email = email.strip()
    if not normalized_email:
        return "VizuAI <hello@vizuai.example>"
    if display_name.strip().lower() == "vizuai":
        return f"VizuAI <{normalized_email}>"
    return f"VizuAI <{normalized_email}>"


def _magic_link_subject(locale: str) -> str:
    return "Sign in to VizuAI" if locale == "en" else "Вход в VizuAI"


def _magic_link_reply_to() -> str:
    return "owner@vizuai.example"


def _build_magic_link_text(magic_link_url: str, ttl_minutes: int, locale: str) -> str:
    if locale == "en":
        return (
            "Sign in to VizuAI\n\n"
            "Use this link to sign in:\n"
            f"{magic_link_url}\n\n"
            f"This link is valid for {ttl_minutes} minutes.\n\n"
            "If you did not request sign-in, you can safely ignore this email."
        )

    return (
        "Вход в VizuAI\n\n"
        "Ссылка для входа в VizuAI:\n"
        f"{magic_link_url}\n\n"
        f"Ссылка действует {ttl_minutes} минут.\n\n"
        "Если вы не запрашивали вход, просто игнорируйте это письмо."
    )


def _build_magic_link_html(magic_link_url: str, ttl_minutes: int, locale: str) -> str:
    escaped_url = html.escape(magic_link_url, quote=True)
    is_english = locale == "en"
    html_lang = "en" if is_english else "ru"
    heading = "Sign in to VizuAI" if is_english else "Вход в VizuAI"
    subtitle = (
        "Click the button below to sign in to your account"
        if is_english
        else "Нажмите кнопку ниже, чтобы войти в аккаунт"
    )
    cta = "Open VizuAI" if is_english else "Войти в VizuAI"
    fallback_label = (
        "If the button does not work, use this link:"
        if is_english
        else "Если кнопка не работает, используйте эту ссылку:"
    )
    ttl_label = (
        f"This link is valid for {ttl_minutes} minutes"
        if is_english
        else f"Ссылка действует {ttl_minutes} минут"
    )
    ignore_label = (
        "If you did not request sign-in, you can safely ignore this email"
        if is_english
        else "Если вы не запрашивали вход, просто игнорируйте это письмо"
    )
    return f"""\
<!doctype html>
<html lang="{html_lang}">
  <body style="margin:0;padding:0;background:#f5f3e7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#2c3419;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f5f3e7;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border:1px solid #e7e2cc;border-radius:24px;overflow:hidden;">
            <tr>
              <td style="padding:32px 32px 16px 32px;text-align:center;">
                <div style="font-size:18px;font-weight:700;color:#2c3419;">VizuAI</div>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 8px 32px;text-align:center;">
                <h1 style="margin:0;font-size:28px;line-height:1.2;color:#2c3419;">{heading}</h1>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 24px 32px;text-align:center;">
                <p style="margin:0;font-size:16px;line-height:1.6;color:#5a6b3a;">{subtitle}</p>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 24px 32px;text-align:center;">
                <a href="{escaped_url}" style="display:inline-block;background:#7a8b4a;color:#ffffff;text-decoration:none;font-size:16px;font-weight:600;padding:14px 28px;border-radius:14px;">{cta}</a>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 24px 32px;">
                <p style="margin:0 0 8px 0;font-size:14px;line-height:1.6;color:#5a6b3a;">{fallback_label}</p>
                <p style="margin:0;word-break:break-all;font-size:14px;line-height:1.6;">
                  <a href="{escaped_url}" style="color:#7a8b4a;text-decoration:underline;">{escaped_url}</a>
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:0 32px 32px 32px;border-top:1px solid #e7e2cc;">
                <p style="margin:24px 0 8px 0;font-size:13px;line-height:1.6;color:#6b7280;">{ttl_label}</p>
                <p style="margin:0;font-size:13px;line-height:1.6;color:#6b7280;">{ignore_label}</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


class SessionsService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def start_magic_link(self, email: str, *, locale: str | None = None) -> dict:
        normalized_email = _normalize_email(email)
        if not normalized_email:
            emit_observability_event(
                logger,
                "auth_magic_link_invalid_email",
                level="warning",
                email=str(email or "").strip()[:128] or None,
            )
            return {"status": "invalid_email"}
        preferred_locale = _normalize_locale(locale)
        token = secrets.token_urlsafe(32)
        magic_link_url = self._build_magic_link_url(token, preferred_locale)
        await asyncio.to_thread(self._create_magic_link_token_sync, normalized_email, token)
        await self._send_magic_link_email(normalized_email, magic_link_url, preferred_locale)
        return {"status": "magic_link_sent"}

    async def verify_magic_link(
        self,
        token: str,
        *,
        anon_id: str | None = None,
        acquisition: dict[str, object] | None = None,
        locale: str | None = None,
    ) -> dict:
        return await asyncio.to_thread(
            self._verify_magic_link_sync,
            token,
            anon_id,
            acquisition,
            locale,
        )

    async def logout(self, session_token: str) -> None:
        await asyncio.to_thread(self._logout_sync, session_token)

    async def get_current_session(self, session_token: str) -> dict | None:
        return await asyncio.to_thread(self._get_current_session_sync, session_token)

    def _build_magic_link_url(self, token: str, locale: str | None = None) -> str:
        query = urlencode({"token": token, "lang": _normalize_locale(locale)})
        return f"{self._settings.WEB_APP_URL.rstrip('/')}/login?{query}"

    async def _send_magic_link_email(self, email: str, magic_link_url: str, locale: str) -> None:
        if self._settings.RESEND_API_KEY and self._settings.RESEND_FROM_EMAIL:
            await self._send_magic_link_email_via_resend(email, magic_link_url, locale)
            return

        if self._settings.POSTMARK_SERVER_TOKEN and self._settings.POSTMARK_FROM_EMAIL:
            await self._send_magic_link_email_via_postmark(email, magic_link_url, locale)
            return

        if (
            self._settings.RESEND_API_KEY
            or self._settings.RESEND_FROM_EMAIL
            or self._settings.POSTMARK_SERVER_TOKEN
            or self._settings.POSTMARK_FROM_EMAIL
        ):
            emit_observability_event(
                logger,
                "auth_magic_link_delivery_misconfigured",
                level="warning",
                provider="resend" if (self._settings.RESEND_API_KEY or self._settings.RESEND_FROM_EMAIL) else "postmark",
                resend_api_key_present=bool(self._settings.RESEND_API_KEY),
                resend_from_email_present=bool(self._settings.RESEND_FROM_EMAIL),
                postmark_token_present=bool(self._settings.POSTMARK_SERVER_TOKEN),
                postmark_from_email_present=bool(self._settings.POSTMARK_FROM_EMAIL),
            )
            raise RuntimeError("magic_link_delivery_misconfigured")

        logger.info(
            "magic_link_delivery_log_only email=%s provider=disabled",
            email,
        )

    async def _send_magic_link_email_via_resend(self, email: str, magic_link_url: str, locale: str) -> None:
        ttl_minutes = max(int(self._settings.AUTH_MAGIC_LINK_TTL_MINUTES), 1)
        payload = {
            "from": _format_magic_link_sender(str(self._settings.RESEND_FROM_EMAIL or "")),
            "to": [email],
            "subject": _magic_link_subject(locale),
            "reply_to": _magic_link_reply_to(),
            "html": _build_magic_link_html(magic_link_url, ttl_minutes, locale),
            "text": _build_magic_link_text(magic_link_url, ttl_minutes, locale),
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._settings.RESEND_API_KEY}",
        }
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.resend.com/emails",
                json=payload,
                headers=headers,
            ) as response:
                if response.status >= 400:
                    body = await response.text()
                    emit_observability_event(
                        logger,
                        "auth_magic_link_delivery_failed",
                        level="warning",
                        email=email,
                        provider="resend",
                        provider_status=response.status,
                        provider_body=body[:512],
                    )
                    raise RuntimeError("magic_link_delivery_failed")

    async def _send_magic_link_email_via_postmark(self, email: str, magic_link_url: str, locale: str) -> None:
        if not self._settings.POSTMARK_SERVER_TOKEN or not self._settings.POSTMARK_FROM_EMAIL:
            logger.info(
                "magic_link_delivery_log_only email=%s provider=disabled",
                email,
            )
            return

        payload = {
            "From": self._settings.POSTMARK_FROM_EMAIL,
            "To": email,
            "Subject": _magic_link_subject(locale),
            "TextBody": _build_magic_link_text(
                magic_link_url,
                max(int(self._settings.AUTH_MAGIC_LINK_TTL_MINUTES), 1),
                locale,
            ),
        }
        if self._settings.POSTMARK_MESSAGE_STREAM:
            payload["MessageStream"] = self._settings.POSTMARK_MESSAGE_STREAM

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Postmark-Server-Token": self._settings.POSTMARK_SERVER_TOKEN,
        }
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "https://api.postmarkapp.com/email",
                json=payload,
                headers=headers,
            ) as response:
                if response.status >= 400:
                    body = await response.text()
                    emit_observability_event(
                        logger,
                        "auth_magic_link_delivery_failed",
                        level="warning",
                        email=email,
                        provider="postmark",
                        provider_status=response.status,
                        provider_body=body[:512],
                    )
                    raise RuntimeError("magic_link_delivery_failed")

    def _create_magic_link_token_sync(self, email: str, token: str) -> None:
        from services.db_connection import get_db_session

        now = utcnow()
        expires_at = now + timedelta(minutes=max(int(self._settings.AUTH_MAGIC_LINK_TTL_MINUTES), 1))
        with get_db_session() as session:
            token_row = AccountMagicLinkToken(
                email=email,
                token_hash=_hash_token(token),
                status="pending",
                redirect_path="/dashboard",
                expires_at=expires_at,
                sent_at=now,
            )
            session.add(token_row)
            session.commit()

    def _verify_magic_link_sync(
        self,
        token: str,
        anon_id: str | None = None,
        acquisition: dict[str, object] | None = None,
        locale: str | None = None,
    ) -> dict:
        from services.db_connection import get_db_session

        now = utcnow()
        token_hash = _hash_token(token)
        preferred_locale = _normalize_locale(locale)
        with get_db_session() as session:
            token_row = (
                session.query(AccountMagicLinkToken)
                .filter(AccountMagicLinkToken.token_hash == token_hash)
                .with_for_update()
                .first()
            )
            if token_row is None:
                emit_observability_event(
                    logger,
                    "auth_magic_link_rejected",
                    level="warning",
                    reason="token_not_found",
                )
                return {"status": "invalid_or_expired"}
            if token_row.status != "pending" or token_row.expires_at <= now:
                if token_row.status == "pending" and token_row.expires_at <= now:
                    token_row.status = "expired"
                    session.commit()
                    reject_reason = "expired"
                else:
                    reject_reason = f"status_{token_row.status}"
                emit_observability_event(
                    logger,
                    "auth_magic_link_rejected",
                    level="warning",
                    reason=reject_reason,
                    account_id=str(token_row.account_id) if token_row.account_id else None,
                )
                return {"status": "invalid_or_expired"}

            normalized_email = _normalize_email(token_row.email)
            identity = (
                session.query(AccountIdentity)
                .filter(
                    AccountIdentity.provider == "email",
                    AccountIdentity.provider_user_id == normalized_email,
                )
                .first()
            )
            if identity is None:
                account = Account(
                    status="active",
                    primary_email=normalized_email,
                    locale=preferred_locale,
                )
                session.add(account)
                session.flush()
                identity = AccountIdentity(
                    account_id=account.id,
                    provider="email",
                    provider_user_id=normalized_email,
                    provider_email=normalized_email,
                    is_primary=True,
                    is_verified=True,
                )
                session.add(identity)
            else:
                account = identity.account
                if not account.primary_email:
                    account.primary_email = normalized_email
                if preferred_locale and account.locale != preferred_locale:
                    account.locale = preferred_locale

            raw_session_token = secrets.token_urlsafe(48)
            expires_at = now + timedelta(days=max(int(self._settings.AUTH_SESSION_TTL_DAYS), 1))
            account.last_seen_at = now
            session_row = AccountSession(
                account_id=account.id,
                session_token_hash=_hash_token(raw_session_token),
                status="active",
                expires_at=expires_at,
                last_seen_at=now,
            )
            bind_web_acquisition_to_account(
                session,
                account_id=account.id,
                anon_id=anon_id,
                acquisition=acquisition,
            )
            token_row.account_id = account.id
            token_row.status = "used"
            token_row.used_at = now
            session.add(session_row)
            session.commit()
            session.refresh(account)
            session.refresh(session_row)

            return {
                "status": "ok",
                "raw_session_token": raw_session_token,
                "session_expires_at": session_row.expires_at,
                "account": {
                    "id": str(account.id),
                    "email": account.primary_email or normalized_email,
                    "display_name": account.display_name,
                    "locale": account.locale,
                    "timezone": account.timezone,
                    "created_at": account.created_at,
                    "last_seen_at": account.last_seen_at,
                },
            }

    def _get_current_session_sync(self, session_token: str) -> dict | None:
        from services.db_connection import get_db_session

        if not session_token:
            return None
        now = utcnow()
        token_hash = _hash_token(session_token)
        touch_interval_seconds = max(int(self._settings.AUTH_SESSION_TOUCH_INTERVAL_SECONDS or 0), 0)
        with get_db_session() as session:
            session_row = (
                session.query(AccountSession)
                .filter(AccountSession.session_token_hash == token_hash)
                .first()
            )
            if session_row is None:
                return None
            if session_row.status != "active" or session_row.expires_at <= now:
                emit_observability_event(
                    logger,
                    "auth_session_rejected",
                    level="warning",
                    reason="expired" if session_row.expires_at <= now else f"status_{session_row.status}",
                    account_id=str(session_row.account_id) if session_row.account_id else None,
                    session_id=str(session_row.id),
                )
                return None
            account = session_row.account
            should_touch = (
                session_row.last_seen_at is None
                or touch_interval_seconds <= 0
                or (now - session_row.last_seen_at).total_seconds() >= touch_interval_seconds
            )
            if should_touch:
                session_row.last_seen_at = now
                session_row.expires_at = now + timedelta(days=max(int(self._settings.AUTH_SESSION_TTL_DAYS), 1))
                account.last_seen_at = now
                session.commit()
                session.refresh(account)
                session.refresh(session_row)
            return {
                "account": {
                    "id": str(account.id),
                    "email": account.primary_email,
                    "display_name": account.display_name,
                    "locale": account.locale,
                    "timezone": account.timezone,
                    "created_at": account.created_at,
                    "last_seen_at": account.last_seen_at,
                },
                "session": {
                    "id": str(session_row.id),
                    "expires_at": session_row.expires_at,
                },
                "balance": {"credits": 0},
            }

    def _logout_sync(self, session_token: str) -> None:
        from services.db_connection import get_db_session

        if not session_token:
            return
        token_hash = _hash_token(session_token)
        now = utcnow()
        with get_db_session() as session:
            session_row = (
                session.query(AccountSession)
                .filter(AccountSession.session_token_hash == token_hash)
                .first()
            )
            if session_row is None:
                return
            session_row.status = "revoked"
            session_row.revoked_at = now
            session.commit()
