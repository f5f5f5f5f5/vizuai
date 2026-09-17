"""Telegram bot handlers and FSM flow."""
from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from dataclasses import dataclass
from io import BytesIO
import logging
import re
import time
from typing import Any, Protocol
from typing import TYPE_CHECKING

from aiogram import Bot, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    MenuButtonCommands,
    PreCheckoutQuery,
    ReplyKeyboardRemove,
    User as TelegramUser,
)
from redis.asyncio import Redis

from services.redis_client import RuntimeStateClient
from services.tbank_acquiring import TBankAcquiringService
from services.whitelist_service import WhitelistService

if TYPE_CHECKING:  # pragma: no cover
    from config import Settings


logger = logging.getLogger("telegram_bot")

MODE_RENDER_ONLY = "render_only"
MODE_FURNITURE_SEARCH = "furniture_search"

UNITS_BY_MODE = {
    MODE_RENDER_ONLY: 10,
    MODE_FURNITURE_SEARCH: 1,
}
FLOW_TIMEOUT_SECONDS_DEFAULT = 15 * 60
CREDIT_SYMBOL = "🎟️"
STARS_CURRENCY = "XTR"
STARS_PROVIDER = "telegram_stars"
TBANK_PROVIDER = "tbank_sbp"
INVOICE_KIND_CREDITS = "credits_pack"
INVOICE_VERSION = 4
SUPPORTED_INVOICE_VERSIONS = {1, 2, 3, INVOICE_VERSION}
NO_WISHES_SENTINEL = "__NO_WISHES__"
CALLBACK_PREFIX = "ui"
CALLBACK_MENU_TTL_SECONDS = 24 * 60 * 60
STYLE_REF_CAPTURE_KEY = "capture_style_reference"
PROMO_CAPTURE_KEY = "capture_promo_code"
PAYMENT_METHOD_KEY = "payment_method"
PROMO_RESERVATION_TTL_SECONDS = 60 * 60
LEGAL_PRIVACY_URL = "https://legal.vizuai.example/privacy-policy"
LEGAL_OFFER_URL = "https://legal.vizuai.example/offer"


class PipelineOrchestrator(Protocol):
    async def start_job(
        self,
        chat_id: int,
        photo: bytes,
        text: str,
        style_reference: bytes | None = None,
        mode: str = MODE_RENDER_ONLY,
        units_spent: int = 0,
    ) -> str: ...

    async def poll_job(self, job_id: str) -> tuple[str, bytes | None]: ...


class UserStates(StatesGroup):
    language = State()
    menu = State()
    settings = State()
    confirm_reset = State()
    mode_select = State()
    photo = State()
    text = State()
    packages = State()
    processing = State()
    post_result = State()


@dataclass
class UserPayload:
    photo: bytes | None = None
    text: str | None = None
    style_reference: bytes | None = None
    job_id: str | None = None
    active_jobs: tuple[str, ...] = ()
    last_result_photo: bytes | None = None
    language: str | None = None
    mode: str | None = None
    promocode: str | None = None
    promo_reservation_id: str | None = None
    last_activity_ts: float | None = None


class UserDataStore:
    def __init__(self, redis_url: str | None = None, ttl_seconds: int = 86400) -> None:
        self._ttl_seconds = ttl_seconds
        self._memory: dict[int, UserPayload] = {}
        self._ui_versions: dict[int, int] = {}
        self._redis = Redis.from_url(redis_url, decode_responses=False) if redis_url else None

    async def set_photo(self, chat_id: int, photo: bytes) -> None:
        await self._update(chat_id, photo=photo)

    async def set_text(self, chat_id: int, text: str) -> None:
        await self._update(chat_id, text=text)

    async def set_style_reference(self, chat_id: int, photo: bytes) -> None:
        await self._update(chat_id, style_reference=photo)

    async def set_job_id(self, chat_id: int, job_id: str) -> None:
        await self._update(chat_id, job_id=job_id)

    async def set_last_result_photo(self, chat_id: int, photo: bytes) -> None:
        await self._update(chat_id, last_result_photo=photo)

    async def add_active_job(self, chat_id: int, job_id: str) -> None:
        if not job_id:
            return
        if self._redis:
            await self._redis.sadd(self._active_jobs_key(chat_id), job_id.encode())
            await self._redis.expire(self._active_jobs_key(chat_id), self._ttl_seconds)
            await self._update(chat_id, job_id=job_id)
            return
        payload = await self.get_payload(chat_id)
        jobs = set(payload.active_jobs)
        jobs.add(job_id)
        await self._update(chat_id, job_id=job_id, active_jobs=tuple(sorted(jobs)))

    async def remove_active_job(self, chat_id: int, job_id: str) -> None:
        if not job_id:
            return
        if self._redis:
            active_key = self._active_jobs_key(chat_id)
            await self._redis.srem(active_key, job_id.encode())
            await self._redis.expire(active_key, self._ttl_seconds)
            remaining = await self._redis.scard(active_key)
            if remaining == 0:
                await self._update(chat_id, job_id="")
            return
        payload = await self.get_payload(chat_id)
        jobs = set(payload.active_jobs)
        jobs.discard(job_id)
        next_job_id = payload.job_id if payload.job_id and payload.job_id in jobs else ""
        await self._update(chat_id, job_id=next_job_id, active_jobs=tuple(sorted(jobs)))

    async def set_language(self, chat_id: int, language: str) -> None:
        await self._update(chat_id, language=language)

    async def set_mode(self, chat_id: int, mode: str) -> None:
        await self._update(chat_id, mode=mode)

    async def set_promocode(self, chat_id: int, promocode: str) -> None:
        await self._update(chat_id, promocode=promocode)

    async def set_promo_reservation_id(self, chat_id: int, reservation_id: str | None) -> None:
        await self._update(chat_id, promo_reservation_id=reservation_id or "")

    async def clear_promocode(self, chat_id: int, *, clear_reservation: bool = True) -> None:
        if clear_reservation:
            await self._update(chat_id, promocode="", promo_reservation_id="")
            return
        await self._update(chat_id, promocode="")

    async def touch(self, chat_id: int) -> None:
        await self._update(chat_id)

    async def get_language(self, chat_id: int) -> str:
        payload = await self.get_payload(chat_id)
        return _resolve_lang(payload.language)

    async def get_payload(self, chat_id: int) -> UserPayload:
        if self._redis:
            raw = await self._redis.hgetall(self._key(chat_id))
            active_raw = await self._redis.smembers(self._active_jobs_key(chat_id))
            return UserPayload(
                photo=raw.get(b"photo"),
                text=raw.get(b"text", b"").decode() if raw.get(b"text") else None,
                style_reference=raw.get(b"style_reference"),
                job_id=raw.get(b"job_id", b"").decode() if raw.get(b"job_id") else None,
                active_jobs=tuple(
                    sorted(
                        value.decode("utf-8", errors="ignore")
                        for value in active_raw
                        if value
                    )
                ),
                last_result_photo=raw.get(b"last_result_photo"),
                language=raw.get(b"language", b"").decode() if raw.get(b"language") else None,
                mode=raw.get(b"mode", b"").decode() if raw.get(b"mode") else None,
                promocode=raw.get(b"promocode", b"").decode() if raw.get(b"promocode") else None,
                promo_reservation_id=(
                    raw.get(b"promo_reservation_id", b"").decode()
                    if raw.get(b"promo_reservation_id")
                    else None
                ),
                last_activity_ts=(
                    float(raw.get(b"last_activity_ts", b"0").decode())
                    if raw.get(b"last_activity_ts")
                    else None
                ),
            )
        return self._memory.get(chat_id, UserPayload())

    async def clear(self, chat_id: int) -> None:
        if self._redis:
            await self._redis.delete(self._key(chat_id))
            await self._redis.delete(self._active_jobs_key(chat_id))
            await self._redis.delete(self._ui_version_key(chat_id))
        self._memory.pop(chat_id, None)
        self._ui_versions.pop(chat_id, None)

    async def bump_ui_version(self, chat_id: int) -> int:
        if self._redis:
            value = await self._redis.incr(self._ui_version_key(chat_id))
            await self._redis.expire(self._ui_version_key(chat_id), self._ttl_seconds)
            return int(value)
        next_value = int(self._ui_versions.get(chat_id, 0)) + 1
        self._ui_versions[chat_id] = next_value
        return next_value

    async def get_ui_version(self, chat_id: int) -> int:
        if self._redis:
            raw = await self._redis.get(self._ui_version_key(chat_id))
            if not raw:
                return 0
            try:
                return int(raw.decode() if isinstance(raw, bytes) else raw)
            except Exception:
                return 0
        return int(self._ui_versions.get(chat_id, 0))

    async def clear_flow_payload(
        self,
        chat_id: int,
        *,
        clear_photo: bool = True,
        clear_text: bool = True,
        clear_style_reference: bool = False,
        clear_job_id: bool = True,
        clear_mode: bool = False,
    ) -> None:
        now_ts = self._now_ts()
        if self._redis:
            fields: list[bytes] = []
            if clear_photo:
                fields.append(b"photo")
            if clear_text:
                fields.append(b"text")
            if clear_style_reference:
                fields.append(b"style_reference")
            if clear_job_id:
                fields.append(b"job_id")
            if clear_mode:
                fields.append(b"mode")
            if fields:
                await self._redis.hdel(self._key(chat_id), *fields)
            await self._redis.hset(
                self._key(chat_id),
                mapping={b"last_activity_ts": str(now_ts).encode()},
            )
            await self._redis.expire(self._key(chat_id), self._ttl_seconds)
            return

        payload = self._memory.get(chat_id, UserPayload())
        if clear_photo:
            payload.photo = None
        if clear_text:
            payload.text = None
        if clear_style_reference:
            payload.style_reference = None
        if clear_job_id:
            payload.job_id = None
        if clear_mode:
            payload.mode = None
        payload.last_activity_ts = now_ts
        self._memory[chat_id] = payload

    async def _update(
        self,
        chat_id: int,
        photo: bytes | None = None,
        text: str | None = None,
        style_reference: bytes | None = None,
        job_id: str | None = None,
        active_jobs: tuple[str, ...] | None = None,
        last_result_photo: bytes | None = None,
        language: str | None = None,
        mode: str | None = None,
        promocode: str | None = None,
        promo_reservation_id: str | None = None,
    ) -> None:
        now_ts = self._now_ts()
        if self._redis:
            mapping: dict[bytes, bytes] = {}
            if photo is not None:
                mapping[b"photo"] = photo
            if text is not None:
                mapping[b"text"] = text.encode()
            if style_reference is not None:
                mapping[b"style_reference"] = style_reference
            if job_id is not None:
                mapping[b"job_id"] = job_id.encode()
            if last_result_photo is not None:
                mapping[b"last_result_photo"] = last_result_photo
            if language is not None:
                mapping[b"language"] = language.encode()
            if mode is not None:
                mapping[b"mode"] = mode.encode()
            if promocode is not None:
                mapping[b"promocode"] = promocode.encode()
            if promo_reservation_id is not None:
                mapping[b"promo_reservation_id"] = promo_reservation_id.encode()
            mapping[b"last_activity_ts"] = str(now_ts).encode()
            await self._redis.hset(self._key(chat_id), mapping=mapping)
            await self._redis.expire(self._key(chat_id), self._ttl_seconds)
            if active_jobs is not None:
                active_key = self._active_jobs_key(chat_id)
                await self._redis.delete(active_key)
                if active_jobs:
                    await self._redis.sadd(
                        active_key,
                        *[value.encode() for value in active_jobs if value],
                    )
                await self._redis.expire(active_key, self._ttl_seconds)
            return

        payload = self._memory.get(chat_id, UserPayload())
        if photo is not None:
            payload.photo = photo
        if text is not None:
            payload.text = text
        if style_reference is not None:
            payload.style_reference = style_reference
        if job_id is not None:
            payload.job_id = job_id
        if active_jobs is not None:
            payload.active_jobs = active_jobs
        if last_result_photo is not None:
            payload.last_result_photo = last_result_photo
        if language is not None:
            payload.language = language
        if mode is not None:
            payload.mode = mode
        if promocode is not None:
            payload.promocode = promocode or None
        if promo_reservation_id is not None:
            payload.promo_reservation_id = promo_reservation_id or None
        payload.last_activity_ts = now_ts
        self._memory[chat_id] = payload

    @staticmethod
    def _key(chat_id: int) -> str:
        return f"user:{chat_id}"

    @staticmethod
    def _active_jobs_key(chat_id: int) -> str:
        return f"user:{chat_id}:active_jobs"

    @staticmethod
    def _ui_version_key(chat_id: int) -> str:
        return f"user:{chat_id}:ui_version"

    @staticmethod
    def _now_ts() -> float:
        return time.time()


LANG_RU = "ru"
LANG_EN = "en"
DEFAULT_LANG = LANG_RU

LANGUAGE_CHOICES = {"Русский": LANG_RU, "English": LANG_EN}

TEXTS: dict[str, dict[str, str]] = {
    "main_menu": {LANG_RU: "🏠 Меню", LANG_EN: "🏠 Menu"},
    "design_menu": {LANG_RU: "🎨 Сделать дизайн", LANG_EN: "🎨 Create design"},
    "settings_menu": {LANG_RU: "⚙️ Настройки", LANG_EN: "⚙️ Settings"},
    "mode_render_only": {LANG_RU: "🏠 Дизайн комнаты • 10🎟️", LANG_EN: "🏠 Room design • 10🎟️"},
    "mode_furniture_search": {LANG_RU: "🛋 Поиск мебели • 1🎟️", LANG_EN: "🛋 Furniture search • 1🎟️"},
    "packages_menu": {LANG_RU: "⭐ Баланс", LANG_EN: "⭐ Balance"},
    "topup_method_stars": {LANG_RU: "⭐ Telegram Stars", LANG_EN: "⭐ Telegram Stars"},
    "topup_method_tbank": {LANG_RU: "🏦 СБП ₽", LANG_EN: "🏦 SBP ₽"},
    "help_menu": {LANG_RU: "❓ Помощь", LANG_EN: "❓ Help"},
    "language_menu": {LANG_RU: "🌐 Язык", LANG_EN: "🌐 Language"},
    "settings_reset_flow": {LANG_RU: "♻️ Сбросить сценарий…", LANG_EN: "♻️ Reset flow…"},
    "start_process": {LANG_RU: "▶️ Сгенерировать", LANG_EN: "▶️ Generate"},
    "start_process_furniture": {LANG_RU: "🔎 Найти мебель", LANG_EN: "🔎 Find furniture"},
    "edit_request": {LANG_RU: "📝 Изменить описание", LANG_EN: "📝 Edit description"},
    "refine_request": {LANG_RU: "📝 Уточнить", LANG_EN: "📝 Refine"},
    "new_photo": {LANG_RU: "📷 Изменить фото", LANG_EN: "📷 Edit photo"},
    "post_new_photo": {LANG_RU: "📷 Новое фото", LANG_EN: "📷 New photo"},
    "retry_variant": {LANG_RU: "🔁 Ещё вариант", LANG_EN: "🔁 Another variant"},
    "edit_from_result": {LANG_RU: "🛠️ Изменить", LANG_EN: "🛠️ Edit"},
    "cancel": {LANG_RU: "↩️ Назад", LANG_EN: "↩️ Back"},
    "back": {LANG_RU: "↩️ Назад", LANG_EN: "↩️ Back"},
    "reset_confirm_yes": {LANG_RU: "✅ Да, сбросить", LANG_EN: "✅ Yes, reset"},
    "reset_confirm_cancel": {LANG_RU: "↩️ Отмена", LANG_EN: "↩️ Cancel"},
    "no_wishes": {LANG_RU: "Без пожеланий", LANG_EN: "No preferences"},
    "no_wishes_value": {LANG_RU: "Без пожеланий", LANG_EN: "No preferences"},
    "choose_language_menu": {
        LANG_RU: "Выбери язык интерфейса.",
        LANG_EN: "Choose interface language.",
    },
    "language_updated": {
        LANG_RU: "Язык обновил.",
        LANG_EN: "Language updated.",
    },
    "language_invalid": {
        LANG_RU: "Пожалуйста, выбери язык кнопкой ниже.",
        LANG_EN: "Please choose a language using the buttons below.",
    },
    "greeting": {
        LANG_RU: (
            "Помогаю с интерьером по фото\n\n"
            "🏠 Дизайн комнаты\n"
            "Изменю текущий интерьер или создам новый по твоему запросу\n\n"
            "🛋️ Мебель по фото\n"
            "Найду похожую мебель на маркетплейсах (Ozon, WB, YM)\n\n"
            "Нажми «🎨 Сделать дизайн», чтобы выбрать режим\n\n"
            "Если найдешь ошибку или захочешь что-то предложить:\n"
            "t.me/vizuai_app?direct"
        ),
        LANG_EN: (
            "I help with interiors from photos\n\n"
            "🏠 Room design\n"
            "I can update the current interior or create a new one based on your request\n\n"
            "🛋️ Furniture by photo\n"
            "I can find similar furniture on marketplaces (Ozon, WB, YM)\n\n"
            "Tap “🎨 Create design” to choose a mode\n\n"
            "If you find a bug or want to suggest something:\n"
            "t.me/vizuai_app?direct"
        ),
    },
    "start_text": {
        LANG_RU: (
            "Что я умею?\n\n"
            "🏠 <b>Дизайн комнаты</b>\n"
            "Изменю текущий интерьер или создам новый по твоему запросу\n\n"
            "🛋️ <b>Мебель по фото</b>\n"
            "Найду похожую мебель на маркетплейсах (Ozon, WB, YM)\n\n"
            "Нажми «🎨 <b>Сделать дизайн</b>», чтобы выбрать режим\n\n"
            "Делимся обновлениями, акциями и бонусами в канале:\n"
            "t.me/vizuai_app"
        ),
        LANG_EN: (
            "What can I do?\n\n"
            "🏠 <b>Room design</b>\n"
            "I can update the current interior or create a new one based on your request\n\n"
            "🛋️ <b>Furniture by photo</b>\n"
            "I can find similar furniture on marketplaces (Ozon, WB, YM)\n\n"
            "Tap “🎨 <b>Create design</b>” to choose a mode\n\n"
            "We share updates, promos, and bonuses in the channel:\n"
            "t.me/vizuai_app"
        ),
    },
    "help_text": {
        LANG_RU: (
            "Я делаю редизайн интерьера по фото и ищу мебель на маркетплейсах\n\n"
            "Как работать:\n"
            "1. Нажми «🎨 Сделать дизайн» и выбери режим\n"
            "2. Отправь фото комнаты (можно сразу с текстом в подписи)\n"
            "3. При необходимости добавь текстовый запрос (что хочешь сделать)\n\n"
            "Советы к запросу:\n"
            "- Укажи тип комнаты (кухня-гостиная / спальня / детская и т.д.)\n"
            "- Можешь указать желаемый стиль (сканди / japandi / лофт и т.д.)\n"
            "- Можешь указать состояние комнаты (черновая/чистовая/white box)\n"
            "\n"
            "Что ты получишь:\n"
            "- 🏠 Дизайн комнаты: финальный рендер\n"
            "- 🛋️ Мебель по фото: ссылки на товары по найденным предметам\n\n"
            "Мы не сможем обработать запрос, если:\n"
            "1) На фото не интерьер (не комната)\n"
            "2) Фото слишком плохого качества (слишком темно, размыто, не видно деталей комнаты)\n"
            "3) На фото есть чувствительный/запрещенный контент\n"
            "4) Запрос нарушает правила сервиса (просит запрещенные изменения или контент)\n\n"
            "Обратная связь:\n"
            "https://example.com/support"
        ),
        LANG_EN: (
            "I create room design from your photo and find furniture on marketplaces\n\n"
            "How to use:\n"
            "1. Tap “🎨 Create design” and pick a mode\n"
            "2. Send a room photo (you can add text in the caption)\n"
            "3. Add text request if needed (what you want to change)\n\n"
            "Prompt tips:\n"
            "- Specify room type (kitchen-living / bedroom / kids room, etc.)\n"
            "- You can specify desired style (scandi / japandi / loft, etc.)\n"
            "- You can specify room condition (unfinished / finished / white box)\n"
            "\n"
            "What you get:\n"
            "- 🏠 Room design: final render\n"
            "- 🛋️ Furniture by photo: links to products for found items\n\n"
            "We can't process the request if:\n"
            "1) The photo is not an interior/room\n"
            "2) The photo quality is too low (too dark, blurry, room details are not visible)\n"
            "3) The photo contains sensitive/prohibited content\n"
            "4) The request violates service rules (asks for prohibited edits or content)\n\n"
            "Feedback:\n"
            "https://example.com/support"
        ),
    },
    "canceled": {
        LANG_RU: "Ок, отменил. Можем начать заново в любой момент.",
        LANG_EN: "Canceled. You can start again anytime.",
    },
    "reset_done": {
        LANG_RU: "Сбросил текущий сценарий. Можно начать заново.",
        LANG_EN: "Current flow has been reset. You can start again.",
    },
    "reset_timeout": {
        LANG_RU: "Была длинная пауза, поэтому я сбросил незавершенный сценарий. Начнем заново.",
        LANG_EN: "There was a long pause, so I reset the unfinished flow. Let's start over.",
    },
    "detached_result_ready": {
        LANG_RU: "Результат по предыдущему запросу готов\nОтправляю его ниже",
        LANG_EN: "Your previous request is ready\nSending it below",
    },
    "detached_result_failed": {
        LANG_RU: "Предыдущий запрос завершился с ошибкой\nЕсли хочешь, запусти его еще раз",
        LANG_EN: "Your previous request ended with an error\nYou can start it again if you want",
    },
    "menu_prompt": {
        LANG_RU: "<b>VizuAI</b>\nРедизайн интерьера по фото и поиск мебели\nНажми «Сделать дизайн» — выберешь режим",
        LANG_EN: "<b>VizuAI</b>\nInterior design from photo and furniture search\nTap “Create design” to choose a mode",
    },
    "settings_prompt": {
        LANG_RU: "Настройки. Что изменить?",
        LANG_EN: "Settings. What do you want to change?",
    },
    "reset_confirm_prompt": {
        LANG_RU: "Точно сбросить текущий сценарий? Если обработка уже запущена, результат будет отвязан.",
        LANG_EN: "Reset current flow? If processing is already running, the result will be detached.",
    },
    "ask_photo": {
        LANG_RU: "Пришли фото комнаты.",
        LANG_EN: "Send a room photo.",
    },
    "ask_mode": {
        LANG_RU: (
            "Выбери режим:\n\n"
            "<b>🏠 Дизайн комнаты • 10🎟️</b>\n"
            "Создам готовый интерьер из комнаты в любом состоянии по твоему запросу\n\n"
            "<b>🛋 Поиск мебели • 1🎟️</b>\n"
            "Отмечу предметы на твоем фото и пришлю ссылки на похожие товары (WB, Ozon, Яндекс Маркет)"
        ),
        LANG_EN: (
            "Choose a mode:\n\n"
            "<b>🏠 Room design • 10🎟️</b>\n"
            "I will create a finished interior from a room in any condition based on your request\n\n"
            "<b>🛋 Furniture search • 1🎟️</b>\n"
            "I will mark items in your photo and send links to similar products (WB, Ozon, Yandex Market)"
        ),
    },
    "ask_photo_furniture": {
        LANG_RU: "Отправь фото, объекты из которого хочешь найти",
        LANG_EN: "Send a photo with objects you want me to find",
    },
    "new_photo_prompt": {
        LANG_RU: "Отправь фото комнаты, которую хочешь изменить",
        LANG_EN: "Send a photo of the room you want to redesign",
    },
    "new_photo_prompt_furniture": {
        LANG_RU: "Отправь фото, объекты из которого хочешь найти",
        LANG_EN: "Send a photo with objects you want me to find",
    },
    "edit_request_prompt": {
        LANG_RU: "Опиши, что хочешь изменить",
        LANG_EN: "Describe what you want to change",
    },
    "edit_from_result_missing": {
        LANG_RU: "Не нашел предыдущий рендер. Отправь фото комнаты, которую хочешь изменить",
        LANG_EN: "I couldn't find the previous render. Send a photo of the room you want to redesign",
    },
    "help_root_text": {
        LANG_RU: "<b>Помощь</b>\nВыбери раздел\n\nЕсть идеи или баг? Напиши в поддержку: t.me/vizuai_app?direct",
        LANG_EN: "<b>Help</b>\nChoose a section\n\nGot ideas or found a bug? Contact support: t.me/vizuai_app?direct",
    },
    "help_examples_text": {
        LANG_RU: (
            "<b>Примеры запросов</b>\n"
            "Примеры (можно копировать):\n\n"
            "• Спальня, современная классика, теплее свет, спокойные стены, кровать не менять\n"
            "• Прихожая, современный стиль, больше хранения для обуви/верхней одежды, зеркало оставить\n"
            "• white box студия, современный стиль, светлое дерево и теплый свет, нужна кухня и зона отдыха\n\n"
            "Поиск мебели: просто отправь фото комнаты"
        ),
        LANG_EN: (
            "<b>Prompt examples</b>\n"
            "Examples (you can copy):\n\n"
            "• Bedroom, modern classic, warmer lighting, calm wall colors, keep the bed\n"
            "• Hallway, modern style, more storage for shoes and outerwear, keep the mirror\n"
            "• White-box studio, modern style, light wood and warm light, need kitchen and lounge zones\n\n"
            "Furniture search: just send a room photo"
        ),
    },
    "help_limits_text": {
        LANG_RU: (
            "<b>Ограничения</b>\n"
            "Мы не сможем обработать запрос, если:\n"
            "1) На фото не интерьер (не комната)\n"
            "2) Фото слишком плохого качества: темно/размыто/не видно деталей\n"
            "3) На фото есть чувствительный/запрещенный контент\n"
            "4) Запрос нарушает правила сервиса (просит запрещенные изменения или контент)"
        ),
        LANG_EN: (
            "<b>Limits</b>\n"
            "We can’t process the request if:\n"
            "1) The photo is not an interior (not a room)\n"
            "2) The photo quality is too low: dark/blurry/no visible details\n"
            "3) The photo contains sensitive/prohibited content\n"
            "4) The request violates service rules (asks for prohibited edits/content)"
        ),
    },
    "help_limits_button": {LANG_RU: "⛔ Ограничения", LANG_EN: "⛔ Limits"},
    "help_docs_button": {LANG_RU: "📄 Документы", LANG_EN: "📄 Documents"},
    "help_docs_text": {
        LANG_RU: "<b>Документы</b>\nВыбери документ ниже",
        LANG_EN: "<b>Documents</b>\nChoose a document below",
    },
    "help_docs_privacy_button": {
        LANG_RU: "🔐 Политика конфиденциальности",
        LANG_EN: "🔐 Privacy Policy",
    },
    "help_docs_offer_button": {
        LANG_RU: "📄 Оферта",
        LANG_EN: "📄 Offer",
    },
    "packages_intro": {
        LANG_RU: "⭐ Telegram Stars\nВыбери пакет кредитов.",
        LANG_EN: "⭐ Telegram Stars\nChoose a credit pack.",
    },
    "packages_intro_tbank": {
        LANG_RU: "🏦 СБП ₽\nВыбери пакет кредитов.",
        LANG_EN: "🏦 SBP ₽\nChoose a credit pack.",
    },
    "promo_activate_button": {
        LANG_RU: "🎁 Активировать промокод",
        LANG_EN: "🎁 Activate promo code",
    },
    "promo_activate_prompt": {
        LANG_RU: "Отправь код промокода одним сообщением",
        LANG_EN: "Send promo code in one message",
    },
    "promo_applied": {
        LANG_RU: "Промокод {code} применен, скидка учтется при следующей оплате",
        LANG_EN: "Promo code {code} applied, discount will be used for the next payment",
    },
    "promo_current": {
        LANG_RU: "Текущий промокод: {code}",
        LANG_EN: "Current promo code: {code}",
    },
    "promo_prices_applied": {
        LANG_RU: "Промокод {code} активен\nЦены ниже уже с учетом скидки {discount}",
        LANG_EN: "Promo code {code} is active\nPrices below already include the {discount} discount",
    },
    "promo_invalid": {
        LANG_RU: "Не удалось применить промокод: {reason}",
        LANG_EN: "Couldn't apply promo code: {reason}",
    },
    "promo_invoice_unavailable": {
        LANG_RU: "Промокод сейчас недоступен ({reason}), выбери другой код",
        LANG_EN: "Promo code is unavailable right now ({reason}), choose another code",
    },
    "promo_price_line": {
        LANG_RU: "Промокод {code}: {original}⭐ -> {final}⭐",
        LANG_EN: "Promo {code}: {original}⭐ -> {final}⭐",
    },
    "promo_price_line_rub": {
        LANG_RU: "Промокод {code}: {original}₽ -> {final}₽",
        LANG_EN: "Promo {code}: {original}₽ -> {final}₽",
    },
    "balance_overview": {
        LANG_RU: "Баланс: {balance}\nМожешь выбрать удобный способ пополнения ниже",
        LANG_EN: "Balance: {balance}\nChoose a convenient top-up method below",
    },
    "balance_paywall_render": {
        LANG_RU: (
            "Запрос готов, но для запуска сейчас не хватает баланса\n\n"
            "Чтобы начать генерацию, пополни баланс минимум на 10 🎟️\n\n"
            "После пополнения нажми на кнопку ▶️ <b>Сгенерировать</b> выше\n\n"
            "Примеры результатов и запросов:\n"
            "{examples_url}"
        ),
        LANG_EN: (
            "Your request is ready, but there is not enough balance to start now\n\n"
            "To start generation, top up at least 10 🎟️\n\n"
            "After top-up, press ▶️ <b>Generate</b> above\n\n"
            "Examples of results and prompts:\n"
            "{examples_url}"
        ),
    },
    "balance_paywall_furniture": {
        LANG_RU: (
            "Запрос готов, но для запуска сейчас не хватает баланса\n\n"
            "Чтобы начать поиск, пополни баланс минимум на 1 🎟️\n\n"
            "После пополнения нажми на кнопку 🔎 <b>Найти мебель</b> выше\n\n"
            "Пример запроса:\n"
            "{examples_url}"
        ),
        LANG_EN: (
            "Your request is ready, but there is not enough balance to start now\n\n"
            "To start search, top up at least 1 🎟️\n\n"
            "After top-up, press 🔎 <b>Find furniture</b> above\n\n"
            "Example prompt:\n"
            "{examples_url}"
        ),
    },
    "render_examples_url": {
        LANG_RU: "t.me/vizuai_app/24",
        LANG_EN: "t.me/vizuai_app/24",
    },
    "furniture_examples_url": {
        LANG_RU: "t.me/vizuai_app/17",
        LANG_EN: "t.me/vizuai_app/17",
    },
    "invoice_title": {
        LANG_RU: "Пакет {amount}🎟️",
        LANG_EN: "Pack {amount}🎟️",
    },
    "invoice_description": {
        LANG_RU: "Пополнение баланса: {amount}🎟️",
        LANG_EN: "Balance top-up: {amount}🎟️",
    },
    "invoice_error": {
        LANG_RU: "Не удалось создать счет, попробуй позже",
        LANG_EN: "Failed to create invoice. Please try again later.",
    },
    "tbank_unavailable": {
        LANG_RU: "СБП пока недоступна, попробуй позже",
        LANG_EN: "SBP is unavailable right now, please try later",
    },
    "tbank_payment_created": {
        LANG_RU: "Счет создан: {amount}🎟️ за {rub}₽\nНажми кнопку ниже, чтобы оплатить",
        LANG_EN: "Payment link created: {amount}🎟️ for {rub}₽\nPress the button below to pay",
    },
    "tbank_package_selected": {
        LANG_RU: "Пакет: {amount}🎟️ за {rub}₽",
        LANG_EN: "Pack: {amount}🎟️ for {rub}₽",
    },
    "tbank_package_selected_discounted": {
        LANG_RU: "Пакет: {amount}🎟️ за {rub}₽ (промокод {code})",
        LANG_EN: "Pack: {amount}🎟️ for {rub}₽ (promo {code})",
    },
    "tbank_payment_button": {
        LANG_RU: "💳 Оплатить через СБП",
        LANG_EN: "💳 Pay via SBP",
    },
    "package_selected": {
        LANG_RU: "Пакет: {amount}🎟️ за {stars}⭐",
        LANG_EN: "Pack: {amount}🎟️ for {stars}⭐",
    },
    "package_selected_discounted": {
        LANG_RU: "Пакет: {amount}🎟️ за {stars}⭐ (промокод {code})",
        LANG_EN: "Pack: {amount}🎟️ for {stars}⭐ (promo {code})",
    },
    "payment_success": {
        LANG_RU: "Оплата прошла. Зачислено: {credits}🎟️. Доступно: {remaining}.",
        LANG_EN: "Payment successful. Added: {credits}🎟️. Available: {remaining}.",
    },
    "payment_duplicate": {
        LANG_RU: "Этот платеж уже обработан, баланс обновлен",
        LANG_EN: "This payment has already been processed, balance is updated",
    },
    "payment_invalid": {
        LANG_RU: "Не удалось обработать платеж автоматически, напиши в поддержку по оплате",
        LANG_EN: "Couldn't process this payment automatically contact payment support",
    },
    "payment_check_failed": {
        LANG_RU: "Оплата не прошла проверку, выбери пакет заново и попробуй еще раз",
        LANG_EN: "Payment did not pass validation, choose a package again and try one more time",
    },
    "paysupport_text": {
        LANG_RU: (
            "Поддержка по оплате\n"
            "Контакт: t.me/vizuai_app?direct\n"
            "Время ответа: обычно до 2 часов, максимум 24 часа\n"
            "Пришли в одном сообщении:\n"
            "- user_id\n"
            "- время оплаты\n"
            "- пакет/сумму\n"
            "- скрин чека/инвойса\n"
            "- что пошло не так\n"
            "Если ошибка на нашей стороне и результат не доставлен, сделаем возврат"
        ),
        LANG_EN: (
            "Payment support\n"
            "Contact: t.me/vizuai_app?direct\n"
            "Response time: usually within 2 hours, up to 24 hours max\n"
            "Send in one message:\n"
            "- user_id\n"
            "- payment time\n"
            "- package/amount\n"
            "- invoice/receipt screenshot\n"
            "- what went wrong\n"
            "If the issue is on our side and the result was not delivered, we will issue a refund"
        ),
    },
    "cabinet_title": {LANG_RU: "👤 Профиль", LANG_EN: "👤 Profile"},
    "cabinet_remaining": {LANG_RU: "Баланс: {value}", LANG_EN: "Balance: {value}"},
    "cabinet_used": {LANG_RU: "Потрачено: {value}", LANG_EN: "Spent: {value}"},
    "cabinet_last_request": {LANG_RU: "Последний запрос: {value}", LANG_EN: "Last request: {value}"},
    "cabinet_access": {LANG_RU: "Статус доступа: {value}", LANG_EN: "Access status: {value}"},
    "cabinet_tip": {
        LANG_RU: "Совет: чем точнее запрос, тем лучше результат.",
        LANG_EN: "Tip: the more specific the prompt, the better the result.",
    },
    "access_active": {LANG_RU: "Активен", LANG_EN: "Active"},
    "access_denied": {LANG_RU: "Нет доступа ({reason})", LANG_EN: "No access ({reason})"},
    "start_denied": {
        LANG_RU: "Сейчас запуск недоступен ({reason}). Открой «⭐ Баланс».",
        LANG_EN: "Launch is unavailable now ({reason}). Open ⭐ Balance.",
    },
    "start_processing": {
        LANG_RU: "Обработка запущена, верну результат через несколько минут",
        LANG_EN: "Processing started, I will return the result in a few minutes",
    },
    "processing_busy": {
        LANG_RU: "Сейчас уже идет обработка предыдущего запроса. Дождись завершения.",
        LANG_EN: "A previous request is still processing. Please wait until it finishes.",
    },
    "start_processing_units": {
        LANG_RU: "Списано: {units}🎟️",
        LANG_EN: "Charged: {units}🎟️",
    },
    "start_processing_style_ref": {
        LANG_RU: "Использую стиль с референса ✅",
        LANG_EN: "Using style reference ✅",
    },
    "failed_next": {
        LANG_RU: "Не смог обработать твой запрос, напиши в поддержку t.me/vizuai_app?direct",
        LANG_EN: "I couldn't process your request, contact support t.me/vizuai_app?direct",
    },
    "ready_step": {
        LANG_RU: "Готово к запуску.",
        LANG_EN: "Ready to launch.",
    },
    "ready_mode": {LANG_RU: "Режим: {value}", LANG_EN: "Mode: {value}"},
    "ready_cost": {LANG_RU: "Стоимость: {value}", LANG_EN: "Cost: {value}"},
    "compose_balance": {LANG_RU: "Баланс: {value}", LANG_EN: "Balance: {value}"},
    "ready_photo": {LANG_RU: "Фото: {value}", LANG_EN: "Photo: {value}"},
    "ready_text": {LANG_RU: "Описание: {value}", LANG_EN: "Description: {value}"},
    "photo_download_error": {
        LANG_RU: "Не получилось скачать фото. Отправь его еще раз.",
        LANG_EN: "Couldn't download the photo. Please send it again.",
    },
    "photo_store_error": {
        LANG_RU: "Не получилось сохранить фото. Отправь его еще раз.",
        LANG_EN: "Couldn't save the photo. Please send it again.",
    },
    "render_compose_title": {
        LANG_RU: "🏠 Дизайн комнаты",
        LANG_EN: "🏠 Room design",
    },
    "render_compose_intro": {
        LANG_RU: "Пришли мне одно фото комнаты и напиши, что хочешь сделать",
        LANG_EN: "Send me a room photo and describe what you want to change",
    },
    "render_compose_guidance": {
        LANG_RU: "Для лучшего результата: тип комнаты, ее состояние, что хочешь изменить",
        LANG_EN: "For best results: room type, room condition, and what you want to change",
    },
    "render_compose_intro_photo_only": {
        LANG_RU: "Фото получил, напиши, что хочешь изменить",
        LANG_EN: "Got the photo, now describe what you want to change",
    },
    "render_compose_intro_text_only": {
        LANG_RU: "Описание получил, отправь фото, которое хочешь изменить",
        LANG_EN: "Got the description, now send the photo you want to change",
    },
    "render_compose_intro_ready": {
        LANG_RU: "Фото и описание получил, можешь запускать или изменить что-то ниже",
        LANG_EN: "Got the photo and description, you can start now or change something below",
    },
    "render_compose_zero_balance_intro": {
        LANG_RU: "Подготовь запрос на редизайн комнаты: добавь фото и опиши, что хочешь изменить",
        LANG_EN: "Prepare a room redesign request: add a photo and describe what you want to change",
    },
    "render_compose_zero_balance_examples": {
        LANG_RU: "Запрос все равно можно подготовить заранее, а запустить после пополнения\n\nПримеры готовых результатов и запросов:\n{examples_url}",
        LANG_EN: "You can prepare the request now and launch it after top-up\n\nExamples of finished results and prompts:\n{examples_url}",
    },
    "render_compose_style_optional_hint": {
        LANG_RU: "Если у тебя есть фото, которое хочешь использовать, как стиль, нажми на 🎨 Стиль по фото, чтобы его добавить",
        LANG_EN: "If you have a photo you want to use as a style reference, tap 🎨 Style reference to add it",
    },
    "render_compose_style_status": {
        LANG_RU: "🎨 {value}",
        LANG_EN: "🎨 {value}",
    },
    "render_compose_photo_button": {
        LANG_RU: "📷 Фото комнаты {status}",
        LANG_EN: "📷 Room photo {status}",
    },
    "render_compose_text_button": {
        LANG_RU: "📝 Описание {status}",
        LANG_EN: "📝 Description {status}",
    },
    "render_compose_style_button": {
        LANG_RU: "🎨 Стиль по фото{status}",
        LANG_EN: "🎨 Style reference{status}",
    },
    "render_compose_style_status_set": {
        LANG_RU: "Стиль по фото добавлен ✅",
        LANG_EN: "Style reference added ✅",
    },
    "render_compose_style_status_optional": {
        LANG_RU: "Стиль по фото не обязателен, добавь если хочешь повторить палитру и настроение",
        LANG_EN: "Style reference is optional, add it if you want to match palette and mood",
    },
    "render_compose_style_remove_button": {
        LANG_RU: "🗑️ Убрать стиль",
        LANG_EN: "🗑️ Remove style",
    },
    "render_compose_retry_hint": {
        LANG_RU: "Оставил то же фото, описание и стиль\n\nЕсли хочешь, можешь сразу запустить еще один вариант или что-то изменить ниже",
        LANG_EN: "I kept the same photo, description, and style reference\n\nYou can generate another variant right away or change something below",
    },
    "render_compose_edit_result_hint": {
        LANG_RU: "Подставил результат как новое фото\n\nТеперь опиши, что хочешь изменить дальше",
        LANG_EN: "I set the result as the new photo\n\nNow describe what you want to change next",
    },
    "style_ref_prompt": {
        LANG_RU: "Пришли фото интерьера/стиля, который нравится. Я возьму только стиль (цвета/материалы/свет), не планировку",
        LANG_EN: "Send a style reference photo. I will use only style (colors/materials/lighting), not layout",
    },
    "style_ref_need_photo": {
        LANG_RU: "Для стиля нужен именно фото-референс. Отправь изображение",
        LANG_EN: "Style reference requires a photo. Please send an image",
    },
    "style_ref_received": {
        LANG_RU: "Стиль-референс получил. Можешь запускать или продолжить редактирование",
        LANG_EN: "Style reference saved. You can generate now or keep editing",
    },
    "style_ref_removed": {
        LANG_RU: "Стиль-референс убрал",
        LANG_EN: "Style reference removed",
    },
    "furniture_compose_title": {
        LANG_RU: "🛋️ Поиск мебели",
        LANG_EN: "🛋️ Furniture search",
    },
    "furniture_compose_intro": {
        LANG_RU: "Пришли одно фото комнаты, я отмечу предметы и пришлю ссылки",
        LANG_EN: "Send a room photo, I will mark objects and send links.",
    },
    "furniture_compose_intro_prefilled": {
        LANG_RU: "Добавил сюда фото полученного дизайна, можешь изменить, нажав на кнопку «📷 Фото»",
        LANG_EN: "I added the generated design photo here; you can change it by pressing «📷 Photo»",
    },
    "furniture_compose_zero_balance_intro": {
        LANG_RU: "Добавь фото и отмечу предметы, по которым можно искать похожие товары",
        LANG_EN: "Add a photo and I will mark objects that can be used to search for similar products",
    },
    "furniture_compose_zero_balance_examples": {
        LANG_RU: "Запрос можно подготовить заранее и запустить после пополнения\n\nПример запроса:\n{examples_url}",
        LANG_EN: "You can prepare the request now and launch it after top-up\n\nExample prompt:\n{examples_url}",
    },
    "furniture_compose_guidance": {
        LANG_RU: "Для лучшего результата: предметы целиком в кадре, без сильного размытия",
        LANG_EN: "For best results: keep full objects in frame and avoid heavy blur.",
    },
    "find_furniture_from_result": {
        LANG_RU: "🛋️ Найти мебель",
        LANG_EN: "🛋️ Find furniture",
    },
    "find_furniture_from_result_missing": {
        LANG_RU: "Не нашел финальный рендер, отправь фото вручную",
        LANG_EN: "I couldn't find the final render, please send a photo manually",
    },
    "post_result_prompt_design": {
        LANG_RU: (
            "Результат готов\n\n"
            "Если хочешь, можем сразу:\n"
            "🔁 сделать еще один вариант\n"
            "🛠️ изменить этот результат\n"
            "⭐ открыть баланс\n"
            "🏠 вернуться в меню"
        ),
        LANG_EN: (
            "Your result is ready\n\n"
            "If you want, we can do this next:\n"
            "🔁 generate another variant\n"
            "🛠️ edit this result\n"
            "⭐ open balance\n"
            "🏠 go back to menu"
        ),
    },
    "post_result_prompt_furniture": {
        LANG_RU: (
            "Результат готов\n\n"
            "Если хочешь, можем сразу:\n"
            "🔁 найти еще один вариант\n"
            "⭐ открыть баланс\n"
            "🏠 вернуться в меню"
        ),
        LANG_EN: (
            "Your result is ready\n\n"
            "If you want, we can do this next:\n"
            "🔁 find another variant\n"
            "⭐ open balance\n"
            "🏠 go back to menu"
        ),
    },
}

PACKAGE_CATALOG_STARS = {
    1: 25,
    5: 109,
    10: 199,
    20: 379,
    50: 899,
    100: 1699,
}
PACKAGE_CATALOG_TBANK_RUB_DEFAULT = {
    1: 29,
    5: 139,
    10: 269,
    20: 519,
    50: 1249,
    100: 2399,
}
PACKAGE_REQUEST_OPTIONS = set(PACKAGE_CATALOG_STARS.keys())


def _build_invoice_payload(
    user_id: int,
    credits: int,
    stars: int,
    *,
    checkout_payment_id: str | None = None,
    promo_reservation_id: str | None = None,
    promo_code_id: str | None = None,
    promo_code: str | None = None,
    stars_original: int | None = None,
    discount_stars: int | None = None,
) -> str:
    if INVOICE_VERSION >= 4:
        payload = {
            "v": INVOICE_VERSION,
            "k": "c",
            "u": int(user_id),
            "c": int(credits),
            "s": int(stars),
            "p": str(checkout_payment_id or "").strip() or None,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    payload = {
        "v": INVOICE_VERSION,
        "kind": INVOICE_KIND_CREDITS,
        "user_id": int(user_id),
        "credits": int(credits),
        "stars": int(stars),
        "checkout_payment_id": str(checkout_payment_id or "").strip() or None,
    }
    has_promo = any(
        [
            promo_reservation_id,
            promo_code_id,
            promo_code,
            stars_original is not None,
            discount_stars is not None,
        ]
    )
    if has_promo:
        payload.update(
            {
                "promo_reservation_id": str(promo_reservation_id or "").strip(),
                "promo_code_id": str(promo_code_id or "").strip(),
                "promo_code": str(promo_code or "").strip(),
                "stars_original": int(stars_original or 0),
                "discount_stars": int(discount_stars or 0),
            }
        )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _payload_fingerprint(payload: str) -> dict[str, Any]:
    text = str(payload or "")
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()
    return {
        "payload_len": len(text),
        "payload_sha1": digest,
        "payload_preview": text[:256],
    }


def _parse_invoice_payload_detailed(payload: str) -> tuple[dict[str, Any] | None, str | None]:
    raw = str(payload or "")
    if not raw.strip():
        return None, "empty_payload"
    try:
        data = json.loads(raw)
    except Exception:
        return None, "invalid_json"
    if not isinstance(data, dict):
        return None, "payload_not_object"
    kind = str(data.get("kind", data.get("k", ""))).strip()
    if not kind:
        return None, "missing_kind"
    if kind == "c":
        kind = INVOICE_KIND_CREDITS
    try:
        version = int(data.get("v", 0))
    except Exception:
        return None, "invalid_version"
    try:
        user_id = int(data.get("user_id", data.get("u", 0)))
    except Exception:
        return None, "invalid_user_id"
    try:
        credits = int(data.get("credits", data.get("c", 0)))
    except Exception:
        return None, "invalid_credits"
    try:
        stars = int(data.get("stars", data.get("s", 0)))
    except Exception:
        return None, "invalid_stars"
    stars_original_raw = data.get("stars_original")
    discount_stars_raw = data.get("discount_stars")
    checkout_payment_id = str(data.get("checkout_payment_id", data.get("p", ""))).strip() or None
    promo_reservation_id = str(data.get("promo_reservation_id", "")).strip() or None
    promo_code_id = str(data.get("promo_code_id", "")).strip() or None
    promo_code = str(data.get("promo_code", "")).strip() or None
    stars_original: int | None = None
    discount_stars: int | None = None
    if stars_original_raw is not None:
        try:
            stars_original = int(stars_original_raw)
        except Exception:
            return None, "invalid_stars_original"
    if discount_stars_raw is not None:
        try:
            discount_stars = int(discount_stars_raw)
        except Exception:
            return None, "invalid_discount_stars"
    has_promo = any(
        [
            promo_reservation_id,
            promo_code_id,
            promo_code,
            stars_original is not None,
            discount_stars is not None,
        ]
    )
    if user_id <= 0 or credits <= 0 or stars <= 0:
        return None, "non_positive_fields"
    if has_promo:
        if not (
            promo_reservation_id
            and promo_code_id
            and promo_code
            and stars_original is not None
            and discount_stars is not None
        ):
            return None, "invalid_promocode_payload"
    return {
        "v": version,
        "kind": kind,
        "user_id": user_id,
        "credits": credits,
        "stars": stars,
        "checkout_payment_id": checkout_payment_id,
        "promo_reservation_id": promo_reservation_id,
        "promo_code_id": promo_code_id,
        "promo_code": promo_code,
        "stars_original": stars_original,
        "discount_stars": discount_stars,
        "has_promocode": has_promo,
    }, None


def _validate_stars_payment_payload(
    payload_data: dict[str, Any] | None,
    *,
    expected_user_id: int,
    currency: str,
    total_amount: int,
) -> tuple[bool, str | None, dict[str, Any]]:
    normalized_currency = str(currency or "").upper().strip()
    actual_total = int(total_amount or 0)
    if payload_data is None:
        return False, "invalid_invoice_payload", {}
    version = int(payload_data.get("v", 0))
    kind = str(payload_data.get("kind", "")).strip()
    user_id = int(payload_data.get("user_id", 0))
    credits = int(payload_data.get("credits", 0))
    stars = int(payload_data.get("stars", 0))
    checkout_payment_id = str(payload_data.get("checkout_payment_id", "")).strip() or None
    has_promocode = bool(payload_data.get("has_promocode"))
    promo_reservation_id = str(payload_data.get("promo_reservation_id", "")).strip() or None
    promo_code_id = str(payload_data.get("promo_code_id", "")).strip() or None
    promo_code = str(payload_data.get("promo_code", "")).strip() or None
    stars_original = int(payload_data.get("stars_original") or 0)
    discount_stars = int(payload_data.get("discount_stars") or 0)

    if kind != INVOICE_KIND_CREDITS:
        return False, "unsupported_payload_kind", {"kind": kind}
    if version not in SUPPORTED_INVOICE_VERSIONS:
        return False, "unsupported_payload_version", {
            "payload_version": version,
            "supported_versions": sorted(SUPPORTED_INVOICE_VERSIONS),
        }
    if normalized_currency != STARS_CURRENCY:
        return False, "currency_mismatch", {
            "currency": normalized_currency,
            "expected_currency": STARS_CURRENCY,
        }
    if user_id != int(expected_user_id):
        return False, "user_mismatch", {
            "payload_user_id": user_id,
            "expected_user_id": int(expected_user_id),
        }
    if credits not in PACKAGE_REQUEST_OPTIONS:
        return False, "unsupported_credits_pack", {
            "credits": credits,
            "allowed_credits": sorted(PACKAGE_REQUEST_OPTIONS),
        }
    catalog_stars = PACKAGE_CATALOG_STARS.get(credits)
    if catalog_stars is None:
        return False, "catalog_missing_price", {"credits": credits}
    if version >= 3 and not checkout_payment_id:
        return False, "checkout_payment_id_missing", {"payload_version": version}
    if not has_promocode and int(catalog_stars) != stars:
        return False, "payload_catalog_mismatch", {
            "credits": credits,
            "payload_stars": stars,
            "catalog_stars": int(catalog_stars),
        }
    if has_promocode:
        if version < 2:
            return False, "promocode_payload_unsupported_version", {"payload_version": version}
        if not (promo_reservation_id and promo_code_id and promo_code):
            return False, "promocode_payload_missing_fields", {}
        if stars_original <= 0 or discount_stars <= 0:
            return False, "promocode_invalid_amounts", {
                "stars_original": stars_original,
                "discount_stars": discount_stars,
            }
        if stars_original != int(catalog_stars):
            return False, "promocode_catalog_mismatch", {
                "credits": credits,
                "stars_original": stars_original,
                "catalog_stars": int(catalog_stars),
            }
        if stars_original - discount_stars != stars:
            return False, "promocode_price_mismatch", {
                "stars_original": stars_original,
                "discount_stars": discount_stars,
                "payload_stars": stars,
            }
        if stars >= stars_original:
            return False, "promocode_non_effective_discount", {
                "stars_original": stars_original,
                "payload_stars": stars,
            }
    if actual_total != stars:
        return False, "total_amount_mismatch", {
            "payload_stars": stars,
            "total_amount": actual_total,
        }
    return True, None, {
        "payload_version": version,
        "credits": credits,
        "stars": stars,
        "checkout_payment_id": checkout_payment_id,
        "has_promocode": has_promocode,
        "promo_code": promo_code,
        "promo_reservation_id": promo_reservation_id,
        "promo_code_id": promo_code_id,
        "stars_original": stars_original if has_promocode else None,
        "discount_stars": discount_stars if has_promocode else None,
    }


REFUND_REASON_CODES = {
    "service_failure_no_result",
    "duplicate_charge",
    "user_requested",
    "support_goodwill",
    "fraud_or_abuse",
    "other_support",
}


def _normalize_refund_reason(reason: str | None) -> str:
    raw = str(reason or "").strip().lower().replace(" ", "_")
    if not raw:
        return "support_manual_unspecified"
    if raw in REFUND_REASON_CODES:
        return raw
    if raw.startswith("custom:"):
        custom = raw[:120]
    else:
        custom = f"custom:{raw}"[:120]
    return custom


def _payment_idempotency_key(
    invoice_payload: str,
    currency: str,
    total_amount: int,
    telegram_payment_charge_id: str | None,
    provider_payment_charge_id: str | None,
) -> str:
    for raw in (telegram_payment_charge_id, provider_payment_charge_id):
        value = str(raw or "").strip()
        if value:
            if len(value) <= 120:
                return f"tg:{value}"
            digest = hashlib.sha1(value.encode("utf-8")).hexdigest()
            return f"tg:sha1:{digest}"
    fallback = f"{invoice_payload}|{currency}|{int(total_amount)}"
    digest = hashlib.sha1(fallback.encode("utf-8")).hexdigest()
    return f"tg:fallback:{digest}"


def _format_remaining_credits(language: str | None, remaining: int | None) -> str:
    if remaining is None:
        return "Unlimited" if _resolve_lang(language) == LANG_EN else "Безлимит"
    return f"{int(remaining)}{CREDIT_SYMBOL}"


def _resolve_lang(language: str | None) -> str:
    if isinstance(language, str) and language.lower().startswith("en"):
        return LANG_EN
    return LANG_RU


def _resolve_mode(mode: str | None) -> str:
    if not mode:
        return MODE_RENDER_ONLY
    normalized = mode.strip().lower()
    if normalized in {MODE_RENDER_ONLY, MODE_FURNITURE_SEARCH}:
        return normalized
    return MODE_RENDER_ONLY


def _t(language: str | None, key: str, **kwargs) -> str:
    lang = _resolve_lang(language)
    text = TEXTS[key][lang]
    return text.format(**kwargs) if kwargs else text


def _mode_title(language: str | None, mode: str | None) -> str:
    normalized = _resolve_mode(mode)
    mapping = {
        MODE_RENDER_ONLY: "mode_render_only",
        MODE_FURNITURE_SEARCH: "mode_furniture_search",
    }
    return _t(language, mapping.get(normalized, "mode_render_only"))


def _is_no_wishes_text(text: str | None) -> bool:
    return isinstance(text, str) and text == NO_WISHES_SENTINEL


def _has_user_text(text: str | None) -> bool:
    return isinstance(text, str) and bool(text.strip()) and not _is_no_wishes_text(text)


def _has_style_reference(payload: UserPayload) -> bool:
    return isinstance(payload.style_reference, (bytes, bytearray)) and bool(payload.style_reference)


def _ready_text_status(language: str | None, payload: UserPayload) -> str:
    if _is_no_wishes_text(payload.text):
        return _t(language, "no_wishes_value")
    if _has_user_text(payload.text):
        return "✅"
    return "❌"


def _build_ready_card(language: str | None, payload: UserPayload) -> str:
    mode = _resolve_mode(payload.mode)
    return "\n".join(
        [
            _t(language, "ready_step"),
            _t(language, "ready_mode", value=_mode_title(language, mode)),
            _t(language, "ready_cost", value=f"{_units_for_mode(mode)}{CREDIT_SYMBOL}"),
            _t(language, "ready_photo", value="✅" if payload.photo else "❌"),
            _t(language, "ready_text", value=_ready_text_status(language, payload)),
        ]
    )


def _package_label(amount: int, language: str | None, stars_amount: int | None = None) -> str:
    stars = int(stars_amount) if stars_amount is not None else PACKAGE_CATALOG_STARS.get(amount)
    if stars is None:
        return str(amount)
    return f"{amount}{CREDIT_SYMBOL} • {stars}⭐"


def _package_label_rub(amount: int, rub_amount: int) -> str:
    return f"{amount}{CREDIT_SYMBOL} • {int(rub_amount)}₽"


def _apply_promocode_preview_amount(original_amount: int, promo_preview: dict[str, Any] | None) -> int:
    original = int(original_amount or 0)
    if original <= 0 or not promo_preview or promo_preview.get("status") != "ok":
        return original
    discount_type = str(promo_preview.get("discount_type") or "").strip().lower()
    try:
        discount_amount = Decimal(str(promo_preview.get("discount_amount") or "0"))
    except Exception:
        return original
    if discount_amount <= 0:
        return original
    if discount_type == "percent":
        discount = int(
            (Decimal(original) * discount_amount / Decimal("100")).quantize(
                Decimal("1"),
                rounding=ROUND_HALF_UP,
            )
        )
    elif discount_type == "fixed":
        discount = int(discount_amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    else:
        return original
    final = original - discount
    if final <= 0 or final >= original:
        return original
    return final


def _format_promocode_discount_label(language: str | None, promo_preview: dict[str, Any] | None) -> str:
    if not promo_preview or promo_preview.get("status") != "ok":
        return ""
    discount_type = str(promo_preview.get("discount_type") or "").strip().lower()
    try:
        discount_amount = Decimal(str(promo_preview.get("discount_amount") or "0"))
    except Exception:
        return ""
    if discount_amount <= 0:
        return ""
    if discount_type == "percent":
        discount = int(discount_amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if language == LANG_EN:
            return f"{discount}%"
        return f"({discount}% скидки)"
    discount = int(discount_amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if language == LANG_EN:
        return f"{discount} credits"
    return f"({discount} кредитов)"


def _parse_tbank_package_catalog(raw: str | None) -> dict[int, int]:
    if not raw:
        return dict(PACKAGE_CATALOG_TBANK_RUB_DEFAULT)
    try:
        data = json.loads(raw)
    except Exception:
        return dict(PACKAGE_CATALOG_TBANK_RUB_DEFAULT)
    if not isinstance(data, dict):
        return dict(PACKAGE_CATALOG_TBANK_RUB_DEFAULT)
    parsed: dict[int, int] = {}
    for key, value in data.items():
        try:
            credits = int(key)
            rub = int(value)
        except Exception:
            continue
        if credits <= 0 or rub <= 0:
            continue
        parsed[credits] = rub
    if not parsed:
        return dict(PACKAGE_CATALOG_TBANK_RUB_DEFAULT)
    return parsed


def _callback_data(action: str, version: int, issued_ts: int) -> str:
    return f"{CALLBACK_PREFIX}|{action}|{int(version)}|{int(issued_ts)}"


def _parse_callback_data(data: str | None) -> tuple[str, int, int] | None:
    if not data:
        return None
    parts = data.split("|", 3)
    if len(parts) != 4 or parts[0] != CALLBACK_PREFIX:
        return None
    action = parts[1].strip()
    try:
        version = int(parts[2])
        issued_ts = int(parts[3])
    except Exception:
        return None
    if not action:
        return None
    return action, version, issued_ts


def _main_menu_inline_keyboard(language: str | None, version: int, issued_ts: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(language, "design_menu"),
                    callback_data=_callback_data("menu:design", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "packages_menu"),
                    callback_data=_callback_data("menu:balance", version, issued_ts),
                ),
                InlineKeyboardButton(
                    text=_t(language, "help_menu"),
                    callback_data=_callback_data("menu:help", version, issued_ts),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "settings_menu"),
                    callback_data=_callback_data("menu:settings", version, issued_ts),
                )
            ],
        ]
    )


def build_main_menu_screen(
    language: str | None,
    *,
    version: int,
    issued_ts: int,
) -> tuple[str, InlineKeyboardMarkup]:
    return _t(language, "menu_prompt"), _main_menu_inline_keyboard(language, version, issued_ts)


def _mode_inline_keyboard(language: str | None, version: int, issued_ts: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(language, "mode_render_only"),
                    callback_data=_callback_data("mode:render_only", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "mode_furniture_search"),
                    callback_data=_callback_data("mode:furniture_search", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "main_menu"),
                    callback_data=_callback_data("menu:main", version, issued_ts),
                )
            ],
        ]
    )


def _help_root_inline_keyboard(language: str | None, version: int, issued_ts: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(language, "help_docs_button"),
                    callback_data=_callback_data("help:docs", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "help_limits_button"),
                    callback_data=_callback_data("help:limits", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "main_menu"),
                    callback_data=_callback_data("menu:main", version, issued_ts),
                )
            ],
        ]
    )


def _help_docs_inline_keyboard(language: str | None, version: int, issued_ts: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(language, "help_docs_privacy_button"),
                    url=LEGAL_PRIVACY_URL,
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "help_docs_offer_button"),
                    url=LEGAL_OFFER_URL,
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "back"),
                    callback_data=_callback_data("help:root", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "main_menu"),
                    callback_data=_callback_data("menu:main", version, issued_ts),
                )
            ],
        ]
    )


def _help_section_inline_keyboard(language: str | None, version: int, issued_ts: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(language, "back"),
                    callback_data=_callback_data("help:root", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "main_menu"),
                    callback_data=_callback_data("menu:main", version, issued_ts),
                )
            ],
        ]
    )


def _settings_inline_keyboard(language: str | None, version: int, issued_ts: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(language, "language_menu"),
                    callback_data=_callback_data("settings:language", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "settings_reset_flow"),
                    callback_data=_callback_data("settings:reset", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "main_menu"),
                    callback_data=_callback_data("menu:main", version, issued_ts),
                )
            ],
        ]
    )


def _language_inline_keyboard(language: str | None, version: int, issued_ts: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Русский",
                    callback_data=_callback_data("settings:lang:ru", version, issued_ts),
                ),
                InlineKeyboardButton(
                    text="English",
                    callback_data=_callback_data("settings:lang:en", version, issued_ts),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "settings_menu"),
                    callback_data=_callback_data("menu:settings", version, issued_ts),
                )
            ],
        ]
    )


def _reset_confirm_inline_keyboard(language: str | None, version: int, issued_ts: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(language, "reset_confirm_yes"),
                    callback_data=_callback_data("settings:reset:confirm", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "reset_confirm_cancel"),
                    callback_data=_callback_data("settings:reset:cancel", version, issued_ts),
                )
            ],
        ]
    )


def _balance_methods_inline_keyboard(
    language: str | None,
    version: int,
    issued_ts: int,
    *,
    tbank_enabled: bool,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if tbank_enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(language, "topup_method_tbank"),
                    callback_data=_callback_data("pay:method:tbank", version, issued_ts),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t(language, "topup_method_stars"),
                callback_data=_callback_data("pay:method:stars", version, issued_ts),
            )
        ]
    )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text=_t(language, "promo_activate_button"),
                    callback_data=_callback_data("pay:promo_activate", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "main_menu"),
                    callback_data=_callback_data("menu:main", version, issued_ts),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _packages_inline_keyboard(
    language: str | None,
    version: int,
    issued_ts: int,
    promo_preview: dict[str, Any] | None = None,
) -> InlineKeyboardMarkup:
    package_units = sorted(PACKAGE_CATALOG_STARS.keys())
    rows: list[list[InlineKeyboardButton]] = []
    for idx in range(0, len(package_units), 2):
        row_units = package_units[idx : idx + 2]
        rows.append(
            [
                InlineKeyboardButton(
                    text=_package_label(
                        amount,
                        language,
                        _apply_promocode_preview_amount(PACKAGE_CATALOG_STARS[amount], promo_preview),
                    ),
                    callback_data=_callback_data(f"pay:pack:{amount}", version, issued_ts),
                )
                for amount in row_units
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t(language, "main_menu"),
                callback_data=_callback_data("menu:main", version, issued_ts),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _tbank_packages_inline_keyboard(
    language: str | None,
    version: int,
    issued_ts: int,
    package_catalog_rub: dict[int, int],
    promo_preview: dict[str, Any] | None = None,
) -> InlineKeyboardMarkup:
    package_units = sorted(package_catalog_rub.keys())
    rows: list[list[InlineKeyboardButton]] = []
    for idx in range(0, len(package_units), 2):
        row_units = package_units[idx : idx + 2]
        rows.append(
            [
                InlineKeyboardButton(
                    text=_package_label_rub(
                        amount,
                        _apply_promocode_preview_amount(int(package_catalog_rub[amount]), promo_preview),
                    ),
                    callback_data=_callback_data(f"pay:tbank_pack:{amount}", version, issued_ts),
                )
                for amount in row_units
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t(language, "packages_menu"),
                callback_data=_callback_data("menu:balance", version, issued_ts),
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t(language, "main_menu"),
                callback_data=_callback_data("menu:main", version, issued_ts),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _tbank_payment_link_inline_keyboard(
    language: str | None,
    version: int,
    issued_ts: int,
    payment_url: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_t(language, "tbank_payment_button"), url=payment_url)],
            [
                InlineKeyboardButton(
                    text=_t(language, "packages_menu"),
                    callback_data=_callback_data("menu:balance", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "main_menu"),
                    callback_data=_callback_data("menu:main", version, issued_ts),
                )
            ],
        ]
    )


def _payment_success_inline_keyboard(language: str | None, version: int, issued_ts: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(language, "design_menu"),
                    callback_data=_callback_data("menu:design", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "packages_menu"),
                    callback_data=_callback_data("menu:balance", version, issued_ts),
                ),
                InlineKeyboardButton(
                    text=_t(language, "main_menu"),
                    callback_data=_callback_data("menu:main", version, issued_ts),
                ),
            ],
        ]
    )


def _payment_issue_inline_keyboard(language: str | None, version: int, issued_ts: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(language, "packages_menu"),
                    callback_data=_callback_data("menu:balance", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "main_menu"),
                    callback_data=_callback_data("menu:main", version, issued_ts),
                )
            ],
        ]
    )


def _post_result_inline_keyboard(
    language: str | None,
    version: int,
    issued_ts: int,
    mode: str,
) -> InlineKeyboardMarkup:
    if mode == MODE_FURNITURE_SEARCH:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=_t(language, "retry_variant"),
                        callback_data=_callback_data("flow:retry_variant", version, issued_ts),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=_t(language, "packages_menu"),
                        callback_data=_callback_data("menu:balance", version, issued_ts),
                    ),
                    InlineKeyboardButton(
                        text=_t(language, "main_menu"),
                        callback_data=_callback_data("menu:main", version, issued_ts),
                    ),
                ],
            ]
        )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(language, "retry_variant"),
                    callback_data=_callback_data("flow:retry_variant", version, issued_ts),
                ),
                InlineKeyboardButton(
                    text=_t(language, "edit_from_result"),
                    callback_data=_callback_data("flow:edit_from_result", version, issued_ts),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "find_furniture_from_result"),
                    callback_data=_callback_data("flow:find_furniture_from_result", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "packages_menu"),
                    callback_data=_callback_data("menu:balance", version, issued_ts),
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(language, "main_menu"),
                    callback_data=_callback_data("menu:main", version, issued_ts),
                )
            ],
        ]
    )


def _post_result_prompt(language: str | None, mode: str) -> str:
    key = "post_result_prompt_furniture" if mode == MODE_FURNITURE_SEARCH else "post_result_prompt_design"
    return _t(language, key)


def _render_compose_card(
    language: str | None,
    payload: UserPayload,
    balance_text: str = "—",
    *,
    prefilled_hint_key: str | None = None,
    zero_balance: bool = False,
) -> str:
    if zero_balance:
        return "\n".join(
            [
                f"<b>{_t(language, 'render_compose_title')}</b>",
                _t(language, "render_compose_zero_balance_intro"),
                "",
                f"Стоимость: {_units_for_mode(MODE_RENDER_ONLY)}{CREDIT_SYMBOL}",
                _t(language, "compose_balance", value=balance_text),
                "",
                _t(
                    language,
                    "render_compose_zero_balance_examples",
                    examples_url=_t(language, "render_examples_url"),
                ),
            ]
        )

    has_photo = bool(payload.photo)
    has_text = _has_user_text(payload.text)
    if has_photo and has_text:
        intro_key = "render_compose_intro_ready"
        guidance_key = "render_compose_style_optional_hint"
    elif has_photo:
        intro_key = "render_compose_intro_photo_only"
        guidance_key = "render_compose_style_optional_hint"
    elif has_text:
        intro_key = "render_compose_intro_text_only"
        guidance_key = "render_compose_style_optional_hint"
    else:
        intro_key = "render_compose_intro"
        guidance_key = "render_compose_guidance"

    intro_text = _t(language, intro_key)
    if prefilled_hint_key and (payload.photo or _has_user_text(payload.text)):
        intro_text = _t(language, prefilled_hint_key)

    lines = [f"<b>{_t(language, 'render_compose_title')}</b>", intro_text, "", _t(language, guidance_key)]
    if _has_style_reference(payload):
        lines.extend(
            [
                "",
                _t(
                    language,
                    "render_compose_style_status",
                    value=_t(language, "render_compose_style_status_set"),
                ),
            ]
        )
    elif not (has_photo or has_text):
        lines.extend(
            [
                "",
                _t(
                    language,
                    "render_compose_style_status",
                    value=_t(language, "render_compose_style_status_optional"),
                ),
            ]
        )
    lines.extend(
        [
            "",
            f"Стоимость: {_units_for_mode(MODE_RENDER_ONLY)}{CREDIT_SYMBOL}",
            _t(language, "compose_balance", value=balance_text),
        ]
    )
    return "\n".join(lines)


def _render_compose_inline_keyboard(
    language: str | None,
    payload: UserPayload,
    version: int,
    issued_ts: int,
    *,
    show_balance_button: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if payload.photo:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(language, "start_process"),
                    callback_data=_callback_data("flow:start", version, issued_ts),
                )
            ]
        )
    rows.extend([
        [
            InlineKeyboardButton(
                text=_t(
                    language,
                    "render_compose_photo_button",
                    status="✅" if payload.photo else "❌",
                ),
                callback_data=_callback_data("flow:new_photo", version, issued_ts),
            ),
        ],
        [
            InlineKeyboardButton(
                text=_t(
                    language,
                    "render_compose_text_button",
                    status="✅" if _has_user_text(payload.text) else "❌",
                ),
                callback_data=_callback_data("flow:edit_text", version, issued_ts),
            )
        ],
        [
            InlineKeyboardButton(
                text=_t(
                    language,
                    "render_compose_style_button",
                    status=" ✅" if _has_style_reference(payload) else "",
                ),
                callback_data=_callback_data("flow:style_ref", version, issued_ts),
            )
        ],
    ])
    if _has_style_reference(payload):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(language, "render_compose_style_remove_button"),
                    callback_data=_callback_data("flow:style_ref_remove", version, issued_ts),
                )
            ]
        )
    if show_balance_button:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(language, "packages_menu"),
                    callback_data=_callback_data("menu:balance", version, issued_ts),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t(language, "main_menu"),
                callback_data=_callback_data("menu:main", version, issued_ts),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _furniture_compose_card(
    language: str | None,
    payload: UserPayload,
    balance_text: str = "—",
    *,
    prefilled_from_render: bool = False,
    zero_balance: bool = False,
) -> str:
    if zero_balance:
        return "\n".join(
            [
                f"<b>{_t(language, 'furniture_compose_title')}</b>",
                _t(language, "furniture_compose_zero_balance_intro"),
                "",
                f"Стоимость: {_units_for_mode(MODE_FURNITURE_SEARCH)}{CREDIT_SYMBOL}",
                _t(language, "compose_balance", value=balance_text),
                "",
                _t(
                    language,
                    "furniture_compose_zero_balance_examples",
                    examples_url=_t(language, "furniture_examples_url"),
                ),
            ]
        )

    return "\n".join(
        [
            f"<b>{_t(language, 'furniture_compose_title')}</b>",
            _t(
                language,
                "furniture_compose_intro_prefilled" if prefilled_from_render else "furniture_compose_intro",
            ),
            _t(language, "furniture_compose_guidance"),
            "",
            f"Стоимость: {_units_for_mode(MODE_FURNITURE_SEARCH)}{CREDIT_SYMBOL}",
            _t(language, "compose_balance", value=balance_text),
        ]
    )


def _furniture_compose_inline_keyboard(
    language: str | None,
    payload: UserPayload,
    version: int,
    issued_ts: int,
    *,
    show_balance_button: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if payload.photo:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(language, "start_process_furniture"),
                    callback_data=_callback_data("flow:start", version, issued_ts),
                )
            ]
        )
    rows.extend([
        [
            InlineKeyboardButton(
                text=f"📷 Фото {'✅' if payload.photo else '❌'}",
                callback_data=_callback_data("flow:new_photo", version, issued_ts),
            ),
        ]
    ])
    if show_balance_button:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_t(language, "packages_menu"),
                    callback_data=_callback_data("menu:balance", version, issued_ts),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=_t(language, "main_menu"),
                callback_data=_callback_data("menu:main", version, issued_ts),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _processing_inline_keyboard(language: str | None, version: int, issued_ts: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(language, "main_menu"),
                    callback_data=_callback_data("menu:main", version, issued_ts),
                )
            ]
        ]
    )


async def on_photo(chat_id: int, photo: bytes, store: UserDataStore) -> None:
    await store.set_photo(chat_id, photo)


async def on_text(chat_id: int, text: str, store: UserDataStore) -> None:
    await store.set_text(chat_id, text)


async def send_processing(
    bot: Bot,
    chat_id: int,
    status: str,
    *,
    parse_mode: str | None = None,
) -> None:
    kwargs: dict[str, str] = {}
    if parse_mode:
        kwargs["parse_mode"] = parse_mode
    try:
        await bot.send_message(chat_id, status, **kwargs)
    except TypeError:
        # Backward-compat for test doubles that expose a minimal send_message signature.
        await bot.send_message(chat_id, status)


async def send_render(bot: Bot, chat_id: int, image_bytes: bytes) -> None:
    filename = "render.png" if image_bytes.startswith(b"\x89PNG\r\n\x1a\n") else "render.jpg"
    await bot.send_document(
        chat_id,
        document=BufferedInputFile(image_bytes, filename=filename),
    )


async def send_debug_payload(
    bot: Bot, chat_id: int, job_id: str, payload: dict
) -> None:
    compact_payload = _compact_debug_payload(payload)
    content = json.dumps(compact_payload, ensure_ascii=False, indent=2).encode("utf-8")
    await bot.send_document(
        chat_id, document=BufferedInputFile(content, filename=f"debug-{job_id}.json")
    )

    simple_payload = payload.get("simple_pipeline") if isinstance(payload, dict) else None
    if not isinstance(simple_payload, dict):
        return

    raw_items = [
        ("planner_raw", simple_payload.get("planner_raw")),
        ("render_prompt", simple_payload.get("render_prompt")),
        ("ranker_ab_raw", simple_payload.get("ranker_ab_raw")),
        ("validator_raw", simple_payload.get("validator_raw")),
        (
            "rerender_validator_raw",
            simple_payload.get("rerender_validator_raw")
            or simple_payload.get("fix_validator_raw"),
        ),
        ("fix_prompt", simple_payload.get("fix_prompt")),
    ]
    for name, text in raw_items:
        if not text:
            continue
        await bot.send_document(
            chat_id,
            document=BufferedInputFile(
                str(text).encode("utf-8"), filename=f"{name}-{job_id}.txt"
            ),
        )


_DEBUG_TEXT_FIELDS = (
    "planner_raw",
    "render_prompt",
    "ranker_ab_raw",
    "validator_raw",
    "rerender_validator_raw",
    "fix_validator_raw",
    "fix_prompt",
)
_DEBUG_PREVIEW_CHARS = 1200


def _compact_debug_payload(payload: dict) -> dict:
    try:
        compact = json.loads(json.dumps(payload, ensure_ascii=False))
    except Exception:
        compact = dict(payload)
    simple_payload = compact.get("simple_pipeline")
    if not isinstance(simple_payload, dict):
        return compact

    for field in _DEBUG_TEXT_FIELDS:
        raw_value = simple_payload.get(field)
        if not isinstance(raw_value, str):
            continue
        text = raw_value.strip()
        if not text:
            continue
        chars = len(text)
        simple_payload[f"{field}_chars"] = chars
        if chars <= _DEBUG_PREVIEW_CHARS:
            continue
        preview = text[:_DEBUG_PREVIEW_CHARS]
        simple_payload[field] = (
            f"<<truncated: {chars} chars; see {field}.txt attachment>>\n"
            f"{preview}\n..."
        )
        simple_payload[f"{field}_truncated"] = True
    return compact


def _format_last_request(value: object) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    return "—"


def _extract_package_amount(text: str | None) -> int | None:
    if not text:
        return None
    match = re.match(r"^\s*(\d+)", text)
    if match:
        amount = int(match.group(1))
        if amount in PACKAGE_REQUEST_OPTIONS:
            return amount
    return None


def _normalize_promocode_input(value: str | None) -> str:
    return "".join(str(value or "").strip().split()).upper()[:64]


def _normalize_start_source(value: str | None) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = "".join(ch for ch in raw if ch.isalnum() or ch in {"_", "-"})
    normalized = normalized[:128]
    return normalized or None


def _extract_start_source(text: str | None) -> str | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    parts = raw.split(maxsplit=1)
    if not parts:
        return None
    if not parts[0].startswith("/start"):
        return None
    if len(parts) < 2:
        return None
    return _normalize_start_source(parts[1])


def _extract_mode_from_text(text: str | None, language: str | None) -> str | None:
    normalized = (text or "").strip().casefold()
    variants = {
        _t(language, "mode_render_only").casefold(): MODE_RENDER_ONLY,
        _t(language, "mode_furniture_search").casefold(): MODE_FURNITURE_SEARCH,
    }
    return variants.get(normalized)


def _units_for_mode(mode: str) -> int:
    return int(UNITS_BY_MODE.get(_resolve_mode(mode), UNITS_BY_MODE[MODE_RENDER_ONLY]))


def _effective_remaining_credits(status: dict[str, Any]) -> int | None:
    if not status.get("whitelisted"):
        return 0
    remaining = status.get("remaining_requests")
    if remaining is None:
        return None
    try:
        return int(remaining)
    except Exception:
        return 0


def _is_balance_insufficient(remaining: int | None, required_units: int) -> bool:
    if remaining is None:
        return False
    return int(remaining) < int(required_units)


def _flow_timeout_seconds(mode: str | None) -> int:
    return FLOW_TIMEOUT_SECONDS_DEFAULT


def _has_active_flow(payload: UserPayload) -> bool:
    return bool(
        payload.photo
        or payload.style_reference
        or payload.job_id
        or (isinstance(payload.text, str) and payload.text.strip())
    )


def _is_flow_expired(payload: UserPayload, now_ts: float | None = None) -> bool:
    if not _has_active_flow(payload):
        return False
    if not isinstance(payload.last_activity_ts, (int, float)):
        return False
    current_ts = time.time() if now_ts is None else float(now_ts)
    return (current_ts - float(payload.last_activity_ts)) > float(
        _flow_timeout_seconds(payload.mode)
    )


def _decode_text_payload(payload: bytes) -> str | None:
    try:
        return payload.decode("utf-8")
    except Exception:
        return None


def _human_access_reason(reason: str, language: str | None) -> str:
    lang = _resolve_lang(language)
    mapping_ru = {
        "no_subscription": "нет активного пакета",
        "expired": "доступ истек",
        "exhausted": "кредиты закончились",
        "insufficient_credits": "недостаточно кредитов",
        "canceled": "доступ отключен",
        "not_found": "пользователь не найден",
    }
    mapping_en = {
        "no_subscription": "no active package",
        "expired": "access expired",
        "exhausted": "credits are exhausted",
        "insufficient_credits": "not enough credits",
        "canceled": "access canceled",
        "not_found": "user not found",
    }
    mapping = mapping_en if lang == LANG_EN else mapping_ru
    return mapping.get(reason, reason)


def _human_promocode_reason(reason: str, language: str | None) -> str:
    lang = _resolve_lang(language)
    mapping_ru = {
        "empty_code": "пустой код",
        "not_found": "код не найден",
        "code_inactive": "код отключен",
        "code_not_started": "код еще не активен",
        "code_expired": "срок действия кода истек",
        "code_exhausted": "лимит использований исчерпан",
        "new_users_only": "код доступен только новым пользователям",
        "max_uses_per_user_reached": "достигнут лимит использований для пользователя",
        "unsupported_discount_type": "неподдерживаемый тип скидки",
        "invalid_discount": "некорректная скидка",
        "invalid_checkout_amounts": "некорректные параметры пакета",
        "invalid_promocode_payload": "некорректные данные промокода",
        "promocode_amount_mismatch": "ошибка расчета скидки",
        "invalid_promocode_identifiers": "ошибка идентификаторов промокода",
        "promocode_reservation_not_found": "резерв не найден",
        "promocode_user_mismatch": "резерв принадлежит другому пользователю",
        "promocode_code_mismatch": "код резерва не совпадает",
        "promocode_not_reserved": "резерв неактивен",
        "promocode_reservation_expired": "время резерва истекло",
        "promocode_checkout_mismatch": "параметры оплаты не совпадают с резервом",
        "promocode_not_found": "код не найден",
        "reservation_not_found": "резерв не найден",
        "reservation_not_active": "резерв неактивен",
        "reservation_expired": "время резерва истекло",
        "checkout_mismatch": "параметры оплаты не совпадают с резервом",
    }
    mapping_en = {
        "empty_code": "empty code",
        "not_found": "code not found",
        "code_inactive": "code is inactive",
        "code_not_started": "code is not active yet",
        "code_expired": "code expired",
        "code_exhausted": "code usage limit is exhausted",
        "new_users_only": "code is available only for new users",
        "max_uses_per_user_reached": "per-user usage limit reached",
        "unsupported_discount_type": "unsupported discount type",
        "invalid_discount": "invalid discount setup",
        "invalid_checkout_amounts": "invalid package parameters",
        "invalid_promocode_payload": "invalid promo payload",
        "promocode_amount_mismatch": "discount calculation mismatch",
        "invalid_promocode_identifiers": "invalid promo identifiers",
        "promocode_reservation_not_found": "reservation not found",
        "promocode_user_mismatch": "reservation belongs to another user",
        "promocode_code_mismatch": "reservation code mismatch",
        "promocode_not_reserved": "reservation is not active",
        "promocode_reservation_expired": "reservation expired",
        "promocode_checkout_mismatch": "checkout data mismatch",
        "promocode_not_found": "promo code not found",
        "reservation_not_found": "reservation not found",
        "reservation_not_active": "reservation is not active",
        "reservation_expired": "reservation expired",
        "checkout_mismatch": "checkout data mismatch",
    }
    mapping = mapping_en if lang == LANG_EN else mapping_ru
    return mapping.get(reason, reason)


def build_router(
    orchestrator: PipelineOrchestrator,
    store: UserDataStore,
    redis_client: RuntimeStateClient,
    admin_ids: set[int],
    whitelist_service: WhitelistService,
    settings: "Settings | None" = None,
) -> Router:
    router = Router()
    idle_states = {
        UserStates.menu.state,
        UserStates.settings.state,
        UserStates.packages.state,
        UserStates.language.state,
    }

    def is_admin(chat_id: int) -> bool:
        return chat_id in admin_ids

    tbank_service = TBankAcquiringService(settings) if settings is not None else None
    tbank_enabled = bool(tbank_service and tbank_service.is_configured())
    tbank_package_catalog = _parse_tbank_package_catalog(
        getattr(settings, "TBANK_PACKAGE_CATALOG_RUB_JSON", None) if settings else None
    )

    async def _set_chat_commands(bot: Bot, chat_id: int, language: str) -> None:
        lang = _resolve_lang(language)
        if lang == LANG_EN:
            commands = [
                BotCommand(command="start", description="Restart bot"),
                BotCommand(command="menu", description="Open main menu"),
                BotCommand(command="balance", description="Show credit balance"),
                BotCommand(command="buy", description="Top up credits"),
                BotCommand(command="help", description="How it works"),
                BotCommand(command="paysupport", description="Payment support"),
            ]
        else:
            commands = [
                BotCommand(command="start", description="Перезапустить бота"),
                BotCommand(command="menu", description="Открыть главное меню"),
                BotCommand(command="balance", description="Показать баланс"),
                BotCommand(command="buy", description="Пополнить кредиты"),
                BotCommand(command="help", description="Как пользоваться"),
                BotCommand(command="paysupport", description="Поддержка по оплате"),
            ]
        if is_admin(chat_id):
            if lang == LANG_EN:
                commands.append(
                    BotCommand(
                        command="jobs_active",
                        description="Show global active jobs",
                    )
                )
                commands.append(
                    BotCommand(
                        command="flow_report",
                        description="Show flow analytics",
                    )
                )
                commands.append(
                    BotCommand(
                        command="flow_user",
                        description="Show user flow details",
                    )
                )
            else:
                commands.append(
                    BotCommand(
                        command="jobs_active",
                        description="Глобально активные job",
                    )
                )
                commands.append(
                    BotCommand(
                        command="flow_report",
                        description="Аналитика по меню",
                    )
                )
                commands.append(
                    BotCommand(
                        command="flow_user",
                        description="Воронка пользователя",
                    )
                )
        try:
            await bot.set_my_commands(commands, scope=BotCommandScopeChat(chat_id=chat_id))
            await bot.set_chat_menu_button(
                chat_id=chat_id,
                menu_button=MenuButtonCommands(),
            )
        except Exception:
            logger.exception("set_my_commands_failed chat_id=%s", chat_id)

    async def _next_ui_context(chat_id: int) -> tuple[int, int]:
        return await store.bump_ui_version(chat_id), int(time.time())

    async def _record_screen_view_safe(
        chat_id: int,
        screen_key: str | None,
        *,
        source: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> None:
        if not screen_key:
            return
        try:
            await whitelist_service.record_screen_view(
                chat_id,
                screen_key,
                source=source,
                meta=meta,
            )
        except Exception:
            logger.exception(
                "record_screen_view_failed chat_id=%s screen_key=%s source=%s",
                chat_id,
                screen_key,
                source,
            )

    async def _record_action_safe(
        chat_id: int,
        action_key: str | None,
        *,
        source: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> None:
        if not action_key:
            return
        try:
            await whitelist_service.record_action_click(
                chat_id,
                action_key,
                source=source,
                meta=meta,
            )
        except Exception:
            logger.exception(
                "record_action_click_failed chat_id=%s action_key=%s source=%s",
                chat_id,
                action_key,
                source,
            )

    async def _cleanup_previous_inline(
        bot: Bot, chat_id: int, state: FSMContext, keep_message_id: int
    ) -> None:
        data = await state.get_data()
        message_ids: list[int] = []
        prev_id = data.get("ui_message_id")
        if isinstance(prev_id, int):
            message_ids.append(prev_id)
        preserved_ids = data.get("preserved_ui_message_ids")
        if isinstance(preserved_ids, list):
            for value in preserved_ids:
                if isinstance(value, int):
                    message_ids.append(value)
        message_ids = [value for value in dict.fromkeys(message_ids) if value != keep_message_id]
        if not message_ids:
            await state.update_data(ui_message_id=keep_message_id)
            return
        for message_id in message_ids:
            try:
                await bot.delete_message(
                    chat_id=chat_id,
                    message_id=message_id,
                )
            except Exception:
                try:
                    await bot.edit_message_reply_markup(
                        chat_id=chat_id,
                        message_id=message_id,
                        reply_markup=None,
                    )
                except Exception:
                    pass
        await state.update_data(ui_message_id=keep_message_id, preserved_ui_message_ids=[])

    async def _send_inline_screen(
        message: Message,
        state: FSMContext,
        text: str,
        markup: InlineKeyboardMarkup,
        *,
        parse_mode: str | None = None,
        screen_key: str | None = None,
        screen_source: str | None = "inline_screen",
        screen_meta: dict[str, object] | None = None,
        preserve_previous_inline: bool = False,
    ) -> Message:
        sent = await message.answer(text, reply_markup=markup, parse_mode=parse_mode)
        sent_message_id = getattr(sent, "message_id", None)
        if isinstance(sent_message_id, int):
            if preserve_previous_inline:
                data = await state.get_data()
                preserved_ids = data.get("preserved_ui_message_ids")
                next_preserved: list[int] = []
                if isinstance(preserved_ids, list):
                    next_preserved = [value for value in preserved_ids if isinstance(value, int)]
                prev_id = data.get("ui_message_id")
                if isinstance(prev_id, int) and prev_id != sent_message_id:
                    next_preserved.append(prev_id)
                next_preserved = list(dict.fromkeys(next_preserved))
                await state.update_data(
                    ui_message_id=sent_message_id,
                    preserved_ui_message_ids=next_preserved,
                )
            else:
                await _cleanup_previous_inline(message.bot, message.chat.id, state, sent_message_id)
        await _record_screen_view_safe(
            message.chat.id,
            screen_key,
            source=screen_source,
            meta=screen_meta,
        )
        return sent

    async def _show_main_menu_screen(message: Message, state: FSMContext, language: str) -> None:
        await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            _t(language, "menu_prompt"),
            _main_menu_inline_keyboard(language, version, issued_ts),
            parse_mode="HTML",
            screen_key="main_menu",
        )

    async def _show_mode_overview_screen(message: Message, state: FSMContext, language: str) -> None:
        await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            _t(language, "ask_mode"),
            _mode_inline_keyboard(language, version, issued_ts),
            parse_mode="HTML",
            screen_key="mode_overview",
        )

    async def _show_help_root_screen(message: Message, state: FSMContext, language: str) -> None:
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            _t(language, "help_root_text"),
            _help_root_inline_keyboard(language, version, issued_ts),
            parse_mode="HTML",
            screen_key="help_root",
        )

    async def _show_help_examples_screen(message: Message, state: FSMContext, language: str) -> None:
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            _t(language, "help_examples_text"),
            _help_section_inline_keyboard(language, version, issued_ts),
            parse_mode="HTML",
            screen_key="help_examples",
        )

    async def _show_help_limits_screen(message: Message, state: FSMContext, language: str) -> None:
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            _t(language, "help_limits_text"),
            _help_section_inline_keyboard(language, version, issued_ts),
            parse_mode="HTML",
            screen_key="help_limits",
        )

    async def _show_help_docs_screen(message: Message, state: FSMContext, language: str) -> None:
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            _t(language, "help_docs_text"),
            _help_docs_inline_keyboard(language, version, issued_ts),
            parse_mode="HTML",
            screen_key="help_docs",
        )

    async def _show_settings_screen(message: Message, state: FSMContext, language: str) -> None:
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            _t(language, "settings_prompt"),
            _settings_inline_keyboard(language, version, issued_ts),
            screen_key="settings",
        )

    async def _show_language_screen(message: Message, state: FSMContext, language: str) -> None:
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            _t(language, "choose_language_menu"),
            _language_inline_keyboard(language, version, issued_ts),
            screen_key="language",
        )

    async def _show_reset_confirm_screen(message: Message, state: FSMContext, language: str) -> None:
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            _t(language, "reset_confirm_prompt"),
            _reset_confirm_inline_keyboard(language, version, issued_ts),
            screen_key="reset_confirm",
        )

    async def _show_balance_screen(
        message: Message,
        state: FSMContext,
        language: str,
        *,
        text_override: str | None = None,
        preserve_previous_inline: bool = False,
        reuse_current_version: bool = False,
    ) -> None:
        status = await whitelist_service.get_whitelist_status(message.chat.id)
        payload = await store.get_payload(message.chat.id)
        remaining = _effective_remaining_credits(status)
        balance_text = _format_remaining_credits(language, remaining)
        lines = [text_override or _t(language, "balance_overview", balance=balance_text)]
        if payload.promocode:
            lines.append(_t(language, "promo_current", code=payload.promocode))
        if reuse_current_version:
            version = await store.get_ui_version(message.chat.id)
            if version <= 0:
                version, issued_ts = await _next_ui_context(message.chat.id)
            else:
                issued_ts = int(time.time())
        else:
            version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            "\n".join(lines),
            _balance_methods_inline_keyboard(
                language,
                version,
                issued_ts,
                tbank_enabled=tbank_enabled,
            ),
            screen_key="balance",
            preserve_previous_inline=preserve_previous_inline,
        )

    async def _show_packages_screen(message: Message, state: FSMContext, language: str) -> None:
        payload = await store.get_payload(message.chat.id)
        lines = [_t(language, "packages_intro")]
        promo_preview: dict[str, Any] | None = None
        if payload.promocode:
            promo_check = await whitelist_service.check_promocode(message.chat.id, payload.promocode)
            if promo_check.get("status") == "ok":
                promo_preview = promo_check
                lines.append(
                    _t(
                        language,
                        "promo_prices_applied",
                        code=promo_check.get("code") or payload.promocode,
                        discount=_format_promocode_discount_label(language, promo_check),
                    )
                )
            else:
                lines.append(_t(language, "promo_current", code=payload.promocode))
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            "\n".join(lines),
            _packages_inline_keyboard(language, version, issued_ts, promo_preview),
            screen_key="packages_stars",
        )

    async def _show_tbank_packages_screen(message: Message, state: FSMContext, language: str) -> None:
        payload = await store.get_payload(message.chat.id)
        lines = [_t(language, "packages_intro_tbank")]
        promo_preview: dict[str, Any] | None = None
        if payload.promocode:
            promo_check = await whitelist_service.check_promocode(message.chat.id, payload.promocode)
            if promo_check.get("status") == "ok":
                promo_preview = promo_check
                lines.append(
                    _t(
                        language,
                        "promo_prices_applied",
                        code=promo_check.get("code") or payload.promocode,
                        discount=_format_promocode_discount_label(language, promo_check),
                    )
                )
            else:
                lines.append(_t(language, "promo_current", code=payload.promocode))
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            "\n".join(lines),
            _tbank_packages_inline_keyboard(
                language,
                version,
                issued_ts,
                tbank_package_catalog,
                promo_preview,
            ),
            screen_key="packages_tbank",
        )

    async def _show_payment_result_screen(
        message: Message,
        state: FSMContext,
        language: str,
        *,
        text: str,
        success: bool,
    ) -> None:
        version, issued_ts = await _next_ui_context(message.chat.id)
        keyboard = (
            _payment_success_inline_keyboard(language, version, issued_ts)
            if success
            else _payment_issue_inline_keyboard(language, version, issued_ts)
        )
        await _send_inline_screen(
            message,
            state,
            text,
            keyboard,
            screen_key="payment_result_success" if success else "payment_result_issue",
        )

    async def _show_post_result_screen(
        message: Message,
        state: FSMContext,
        language: str,
        text: str,
        mode: str,
    ) -> None:
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            text,
            _post_result_inline_keyboard(language, version, issued_ts, mode),
            screen_key="post_result_furniture" if mode == MODE_FURNITURE_SEARCH else "post_result_design",
        )

    async def _apply_promocode(chat_id: int, code: str, language: str, message: Message) -> bool:
        payload = await store.get_payload(chat_id)
        check = await whitelist_service.check_promocode(chat_id, code)
        if str(check.get("status")) != "ok":
            reason = _human_promocode_reason(str(check.get("reason", "invalid")), language)
            await message.answer(_t(language, "promo_invalid", reason=reason))
            return False

        if payload.promo_reservation_id:
            await whitelist_service.release_promocode_reservation(
                payload.promo_reservation_id,
                user_id=chat_id,
                reason="promo_replaced",
            )
        await store.set_promocode(chat_id, code)
        await store.set_promo_reservation_id(chat_id, None)
        await whitelist_service.record_billing_event(
            provider=STARS_PROVIDER,
            event_type="promocode_selected",
            user_id=chat_id,
            reason=code,
            meta={"code_id": check.get("code_id")},
        )
        await message.answer(_t(language, "promo_applied", code=code))
        return True

    async def _show_render_compose_screen(message: Message, state: FSMContext, language: str) -> None:
        payload = await store.get_payload(message.chat.id)
        status = await whitelist_service.get_whitelist_status(message.chat.id)
        remaining = _effective_remaining_credits(status)
        required = _units_for_mode(MODE_RENDER_ONLY)
        balance_text = _format_remaining_credits(language, remaining)
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            _render_compose_card(language, payload, balance_text, zero_balance=(remaining == 0)),
            _render_compose_inline_keyboard(
                language,
                payload,
                version,
                issued_ts,
                show_balance_button=_is_balance_insufficient(remaining, required),
            ),
            parse_mode="HTML",
            screen_key="render_compose",
        )

    async def _show_render_compose_screen_prefilled(
        message: Message,
        state: FSMContext,
        language: str,
        *,
        prefilled_hint_key: str,
    ) -> None:
        payload = await store.get_payload(message.chat.id)
        status = await whitelist_service.get_whitelist_status(message.chat.id)
        remaining = _effective_remaining_credits(status)
        required = _units_for_mode(MODE_RENDER_ONLY)
        balance_text = _format_remaining_credits(language, remaining)
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            _render_compose_card(language, payload, balance_text, prefilled_hint_key=prefilled_hint_key),
            _render_compose_inline_keyboard(
                language,
                payload,
                version,
                issued_ts,
                show_balance_button=_is_balance_insufficient(remaining, required),
            ),
            parse_mode="HTML",
            screen_key=(
                "render_compose_edit_result"
                if prefilled_hint_key == "render_compose_edit_result_hint"
                else "render_compose_retry"
            ),
        )

    async def _show_furniture_compose_screen(
        message: Message,
        state: FSMContext,
        language: str,
        *,
        prefilled_from_render: bool = False,
    ) -> None:
        payload = await store.get_payload(message.chat.id)
        status = await whitelist_service.get_whitelist_status(message.chat.id)
        remaining = _effective_remaining_credits(status)
        required = _units_for_mode(MODE_FURNITURE_SEARCH)
        balance_text = _format_remaining_credits(language, remaining)
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            _furniture_compose_card(
                language,
                payload,
                balance_text,
                prefilled_from_render=prefilled_from_render,
                zero_balance=(remaining == 0 and not prefilled_from_render),
            ),
            _furniture_compose_inline_keyboard(
                language,
                payload,
                version,
                issued_ts,
                show_balance_button=_is_balance_insufficient(remaining, required),
            ),
            parse_mode="HTML",
            screen_key="furniture_compose_prefilled" if prefilled_from_render else "furniture_compose",
        )

    async def _show_processing_screen(message: Message, state: FSMContext, language: str) -> None:
        version, issued_ts = await _next_ui_context(message.chat.id)
        await _send_inline_screen(
            message,
            state,
            _t(language, "start_processing"),
            _processing_inline_keyboard(language, version, issued_ts),
            screen_key="processing",
        )

    async def _callback_ttl_seconds(chat_id: int, action: str) -> int:
        del chat_id, action
        return CALLBACK_MENU_TTL_SECONDS

    async def _handle_stale_callback(query: CallbackQuery, state: FSMContext) -> None:
        msg = query.message
        if not isinstance(msg, Message):
            return
        lang = await store.get_language(msg.chat.id)
        await state.set_state(UserStates.menu)
        await _show_main_menu_screen(msg, state, lang)

    async def _parse_and_validate_callback(
        query: CallbackQuery, state: FSMContext
    ) -> tuple[str, Message, str] | None:
        msg = query.message
        if not isinstance(msg, Message):
            await query.answer()
            return None
        parsed = _parse_callback_data(query.data)
        if not parsed:
            await query.answer()
            return None
        action, version, issued_ts = parsed
        chat_id = msg.chat.id
        current_version = await store.get_ui_version(chat_id)
        ttl_seconds = await _callback_ttl_seconds(chat_id, action)
        stale = version != current_version or (int(time.time()) - issued_ts) > int(ttl_seconds)
        if stale:
            await query.answer()
            await _handle_stale_callback(query, state)
            return None
        if not await ensure_fresh_flow(msg, state):
            await query.answer()
            return None
        await query.answer()
        lang = await store.get_language(chat_id)
        return action, msg, lang

    async def reset_user_session(
        message: Message,
        state: FSMContext,
        *,
        reason: str,
        notice_key: str,
    ) -> None:
        payload = await store.get_payload(message.chat.id)
        lang = _resolve_lang(payload.language)
        prev_mode = _resolve_mode(payload.mode)
        prev_job_id = payload.job_id
        had_flow = _has_active_flow(payload)
        detached_jobs_count = len(payload.active_jobs)
        await state.clear()
        await store.clear(message.chat.id)
        await store.set_language(message.chat.id, lang)
        await state.set_state(UserStates.menu)
        logger.info(
            "state_reset chat_id=%s reason=%s mode=%s had_flow=%s detached_job_id=%s detached_jobs_count=%s",
            message.chat.id,
            reason,
            prev_mode,
            had_flow,
            prev_job_id,
            detached_jobs_count,
        )
        await message.answer(_t(lang, notice_key), reply_markup=ReplyKeyboardRemove())
        await _show_main_menu_screen(message, state, lang)

    async def send_mode_overview(message: Message, state: FSMContext, language: str) -> None:
        await _show_mode_overview_screen(message, state, language)

    async def ensure_fresh_flow(message: Message, state: FSMContext) -> bool:
        del state
        await store.touch(message.chat.id)
        return True

    async def show_cabinet(message: Message) -> None:
        lang = await store.get_language(message.chat.id)
        status = await whitelist_service.get_whitelist_status(message.chat.id)
        try:
            user = await whitelist_service.ensure_user(
                message.chat.id,
                username=message.from_user.username if message.from_user else None,
                first_name=message.from_user.first_name if message.from_user else None,
                last_name=message.from_user.last_name if message.from_user else None,
            )
        except Exception:
            logger.exception("Failed to load cabinet user data for chat_id=%s", message.chat.id)
            user = None
        usage_total = int(getattr(user, "usage_count", 0) or 0)
        last_request = _format_last_request(getattr(user, "last_request_at", None))
        whitelisted = bool(status.get("whitelisted"))
        remaining = status.get("remaining_requests")
        if whitelisted:
            remaining_text = "Безлимит" if remaining is None else str(remaining)
            if _resolve_lang(lang) == LANG_EN:
                remaining_text = "Unlimited" if remaining is None else str(remaining)
            if remaining is not None:
                remaining_text = f"{remaining_text}{CREDIT_SYMBOL}"
            access_text = _t(lang, "access_active")
        else:
            remaining_text = f"0{CREDIT_SYMBOL}"
            reason = _human_access_reason(str(status.get("reason", "no_access")), lang)
            access_text = _t(lang, "access_denied", reason=reason)
        await message.answer(
            "\n".join(
                [
                    _t(lang, "cabinet_title"),
                    _t(lang, "cabinet_remaining", value=remaining_text),
                    _t(lang, "cabinet_used", value=f"{usage_total}{CREDIT_SYMBOL}"),
                    _t(lang, "cabinet_last_request", value=last_request),
                    _t(lang, "cabinet_access", value=access_text),
                    "",
                    _t(lang, "cabinet_tip"),
                ]
            )
        )

    async def show_packages(message: Message, state: FSMContext) -> None:
        lang = await store.get_language(message.chat.id)
        await _show_balance_screen(message, state, lang)

    async def _send_stars_invoice(message: Message, language: str, amount: int) -> None:
        stars = PACKAGE_CATALOG_STARS[amount]
        checkout_stars = int(stars)
        payload_data = await store.get_payload(message.chat.id)
        promo_code = _normalize_promocode_input(payload_data.promocode)
        promo_reservation_id: str | None = None
        promo_code_id: str | None = None
        discount_stars = 0
        checkout_payment_id: str | None = None
        if not promo_code and payload_data.promo_reservation_id:
            await whitelist_service.release_promocode_reservation(
                payload_data.promo_reservation_id,
                user_id=message.chat.id,
                reason="invoice_without_promo",
            )
            await store.set_promo_reservation_id(message.chat.id, None)
        if promo_code:
            reserve = await whitelist_service.reserve_promocode(
                user_id=message.chat.id,
                code=promo_code,
                credits=amount,
                stars_original=stars,
                ttl_seconds=PROMO_RESERVATION_TTL_SECONDS,
                previous_reservation_id=payload_data.promo_reservation_id,
            )
            if str(reserve.get("status")) != "ok":
                reason = _human_promocode_reason(str(reserve.get("reason", "invalid_discount")), language)
                await store.set_promo_reservation_id(message.chat.id, None)
                await whitelist_service.record_billing_event(
                    provider=STARS_PROVIDER,
                    event_type="promocode_reserve_rejected",
                    user_id=message.chat.id,
                    reason=str(reserve.get("reason", "invalid_discount")),
                    meta={
                        "code": promo_code,
                        "credits": amount,
                        "stars_original": stars,
                    },
                )
                await message.answer(_t(language, "promo_invoice_unavailable", reason=reason))
                return
            promo_reservation_id = str(reserve.get("reservation_id"))
            promo_code_id = str(reserve.get("code_id"))
            promo_code = str(reserve.get("code") or promo_code)
            checkout_stars = int(reserve.get("stars_final") or stars)
            discount_stars = int(reserve.get("discount_stars") or 0)

        intent = await whitelist_service.create_checkout_intent(
            provider=STARS_PROVIDER,
            user_id=message.chat.id,
            credits=amount,
            amount=checkout_stars,
            currency=STARS_CURRENCY,
            promo_reservation_id=promo_reservation_id,
            promo_code_id=promo_code_id,
            amount_original=(stars if promo_reservation_id else None),
            discount_amount=(discount_stars if promo_reservation_id else None),
        )
        if str(intent.get("status")) != "ok":
            if promo_reservation_id:
                await whitelist_service.release_promocode_reservation(
                    promo_reservation_id,
                    user_id=message.chat.id,
                    reason="stars_intent_create_failed",
                )
                await store.set_promo_reservation_id(message.chat.id, None)
            logger.warning(
                "stars_intent_create_invalid chat_id=%s credits=%s stars=%s status=%s",
                message.chat.id,
                amount,
                checkout_stars,
                intent.get("status"),
            )
            await message.answer(_t(language, "invoice_error"))
            return
        checkout_payment_id = str(intent.get("payment_id") or "").strip()
        if not checkout_payment_id:
            await message.answer(_t(language, "invoice_error"))
            return

        payload = _build_invoice_payload(
            message.chat.id,
            amount,
            checkout_stars,
            checkout_payment_id=checkout_payment_id,
            promo_reservation_id=promo_reservation_id,
            promo_code_id=promo_code_id,
            promo_code=promo_code if promo_reservation_id else None,
            stars_original=stars if promo_reservation_id else None,
            discount_stars=discount_stars if promo_reservation_id else None,
        )
        title = _t(language, "invoice_title", amount=amount)
        description = _t(language, "invoice_description", amount=amount)
        try:
            sent_invoice = await message.bot.send_invoice(
                chat_id=message.chat.id,
                title=title,
                description=description,
                payload=payload,
                currency=STARS_CURRENCY,
                prices=[LabeledPrice(label=f"{amount}{CREDIT_SYMBOL}", amount=checkout_stars)],
                start_parameter=f"credits-{amount}",
            )
        except Exception:
            await whitelist_service.mark_stars_payment_failed(
                payment_id=checkout_payment_id,
                reason="invoice_send_failed",
                error_meta={
                    "chat_id": message.chat.id,
                    "credits": amount,
                    "stars": checkout_stars,
                },
            )
            if promo_reservation_id:
                await whitelist_service.release_promocode_reservation(
                    promo_reservation_id,
                    user_id=message.chat.id,
                    reason="invoice_send_failed",
                )
                await store.set_promo_reservation_id(message.chat.id, None)
            logger.exception(
                "send_invoice_failed chat_id=%s credits=%s stars=%s",
                message.chat.id,
                amount,
                checkout_stars,
            )
            await message.answer(_t(language, "invoice_error"))
            return

        await whitelist_service.mark_stars_payment_invoice_sent(
            payment_id=checkout_payment_id,
            invoice_meta={
                "chat_id": message.chat.id,
                "message_id": getattr(sent_invoice, "message_id", None),
                **_payload_fingerprint(payload),
            },
        )
        if promo_reservation_id:
            await store.set_promo_reservation_id(message.chat.id, promo_reservation_id)
            await message.answer(
                _t(
                    language,
                    "package_selected_discounted",
                    amount=amount,
                    stars=checkout_stars,
                    code=promo_code,
                )
            )
            await message.answer(
                _t(
                    language,
                    "promo_price_line",
                    code=promo_code,
                    original=stars,
                    final=checkout_stars,
                )
            )
            return
        await store.set_promo_reservation_id(message.chat.id, None)
        await message.answer(_t(language, "package_selected", amount=amount, stars=checkout_stars))

    async def _send_tbank_payment_link(
        message: Message,
        state: FSMContext,
        language: str,
        amount: int,
    ) -> None:
        if not tbank_enabled or tbank_service is None:
            await message.answer(_t(language, "tbank_unavailable"))
            return
        rub_amount = tbank_package_catalog.get(amount)
        if rub_amount is None:
            await message.answer(_t(language, "tbank_unavailable"))
            return
        checkout_rub = int(rub_amount)
        payload_data = await store.get_payload(message.chat.id)
        promo_code = _normalize_promocode_input(payload_data.promocode)
        promo_reservation_id: str | None = None
        promo_code_id: str | None = None
        discount_rub = 0
        if not promo_code and payload_data.promo_reservation_id:
            await whitelist_service.release_promocode_reservation(
                payload_data.promo_reservation_id,
                user_id=message.chat.id,
                reason="payment_without_promo",
                provider=TBANK_PROVIDER,
                currency="RUB",
            )
            await store.set_promo_reservation_id(message.chat.id, None)
        if promo_code:
            reserve = await whitelist_service.reserve_promocode(
                user_id=message.chat.id,
                code=promo_code,
                credits=amount,
                stars_original=checkout_rub,
                ttl_seconds=PROMO_RESERVATION_TTL_SECONDS,
                previous_reservation_id=payload_data.promo_reservation_id,
                provider=TBANK_PROVIDER,
                currency="RUB",
            )
            if str(reserve.get("status")) != "ok":
                reason = _human_promocode_reason(str(reserve.get("reason", "invalid_discount")), language)
                await store.set_promo_reservation_id(message.chat.id, None)
                await whitelist_service.record_billing_event(
                    provider=TBANK_PROVIDER,
                    event_type="promocode_reserve_rejected",
                    user_id=message.chat.id,
                    reason=str(reserve.get("reason", "invalid_discount")),
                    meta={
                        "code": promo_code,
                        "credits": amount,
                        "rub_original": checkout_rub,
                    },
                )
                await message.answer(_t(language, "promo_invoice_unavailable", reason=reason))
                return
            promo_reservation_id = str(reserve.get("reservation_id"))
            promo_code_id = str(reserve.get("code_id"))
            promo_code = str(reserve.get("code") or promo_code)
            checkout_rub = int(reserve.get("stars_final") or checkout_rub)
            discount_rub = int(reserve.get("discount_stars") or 0)

        amount_rub = Decimal(str(checkout_rub))
        amount_original_rub = Decimal(str(rub_amount))
        try:
            intent = await whitelist_service.create_checkout_intent(
                provider=TBANK_PROVIDER,
                user_id=message.chat.id,
                credits=amount,
                amount=amount_rub,
                currency="RUB",
                promo_reservation_id=promo_reservation_id,
                promo_code_id=promo_code_id,
                amount_original=(amount_original_rub if promo_reservation_id else None),
                discount_amount=(Decimal(str(discount_rub)) if promo_reservation_id else None),
            )
        except Exception:
            logger.exception(
                "tbank_intent_create_failed chat_id=%s credits=%s rub=%s",
                message.chat.id,
                amount,
                checkout_rub,
            )
            await message.answer(_t(language, "tbank_unavailable"))
            return
        if str(intent.get("status")) != "ok":
            logger.warning(
                "tbank_intent_invalid chat_id=%s credits=%s rub=%s status=%s",
                message.chat.id,
                amount,
                checkout_rub,
                intent.get("status"),
            )
            if promo_reservation_id:
                await whitelist_service.release_promocode_reservation(
                    promo_reservation_id,
                    user_id=message.chat.id,
                    reason="tbank_intent_invalid",
                    provider=TBANK_PROVIDER,
                    currency="RUB",
                )
                await store.set_promo_reservation_id(message.chat.id, None)
            await message.answer(_t(language, "tbank_unavailable"))
            return

        payment_uuid = str(intent.get("payment_id") or "").strip()
        if not payment_uuid:
            if promo_reservation_id:
                await whitelist_service.release_promocode_reservation(
                    promo_reservation_id,
                    user_id=message.chat.id,
                    reason="tbank_payment_id_missing",
                    provider=TBANK_PROVIDER,
                    currency="RUB",
                )
                await store.set_promo_reservation_id(message.chat.id, None)
            await message.answer(_t(language, "tbank_unavailable"))
            return

        # Keep payment description plain-text: some acquiring UIs replace emoji/special symbols with '?'.
        description = f"VizuAI top-up: {amount} credits"
        try:
            init_result = await tbank_service.init_payment(
                order_id=payment_uuid,
                amount_rub=amount_rub,
                description=description,
                customer_key=str(message.chat.id),
            )
        except Exception:
            logger.exception(
                "tbank_init_failed chat_id=%s payment_id=%s credits=%s rub=%s",
                message.chat.id,
                payment_uuid,
                amount,
                rub_amount,
            )
            try:
                await whitelist_service.mark_tbank_payment_failed(
                    payment_id=payment_uuid,
                    reason="init_failed",
                    error_meta={"stage": "init", "credits": amount, "rub": checkout_rub},
                )
            except Exception:
                logger.exception(
                    "tbank_mark_failed_after_init_error chat_id=%s payment_id=%s",
                    message.chat.id,
                    payment_uuid,
                )
            await message.answer(_t(language, "tbank_unavailable"))
            return

        try:
            await whitelist_service.mark_tbank_payment_initialized(
                payment_id=payment_uuid,
                provider_payment_id=init_result.payment_id,
                init_meta={
                    "status": init_result.status,
                    "payment_url_set": bool(init_result.payment_url),
                },
            )
        except Exception:
            logger.exception(
                "tbank_mark_initialized_failed chat_id=%s payment_id=%s provider_payment_id=%s",
                message.chat.id,
                payment_uuid,
                init_result.payment_id,
            )
            try:
                await whitelist_service.mark_tbank_payment_failed(
                    payment_id=payment_uuid,
                    reason="mark_initialized_failed",
                    error_meta={
                    "stage": "mark_initialized",
                    "provider_payment_id": init_result.payment_id,
                },
            )
            except Exception:
                logger.exception(
                    "tbank_mark_failed_after_mark_initialized_error chat_id=%s payment_id=%s",
                    message.chat.id,
                    payment_uuid,
                )
            await message.answer(_t(language, "tbank_unavailable"))
            return

        logger.info(
            "tbank_link_created chat_id=%s payment_id=%s provider_payment_id=%s credits=%s rub=%s",
            message.chat.id,
            payment_uuid,
            init_result.payment_id,
            amount,
            checkout_rub,
        )
        if promo_reservation_id:
            await store.set_promo_reservation_id(message.chat.id, promo_reservation_id)
        else:
            await store.set_promo_reservation_id(message.chat.id, None)
        version, issued_ts = await _next_ui_context(message.chat.id)
        sent = await _send_inline_screen(
            message,
            state,
            _t(language, "tbank_payment_created", amount=amount, rub=checkout_rub),
            _tbank_payment_link_inline_keyboard(
                language,
                version,
                issued_ts,
                init_result.payment_url,
            ),
        )
        if promo_reservation_id and promo_code:
            await message.answer(
                _t(
                    language,
                    "tbank_package_selected_discounted",
                    amount=amount,
                    rub=checkout_rub,
                    code=promo_code,
                )
            )
            await message.answer(
                _t(
                    language,
                    "promo_price_line_rub",
                    code=promo_code,
                    original=rub_amount,
                    final=checkout_rub,
                )
            )
        else:
            await message.answer(_t(language, "tbank_package_selected", amount=amount, rub=checkout_rub))
        sent_message_id = getattr(sent, "message_id", None)
        if isinstance(sent_message_id, int):
            try:
                await whitelist_service.record_billing_event(
                    provider="tbank_sbp",
                    event_type="tbank_payment_link_sent",
                    user_id=message.chat.id,
                    payment_id=payment_uuid,
                    provider_payment_id=init_result.payment_id,
                    telegram_payment_charge_id=None,
                    currency="RUB",
                    stars_amount=None,
                    credits_amount=amount,
                    reason=None,
                    meta={"chat_id": message.chat.id, "message_id": sent_message_id},
                )
            except Exception:
                logger.exception(
                    "tbank_payment_link_event_failed chat_id=%s payment_id=%s message_id=%s",
                    message.chat.id,
                    payment_uuid,
                    sent_message_id,
                )

    async def start_processing(
        message: Message,
        state: FSMContext,
        payload: UserPayload,
        *,
        actor_user: TelegramUser | None = None,
    ) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        mode = _resolve_mode(payload.mode)
        units_to_spend = _units_for_mode(mode)

        if not payload.photo:
            if mode == MODE_RENDER_ONLY:
                await _show_render_compose_screen(message, state, lang)
                return
            if mode == MODE_FURNITURE_SEARCH:
                await _show_furniture_compose_screen(message, state, lang)
                return
            await message.answer(_build_ready_card(lang, payload))
            return
        effective_user = actor_user or message.from_user
        await whitelist_service.ensure_user(
            message.chat.id,
            username=effective_user.username if effective_user else None,
            first_name=effective_user.first_name if effective_user else None,
            last_name=effective_user.last_name if effective_user else None,
        )

        reserve = await whitelist_service.reserve_units(message.chat.id, units_to_spend)
        if not reserve.get("allowed"):
            logger.info(
                "start_processing_denied chat_id=%s mode=%s units=%s reason=%s",
                message.chat.id,
                mode,
                units_to_spend,
                reserve.get("reason"),
            )
            paywall_key = "balance_paywall_furniture" if mode == MODE_FURNITURE_SEARCH else "balance_paywall_render"
            examples_key = "furniture_examples_url" if mode == MODE_FURNITURE_SEARCH else "render_examples_url"
            await _show_balance_screen(
                message,
                state,
                lang,
                text_override=_t(lang, paywall_key, examples_url=_t(lang, examples_key)),
                preserve_previous_inline=True,
                reuse_current_version=True,
            )
            return

        await state.set_state(UserStates.menu)
        user_text = "" if _is_no_wishes_text(payload.text) else (payload.text or "")
        await _record_action_safe(
            message.chat.id,
            "process_started",
            source=mode,
            meta={"mode": mode, "units_spent": units_to_spend},
        )
        job_id = await orchestrator.start_job(
            message.chat.id,
            payload.photo,
            user_text,
            style_reference=payload.style_reference,
            mode=mode,
            units_spent=units_to_spend,
        )
        logger.info(
            "start_job chat_id=%s job_id=%s mode=%s units=%s",
            message.chat.id,
            job_id,
            mode,
            units_to_spend,
        )
        await store.add_active_job(message.chat.id, job_id)
        await _show_processing_screen(message, state, lang)
        await send_processing(
            message.bot,
            message.chat.id,
            _t(lang, "start_processing_units", units=units_to_spend),
        )
        if _has_style_reference(payload):
            await send_processing(
                message.bot,
                message.chat.id,
                _t(lang, "start_processing_style_ref"),
            )

        async def poll_job() -> None:
            furniture_overlay_pending: bytes | None = None
            render_preview_pending: bytes | None = None
            detached = False
            while True:
                current_status, result_payload = await orchestrator.poll_job(job_id)
                latest_payload = await store.get_payload(message.chat.id)
                if job_id not in set(latest_payload.active_jobs):
                    if not detached:
                        detached = True
                        logger.info(
                            "poll_job_detached_continue chat_id=%s job_id=%s",
                            message.chat.id,
                            job_id,
                        )
                if current_status == "rendered" and result_payload:
                    if detached:
                        if mode == MODE_FURNITURE_SEARCH:
                            furniture_overlay_pending = result_payload
                        else:
                            render_preview_pending = result_payload
                    else:
                        await store.set_last_result_photo(message.chat.id, result_payload)
                        if mode == MODE_FURNITURE_SEARCH:
                            # Keep overlay image until the summary links are ready, then send together.
                            furniture_overlay_pending = result_payload
                        else:
                            await send_render(message.bot, message.chat.id, result_payload)
                if current_status == "done":
                    debug_payload = redis_client.get_debug(job_id)
                    if detached:
                        await send_processing(
                            message.bot,
                            message.chat.id,
                            _t(lang, "detached_result_ready"),
                        )
                    if render_preview_pending:
                        await store.set_last_result_photo(message.chat.id, render_preview_pending)
                        await send_render(message.bot, message.chat.id, render_preview_pending)
                    if mode == MODE_FURNITURE_SEARCH and furniture_overlay_pending:
                        await store.set_last_result_photo(message.chat.id, furniture_overlay_pending)
                        await send_render(
                            message.bot,
                            message.chat.id,
                            furniture_overlay_pending,
                        )
                    if result_payload:
                        text_payload = _decode_text_payload(result_payload)
                        if text_payload:
                            parse_mode = "HTML" if mode == MODE_FURNITURE_SEARCH else None
                            await send_processing(
                                message.bot,
                                message.chat.id,
                                text_payload,
                                parse_mode=parse_mode,
                            )
                    simple_debug = (
                        debug_payload.get("simple_pipeline")
                        if isinstance(debug_payload, dict)
                        and isinstance(debug_payload.get("simple_pipeline"), dict)
                        else {}
                    )
                    notice_key = (
                        str(simple_debug.get("style_reference_notice_key"))
                        if simple_debug.get("style_reference_notice_key")
                        else None
                    )
                    if notice_key in TEXTS:
                        await send_processing(
                            message.bot,
                            message.chat.id,
                            _t(lang, notice_key),
                        )
                    if is_admin(message.chat.id) and redis_client.get_debug_mode(
                        message.chat.id
                    ):
                        if debug_payload:
                            await send_debug_payload(
                                message.bot, message.chat.id, job_id, debug_payload
                            )
                    await store.remove_active_job(message.chat.id, job_id)
                    if not detached:
                        await _show_post_result_screen(
                            message,
                            state,
                            lang,
                            _post_result_prompt(lang, mode),
                            mode,
                        )
                    return
                if current_status == "failed":
                    debug_payload = redis_client.get_debug(job_id)
                    if detached:
                        await send_processing(
                            message.bot,
                            message.chat.id,
                            _t(lang, "detached_result_failed"),
                        )
                    if is_admin(message.chat.id) and redis_client.get_debug_mode(
                        message.chat.id
                    ):
                        if debug_payload:
                            await send_debug_payload(
                                message.bot, message.chat.id, job_id, debug_payload
                            )
                    await store.remove_active_job(message.chat.id, job_id)
                    if not detached:
                        await _show_post_result_screen(
                            message,
                            state,
                            lang,
                            _t(lang, "failed_next"),
                            mode,
                        )
                    return
                await asyncio.sleep(3)

        asyncio.create_task(poll_job())

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext) -> None:
        start_source = _extract_start_source(message.text)
        await whitelist_service.ensure_user(
            message.chat.id,
            username=message.from_user.username if message.from_user else None,
            first_name=message.from_user.first_name if message.from_user else None,
            last_name=message.from_user.last_name if message.from_user else None,
            acquisition_source=start_source,
        )
        await store.set_language(message.chat.id, LANG_RU)
        await state.set_state(UserStates.menu)
        await _set_chat_commands(message.bot, message.chat.id, LANG_RU)
        await message.answer(
            _t(LANG_RU, "start_text"),
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="HTML",
        )
        await _show_main_menu_screen(message, state, LANG_RU)

    @router.message(Command("cancel"))
    async def cmd_cancel(message: Message, state: FSMContext) -> None:
        await reset_user_session(
            message,
            state,
            reason="cancel",
            notice_key="canceled",
        )

    @router.message(F.text.casefold() == _t(LANG_RU, "cancel").casefold())
    @router.message(F.text.casefold() == _t(LANG_EN, "cancel").casefold())
    async def text_cancel(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        current = await state.get_state()
        lang = await store.get_language(message.chat.id)
        if current == UserStates.confirm_reset.state:
            await state.set_state(UserStates.settings)
            await _show_settings_screen(message, state, lang)
            return
        if current == UserStates.settings.state:
            await state.set_state(UserStates.menu)
            await _show_main_menu_screen(message, state, lang)
            return
        if current == UserStates.text.state:
            payload = await store.get_payload(message.chat.id)
            mode = _resolve_mode(payload.mode)
            await state.set_state(UserStates.photo)
            if mode == MODE_FURNITURE_SEARCH:
                await _show_furniture_compose_screen(message, state, lang)
                return
            await message.answer(_t(lang, "ask_photo"))
            return
        if current == UserStates.photo.state:
            await state.set_state(UserStates.mode_select)
            await send_mode_overview(message, state, lang)
            return
        await state.set_state(UserStates.menu)
        await _show_main_menu_screen(message, state, lang)

    @router.message(Command("reset"))
    async def cmd_reset(message: Message, state: FSMContext) -> None:
        lang = await store.get_language(message.chat.id)
        await state.set_state(UserStates.confirm_reset)
        await _show_reset_confirm_screen(message, state, lang)

    @router.message(Command("help"))
    async def cmd_help(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await state.set_state(UserStates.menu)
        await _show_help_root_screen(message, state, lang)

    @router.message(Command("menu"))
    async def cmd_menu(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await state.set_state(UserStates.menu)
        await _show_main_menu_screen(message, state, lang)

    @router.message(Command("balance"))
    async def cmd_balance(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await state.set_state(UserStates.packages)
        await state.update_data(**{PAYMENT_METHOD_KEY: "stars"})
        await _show_balance_screen(message, state, lang)

    @router.message(Command("buy"))
    async def cmd_buy(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await state.set_state(UserStates.packages)
        await state.update_data(**{PAYMENT_METHOD_KEY: "stars"})
        await _show_balance_screen(message, state, lang)

    @router.message(Command("promo"))
    async def cmd_promo(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        payload = await store.get_payload(message.chat.id)
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            if payload.promocode:
                await message.answer(_t(lang, "promo_current", code=payload.promocode))
            else:
                await message.answer(_t(lang, "promo_activate_prompt"))
            return
        code = _normalize_promocode_input(parts[1])
        if not code:
            await message.answer(_t(lang, "promo_activate_prompt"))
            return
        await _apply_promocode(message.chat.id, code, lang, message)

    @router.message(Command("paysupport"))
    async def cmd_paysupport(message: Message) -> None:
        lang = await store.get_language(message.chat.id)
        await whitelist_service.record_billing_event(
            provider=STARS_PROVIDER,
            event_type="payment_support_requested",
            user_id=message.chat.id,
            reason="user_paysupport_command",
            meta={"lang": lang},
        )
        await message.answer(_t(lang, "paysupport_text"), reply_markup=ReplyKeyboardRemove())

    @router.message(Command("refund_reasons"))
    async def cmd_refund_reasons(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        await message.answer(
            "\n".join(
                [
                    "Refund reasons (use in /refund_stars <payment_id> <reason>):",
                    "- service_failure_no_result: наша ошибка, результат пользователю не доставлен",
                    "- duplicate_charge: повторная/ошибочная оплата",
                    "- user_requested: запрос пользователя на возврат",
                    "- support_goodwill: возврат по решению поддержки",
                    "- fraud_or_abuse: антифрод/злоупотребление",
                    "- other_support: прочий кейс поддержки",
                    "Любая другая причина сохраняется как custom:<reason>",
                ]
            )
        )

    @router.message(UserStates.language, F.text.casefold() == "русский")
    @router.message(UserStates.language, F.text.casefold() == "english")
    async def choose_language(message: Message, state: FSMContext) -> None:
        text = (message.text or "").strip().casefold()
        selected = LANGUAGE_CHOICES.get("Русский") if text == "русский" else None
        if text == "english":
            selected = LANGUAGE_CHOICES.get("English")
        if not selected:
            return
        await store.set_language(message.chat.id, selected)
        await state.set_state(UserStates.menu)
        await _set_chat_commands(message.bot, message.chat.id, selected)
        await message.answer(
            f"{_t(selected, 'language_updated')}\n\n{_t(selected, 'greeting')}",
            reply_markup=ReplyKeyboardRemove(),
        )
        await _show_main_menu_screen(message, state, selected)

    @router.message(UserStates.language, F.text)
    async def choose_language_unknown(message: Message) -> None:
        lang = await store.get_language(message.chat.id)
        await message.answer(_t(lang, "language_invalid"))

    @router.message(Command("stats"))
    async def cmd_stats(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        metrics = redis_client.get_daily_metrics()
        costs = redis_client.get_daily_costs()
        requests = metrics.get("requests", 0)
        success = metrics.get("success", 0)
        success_rate = round((success / requests) * 100) if requests else 0
        total_cost = sum(costs.values())
        await message.answer(
            f"{requests} запросов, {success_rate}% success, ${total_cost:.2f}"
        )

    @router.message(Command("costs"))
    async def cmd_costs(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        costs = redis_client.get_daily_costs()
        if not costs:
            await message.answer("Расходов пока нет.")
            return
        lines = [f"{name}: ${amount:.2f}" for name, amount in costs.items()]
        total = sum(costs.values())
        lines.append(f"Total: ${total:.2f}")
        await message.answer("\n".join(lines))

    @router.message(Command("jobs_active"))
    async def cmd_jobs_active(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split() if message.text else []
        limit = 10
        if len(parts) >= 2:
            try:
                limit = max(int(parts[1]), 1)
            except ValueError:
                await message.answer("Формат: /jobs_active [limit]")
                return
        active_count = redis_client.get_global_active_job_count()
        active_jobs = redis_client.get_global_active_jobs(limit=limit)
        configured_limit = int(
            getattr(settings, "WORKER_GLOBAL_ACTIVE_JOBS_LIMIT", 2) or 2
        )
        wait_seconds = float(
            getattr(settings, "WORKER_GLOBAL_ACTIVE_JOBS_WAIT_SECONDS", 1.0) or 1.0
        )
        lease_seconds = int(
            getattr(settings, "WORKER_GLOBAL_ACTIVE_JOBS_LEASE_SECONDS", 7200) or 7200
        )
        lines = [
            "Global jobs limiter",
            f"active={active_count} limit={configured_limit}",
            f"wait_seconds={wait_seconds:.1f} lease_seconds={lease_seconds}",
            "key=jobs:global:active",
        ]
        if active_jobs:
            lines.append("active_jobs:")
            for item in active_jobs:
                lines.append(
                    f"- {item.get('job_id')} ttl={item.get('ttl_sec')}s"
                )
        else:
            lines.append("active_jobs: none")
        await message.answer("\n".join(lines))

    @router.message(Command("debug"))
    async def cmd_debug(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split(maxsplit=1) if message.text else []
        if len(parts) < 2:
            await message.answer("Укажите job_id: /debug <job_id>")
            return
        job_id = parts[1].strip()
        payload = redis_client.get_debug(job_id)
        if not payload:
            await message.answer("Нет данных для этого job_id.")
            return
        await send_debug_payload(message.bot, message.chat.id, job_id, payload)

    @router.message(Command("debug_on"))
    async def cmd_debug_on(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        redis_client.set_debug_mode(message.chat.id, True)
        await message.answer("Debug-режим включен. Буду отправлять все этапы.")

    @router.message(Command("debug_off"))
    async def cmd_debug_off(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        redis_client.set_debug_mode(message.chat.id, False)
        await message.answer("Debug-режим выключен. Буду отправлять только финал.")

    @router.message(Command("debug_status"))
    async def cmd_debug_status(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        enabled = redis_client.get_debug_mode(message.chat.id)
        await message.answer("Debug-режим: ON" if enabled else "Debug-режим: OFF")

    @router.message(Command("whitelist_add"))
    async def cmd_whitelist_add(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split() if message.text else []
        if len(parts) < 3:
            await message.answer(
                "Формат: /whitelist_add <user_id> <credits|unlimited>\n"
                "Легаси: /whitelist_add <user_id> <days> <requests>"
            )
            return
        try:
            user_id = int(parts[1])
        except ValueError:
            await message.answer("user_id должен быть числом.")
            return

        days: int | None = None
        requests: int | None = None
        used_legacy_format = len(parts) > 3
        if used_legacy_format:
            try:
                raw_days = int(parts[2])
                raw_requests = int(parts[3])
            except ValueError:
                await message.answer("days и requests должны быть числами.")
                return
            days = raw_days if raw_days > 0 else None
            requests = raw_requests if raw_requests > 0 else None
        else:
            mode = parts[2].strip().lower()
            if mode in {"unlimited", "manual", "inf"}:
                days = None
                requests = None
            else:
                try:
                    credits = int(parts[2])
                except ValueError:
                    await message.answer("credits должен быть числом или 'unlimited'.")
                    return
                if credits <= 0:
                    await message.answer("credits должен быть больше 0.")
                    return
                days = None
                requests = credits

        await whitelist_service.add_user_to_whitelist(user_id, days, requests)
        if requests is None:
            await message.answer(f"Пользователь {user_id}: включен безлимитный доступ")
            return
        suffix = " (legacy-формат)" if used_legacy_format else ""
        await message.answer(f"Пользователь {user_id}: выдано {requests} кредитов{suffix}")

    @router.message(Command("whitelist_remove"))
    async def cmd_whitelist_remove(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split() if message.text else []
        if len(parts) < 2:
            await message.answer("Формат: /whitelist_remove <user_id>")
            return
        try:
            user_id = int(parts[1])
        except ValueError:
            await message.answer("user_id должен быть числом.")
            return
        user = await whitelist_service.remove_user_from_whitelist(user_id)
        if not user:
            await message.answer("Пользователь не найден.")
            return
        await message.answer(f"Пользователь {user_id} удален из whitelist.")

    @router.message(Command("whitelist_status"))
    async def cmd_whitelist_status(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split() if message.text else []
        if len(parts) < 2:
            await message.answer("Формат: /whitelist_status <user_id>")
            return
        try:
            user_id = int(parts[1])
        except ValueError:
            await message.answer("user_id должен быть числом.")
            return
        status = await whitelist_service.get_whitelist_status(user_id)
        expires = status.get("expires_at")
        remaining = status.get("remaining_requests")
        expires_text = expires.strftime("%Y-%m-%d") if expires else "never"
        remaining_text = "unlimited" if remaining is None else str(remaining)
        await message.answer(
            f"user_id={user_id} whitelisted={status.get('whitelisted')} "
            f"reason={status.get('reason')} expires={expires_text} remaining={remaining_text}"
        )

    @router.message(Command("whitelist_reset"))
    async def cmd_whitelist_reset(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split() if message.text else []
        if len(parts) < 2:
            await message.answer("Формат: /whitelist_reset <user_id>")
            return
        try:
            user_id = int(parts[1])
        except ValueError:
            await message.answer("user_id должен быть числом.")
            return
        user = await whitelist_service.reset_quota(user_id)
        if not user:
            await message.answer("Пользователь не найден.")
            return
        await message.answer(f"Квота для {user_id} сброшена.")

    @router.message(Command("whitelist_list"))
    async def cmd_whitelist_list(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        users = await whitelist_service.list_whitelisted_users()
        if not users:
            await message.answer("Whitelist пуст.")
            return
        lines = [f"Whitelist users: {len(users)}"]
        for item in users:
            username = f"@{item['username']}" if item.get("username") else "—"
            expires = (
                item["expires_at"].strftime("%Y-%m-%d")
                if item.get("expires_at")
                else "never"
            )
            remaining = (
                "unlimited"
                if item.get("remaining_requests") is None
                else str(item["remaining_requests"])
            )
            source = item.get("source", "unknown")
            lines.append(
                f"{item['user_id']} {username} {source} expires={expires} remaining={remaining}"
            )
        await message.answer("\n".join(lines))

    @router.message(Command("refund_lookup"))
    async def cmd_refund_lookup(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split(maxsplit=1) if message.text else []
        if len(parts) < 2:
            await message.answer("Формат: /refund_lookup <payment_id|provider_payment_id|telegram_charge_id>")
            return
        query = parts[1].strip()
        result = await whitelist_service.lookup_payment(STARS_PROVIDER, query)
        status = str(result.get("status", "unknown"))
        if status != "ok":
            await message.answer(f"Не найдено ({status}).")
            return
        paid_at = result.get("paid_at")
        refunded_at = result.get("refunded_at")
        paid_at_text = paid_at.strftime("%Y-%m-%d %H:%M:%S") if paid_at else "—"
        refunded_at_text = refunded_at.strftime("%Y-%m-%d %H:%M:%S") if refunded_at else "—"
        remaining = result.get("remaining_requests")
        remaining_text = "unlimited" if remaining is None else str(remaining)
        await message.answer(
            "\n".join(
                [
                    f"payment_id={result.get('payment_id')}",
                    f"user_id={result.get('user_id')}",
                    f"status={result.get('payment_status')}",
                    f"provider_payment_id={result.get('provider_payment_id')}",
                    f"telegram_charge_id={result.get('telegram_payment_charge_id')}",
                    f"credits_amount={result.get('credits_amount')}",
                    f"stars_amount={result.get('stars_amount')} {result.get('currency')}",
                    f"paid_at={paid_at_text}",
                    f"refunded_at={refunded_at_text}",
                    f"user_remaining={remaining_text}",
                ]
            )
        )

    @router.message(Command("refund_stars"))
    async def cmd_refund_stars(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split(maxsplit=2) if message.text else []
        if len(parts) < 2:
            await message.answer("Формат: /refund_stars <payment_id> [reason]")
            return

        payment_id = parts[1].strip()
        reason_raw = parts[2].strip() if len(parts) > 2 else ""
        reason = _normalize_refund_reason(reason_raw)
        logger.info(
            "stars_refund_admin_requested payment_id=%s reason=%s admin_chat_id=%s",
            payment_id,
            reason,
            message.chat.id,
        )

        start_result = await whitelist_service.start_refund(STARS_PROVIDER, payment_id)
        start_status = str(start_result.get("status", "unknown"))
        if start_status != "ready":
            await message.answer(
                f"Refund отклонен ({start_status}). "
                f"remaining={start_result.get('remaining_requests')} required={start_result.get('required_credits')}"
            )
            return

        user_id = int(start_result["user_id"])
        telegram_charge_id = str(start_result["telegram_payment_charge_id"])
        try:
            refunded = await message.bot.refund_star_payment(
                user_id=user_id,
                telegram_payment_charge_id=telegram_charge_id,
            )
        except Exception as exc:
            logger.exception(
                "stars_refund_api_exception payment_id=%s user_id=%s",
                payment_id,
                user_id,
            )
            finalize = await whitelist_service.finalize_refund(
                STARS_PROVIDER,
                payment_id,
                success=False,
                reason=reason,
                error=str(exc),
            )
            await message.answer(f"Ошибка refund API: {finalize.get('status')}")
            return

        if not refunded:
            finalize = await whitelist_service.finalize_refund(
                STARS_PROVIDER,
                payment_id,
                success=False,
                reason=reason,
                error="refund_star_payment returned False",
            )
            await message.answer(f"Refund не применен: {finalize.get('status')}")
            return

        finalize = await whitelist_service.finalize_refund(
            STARS_PROVIDER,
            payment_id,
            success=True,
            reason=reason,
        )
        final_status = str(finalize.get("status", "unknown"))
        if final_status != "applied":
            await message.answer(f"Refund API ok, но локальный commit не завершен ({final_status})")
            return
        await message.answer(
            "Refund выполнен: "
            f"payment_id={finalize.get('payment_id')} "
            f"user_id={finalize.get('user_id')} "
            f"remaining={finalize.get('remaining_requests')} "
            f"reason={reason}"
        )

    @router.message(Command("refund_lookup_tbank"))
    async def cmd_refund_lookup_tbank(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split(maxsplit=1) if message.text else []
        if len(parts) < 2:
            await message.answer("Формат: /refund_lookup_tbank <payment_id|provider_payment_id>")
            return
        query = parts[1].strip()
        result = await whitelist_service.lookup_payment(TBANK_PROVIDER, query)
        status = str(result.get("status", "unknown"))
        if status != "ok":
            await message.answer(f"Не найдено ({status}).")
            return
        paid_at = result.get("paid_at")
        refunded_at = result.get("refunded_at")
        paid_at_text = paid_at.strftime("%Y-%m-%d %H:%M:%S") if paid_at else "—"
        refunded_at_text = refunded_at.strftime("%Y-%m-%d %H:%M:%S") if refunded_at else "—"
        remaining = result.get("remaining_requests")
        remaining_text = "unlimited" if remaining is None else str(remaining)
        await message.answer(
            "\n".join(
                [
                    f"payment_id={result.get('payment_id')}",
                    f"user_id={result.get('user_id')}",
                    f"status={result.get('payment_status')}",
                    f"provider_payment_id={result.get('provider_payment_id')}",
                    f"credits_amount={result.get('credits_amount')}",
                    f"amount_rub={result.get('amount_rub')} {result.get('currency')}",
                    f"paid_at={paid_at_text}",
                    f"refunded_at={refunded_at_text}",
                    f"user_remaining={remaining_text}",
                ]
            )
        )

    @router.message(Command("refund_tbank"))
    async def cmd_refund_tbank(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        if not tbank_enabled or tbank_service is None:
            await message.answer("T-Bank не настроен.")
            return
        parts = message.text.split(maxsplit=2) if message.text else []
        if len(parts) < 2:
            await message.answer("Формат: /refund_tbank <payment_id> [reason]")
            return

        payment_id = parts[1].strip()
        reason_raw = parts[2].strip() if len(parts) > 2 else ""
        reason = _normalize_refund_reason(reason_raw)
        logger.info(
            "tbank_refund_admin_requested payment_id=%s reason=%s admin_chat_id=%s",
            payment_id,
            reason,
            message.chat.id,
        )

        start_result = await whitelist_service.start_refund(TBANK_PROVIDER, payment_id)
        start_status = str(start_result.get("status", "unknown"))
        if start_status != "ready":
            await message.answer(
                f"Refund/Cancel отклонен ({start_status}). "
                f"remaining={start_result.get('remaining_requests')} required={start_result.get('required_credits')}"
            )
            return

        provider_payment_id = str(start_result.get("provider_payment_id") or "").strip()
        if not provider_payment_id:
            await message.answer("Refund/Cancel отклонен (missing_provider_payment_id).")
            return

        lookup_status = None
        try:
            state_result = await tbank_service.get_state(payment_id=provider_payment_id)
            lookup_status = str(state_result.get("status") or "").strip() or None
        except Exception:
            logger.exception(
                "tbank_get_state_failed payment_id=%s provider_payment_id=%s",
                payment_id,
                provider_payment_id,
            )

        amount_kopecks = start_result.get("amount_kopecks")
        try:
            cancel_result = await tbank_service.cancel_payment(
                payment_id=provider_payment_id,
                amount_kopecks=int(amount_kopecks) if amount_kopecks is not None else None,
            )
        except Exception as exc:
            logger.exception(
                "tbank_cancel_api_exception payment_id=%s provider_payment_id=%s",
                payment_id,
                provider_payment_id,
            )
            finalize = await whitelist_service.finalize_refund(
                TBANK_PROVIDER,
                payment_id,
                success=False,
                reason=reason,
                error=str(exc),
                status=lookup_status,
            )
            await message.answer(f"Ошибка Cancel API: {finalize.get('status')}")
            return

        if not bool(cancel_result.get("success")):
            error_text = (
                f"code={cancel_result.get('error_code')} "
                f"message={cancel_result.get('message')} "
                f"details={cancel_result.get('details')}"
            ).strip()
            finalize = await whitelist_service.finalize_refund(
                TBANK_PROVIDER,
                payment_id,
                success=False,
                reason=reason,
                error=error_text,
                status=str(cancel_result.get("status") or lookup_status or ""),
            )
            await message.answer(f"Cancel не применен: {finalize.get('status')}")
            return

        finalize = await whitelist_service.finalize_refund(
            TBANK_PROVIDER,
            payment_id,
            success=True,
            reason=reason,
            status=str(cancel_result.get("status") or lookup_status or ""),
        )
        final_status = str(finalize.get("status", "unknown"))
        if final_status != "applied":
            await message.answer(f"Cancel API ok, но локальный commit не завершен ({final_status})")
            return
        await message.answer(
            "T-Bank refund/cancel выполнен: "
            f"payment_id={finalize.get('payment_id')} "
            f"user_id={finalize.get('user_id')} "
            f"mode={finalize.get('mode')} "
            f"remaining={finalize.get('remaining_requests')} "
            f"reason={reason}"
        )

    @router.message(Command("billing_report"))
    async def cmd_billing_report(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split() if message.text else []
        days = 7
        if len(parts) >= 2:
            try:
                days = max(int(parts[1]), 1)
            except ValueError:
                await message.answer("Формат: /billing_report [days]")
                return
        report = await whitelist_service.get_billing_report(days=days)
        summary = report.get("summary", {})
        payment_counts = report.get("payment_counts", {})
        payment_amounts = report.get("payment_amounts_xtr", {})
        payment_breakdown = report.get("payment_breakdown", [])
        invalid_reason_counts = report.get("invalid_reason_counts", {})

        def _format_amount(value: object) -> str:
            if isinstance(value, Decimal):
                return format(value.normalize(), "f").rstrip("0").rstrip(".") or "0"
            text = str(value or "0").strip()
            if "." in text:
                text = text.rstrip("0").rstrip(".")
            return text or "0"

        lines = [
            f"Billing report ({report.get('days')}d, since {report.get('since_utc')})",
            "Summary:",
            f"paid={summary.get('paid', 0)} refunded={summary.get('refunded', 0)} duplicate={summary.get('duplicate', 0)} invalid={summary.get('invalid', 0)}",
        ]

        if isinstance(payment_breakdown, list) and payment_breakdown:
            lines.append("Payments by provider/status:")
            for row in payment_breakdown:
                provider = str((row or {}).get("provider") or "unknown")
                status = str((row or {}).get("status") or "unknown")
                currency = str((row or {}).get("currency") or "NA")
                count = int((row or {}).get("count") or 0)
                amount = _format_amount((row or {}).get("amount"))
                lines.append(f"- {provider}/{status}: count={count} amount={amount} {currency}")
        elif payment_counts:
            lines.append("Payments by status:")
            for status in sorted(payment_counts.keys()):
                lines.append(
                    f"- {status}: count={payment_counts.get(status, 0)} amount={_format_amount(payment_amounts.get(status, 0))} XTR"
                )
        else:
            lines.append("Payments by status:")
            lines.append("- no data")
        lines.append("Invalid reasons:")
        if invalid_reason_counts:
            for reason in sorted(invalid_reason_counts.keys()):
                lines.append(f"- {reason}: {invalid_reason_counts[reason]}")
        else:
            lines.append("- no data")
        await message.answer("\n".join(lines))

    @router.message(Command("billing_suspicious"))
    async def cmd_billing_suspicious(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split() if message.text else []
        days = 7
        if len(parts) >= 2:
            try:
                days = max(int(parts[1]), 1)
            except ValueError:
                await message.answer("Формат: /billing_suspicious [days]")
                return
        report = await whitelist_service.get_billing_suspicious(days=days, refund_pending_minutes=10)
        issues = report.get("issues", [])
        lines = [
            f"Billing suspicious ({report.get('days')}d, since {report.get('since_utc')}): total={report.get('issues_total', 0)}",
        ]
        for item in issues[:20]:
            lines.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
        if len(issues) > 20:
            lines.append(f"... and {len(issues) - 20} more")
        await message.answer("\n".join(lines))

    @router.message(Command("billing_user"))
    async def cmd_billing_user(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split() if message.text else []
        if len(parts) < 2:
            await message.answer("Формат: /billing_user <user_id> [days]")
            return
        try:
            user_id = int(parts[1])
        except ValueError:
            await message.answer("user_id должен быть числом.")
            return
        days = 30
        if len(parts) >= 3:
            try:
                days = max(int(parts[2]), 1)
            except ValueError:
                await message.answer("Формат: /billing_user <user_id> [days]")
                return
        report = await whitelist_service.get_billing_user_report(user_id=user_id, days=days)
        lines = [
            f"Billing user={report.get('user_id')} ({report.get('days')}d, since {report.get('since_utc')})",
            f"user_is_active={report.get('user_is_active')} usage_left={report.get('user_usage_left')}",
            f"acquisition_source={report.get('acquisition_source') or '—'} recorded_at={report.get('acquisition_recorded_at') or '—'}",
            "event_counts:",
        ]
        event_counts = report.get("event_counts") or {}
        if event_counts:
            for key in sorted(event_counts.keys()):
                lines.append(f"- {key}: {event_counts[key]}")
        else:
            lines.append("- no events")
        payments = report.get("payments") or []
        if payments:
            lines.append("payments:")
            for item in payments[:10]:
                provider = str(item.get("provider") or "unknown")
                amount = str(item.get("amount") or "0")
                currency = str(item.get("currency") or "NA")
                lines.append(
                    f"- {item.get('payment_id')} provider={provider} status={item.get('status')} amount={amount} {currency} credits={item.get('credits_amount')}"
                )
        await message.answer("\n".join(lines))

    @router.message(Command("flow_report"))
    async def cmd_flow_report(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split() if message.text else []
        days = 7
        if len(parts) >= 2:
            try:
                days = max(1, min(int(parts[1]), 3650))
            except ValueError:
                await message.answer("Формат: /flow_report [days] [acquisition_source]")
                return
        source = parts[2].strip() if len(parts) >= 3 else None
        report = await whitelist_service.get_flow_report(days=days, acquisition_source=source)
        lines = [
            f"Flow report ({report.get('days')}d, since {report.get('since_utc')})",
            f"acquisition_source={report.get('acquisition_source') or '—'} users={report.get('users_total', 0)}",
            "screen_views:",
        ]
        screen_views = report.get("screen_views") or []
        if screen_views:
            for item in screen_views[:20]:
                lines.append(
                    f"- {item.get('screen_key')}: views={item.get('views', 0)} users={item.get('users', 0)}"
                )
        else:
            lines.append("- no data")
        lines.append("action_clicks:")
        action_clicks = report.get("action_clicks") or []
        if action_clicks:
            for item in action_clicks[:20]:
                lines.append(
                    f"- {item.get('action_key')}: clicks={item.get('clicks', 0)} users={item.get('users', 0)}"
                )
        else:
            lines.append("- no data")
        lines.append("last_screens:")
        last_screens = report.get("last_screens") or []
        if last_screens:
            for item in last_screens[:20]:
                lines.append(f"- {item.get('screen_key')}: users={item.get('users', 0)}")
        else:
            lines.append("- no data")
        await message.answer("\n".join(lines))

    @router.message(Command("flow_user"))
    async def cmd_flow_user(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split() if message.text else []
        if len(parts) < 2:
            await message.answer("Формат: /flow_user <user_id> [days]")
            return
        try:
            user_id = int(parts[1])
        except ValueError:
            await message.answer("user_id должен быть числом.")
            return
        days = 30
        if len(parts) >= 3:
            try:
                days = max(1, min(int(parts[2]), 3650))
            except ValueError:
                await message.answer("Формат: /flow_user <user_id> [days]")
                return
        report = await whitelist_service.get_flow_user_report(user_id=user_id, days=days)
        lines = [
            f"Flow user={report.get('user_id')} ({report.get('days')}d, since {report.get('since_utc')})",
            f"acquisition_source={report.get('acquisition_source') or '—'} recorded_at={report.get('acquisition_recorded_at') or '—'}",
            f"last_screen={report.get('last_screen_key') or '—'} last_screen_at={report.get('last_screen_at') or '—'}",
            "events:",
        ]
        events = report.get("events") or []
        if events:
            for item in events[:30]:
                tail = []
                if item.get("screen_key"):
                    tail.append(f"screen={item.get('screen_key')}")
                if item.get("action_key"):
                    tail.append(f"action={item.get('action_key')}")
                if item.get("source"):
                    tail.append(f"source={item.get('source')}")
                lines.append(
                    f"- {item.get('created_at')} {item.get('event_type')} {' '.join(tail)}".rstrip()
                )
        else:
            lines.append("- no events")
        await message.answer("\n".join(lines))

    @router.message(Command("billing_reconcile"))
    async def cmd_billing_reconcile(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split() if message.text else []
        limit_users = 20
        min_abs_delta = 1
        if len(parts) >= 2:
            try:
                limit_users = max(int(parts[1]), 1)
            except ValueError:
                await message.answer("Формат: /billing_reconcile [limit_users] [min_abs_delta]")
                return
        if len(parts) >= 3:
            try:
                min_abs_delta = max(int(parts[2]), 0)
            except ValueError:
                await message.answer("Формат: /billing_reconcile [limit_users] [min_abs_delta]")
                return
        report = await whitelist_service.get_billing_reconciliation(
            limit_users=limit_users,
            min_abs_delta=min_abs_delta,
        )
        lines = [
            "Billing reconcile",
            (
                f"users_checked={report.get('users_checked', 0)} "
                f"exact={report.get('exact_count', 0)} "
                f"mismatches={report.get('mismatches_total', 0)} "
                f"threshold={report.get('min_abs_delta', 0)}"
            ),
            (
                f"totals expected={report.get('expected_total', 0)} "
                f"actual={report.get('actual_total', 0)} "
                f"delta={report.get('total_delta', 0)}"
            ),
        ]
        mismatches = report.get("mismatches") or []
        if mismatches:
            lines.append("Top mismatches:")
            for item in mismatches:
                lines.append(
                    (
                        f"- user={item.get('user_id')} "
                        f"actual={item.get('actual')} expected={item.get('expected')} "
                        f"delta={item.get('delta')} "
                        f"(paid={item.get('paid_total')} admin={item.get('admin_grants')} "
                        f"spent={item.get('spent_total')} refunds={item.get('refund_total')})"
                    )
                )
        await message.answer("\n".join(lines))

    @router.message(Command("billing_webhook_deadletters"))
    async def cmd_billing_webhook_deadletters(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        parts = message.text.split() if message.text else []
        default_limit = int(getattr(settings, "BILLING_WEBHOOK_DEADLETTER_LIMIT", 20) or 20)
        limit = default_limit
        if len(parts) >= 2:
            try:
                limit = max(int(parts[1]), 1)
            except ValueError:
                await message.answer("Формат: /billing_webhook_deadletters [limit]")
                return
        dead = await whitelist_service.list_webhook_dead_letters(provider=TBANK_PROVIDER, limit=limit)
        if str(dead.get("status")) != "ok":
            await message.answer(f"Ошибка: {dead.get('status')}")
            return
        items = dead.get("items") or []
        lines = [
            f"Webhook dead letters ({TBANK_PROVIDER}) count={len(items)}",
        ]
        for item in items:
            lines.append(
                f"- {item.get('event_id')} attempts={item.get('attempts')} "
                f"order_id={item.get('order_id')} payment_id={item.get('provider_payment_id')} "
                f"error={item.get('last_error')}"
            )
        await message.answer("\n".join(lines))

    @router.message(Command("billing_webhook_replay"))
    async def cmd_billing_webhook_replay(message: Message) -> None:
        if not is_admin(message.chat.id):
            await message.answer("Недостаточно прав.")
            return
        if not tbank_enabled or tbank_service is None:
            await message.answer("T-Bank не настроен.")
            return
        parts = message.text.split() if message.text else []
        if len(parts) < 2:
            await message.answer("Формат: /billing_webhook_replay <event_id>")
            return
        event_id = parts[1].strip()
        event = await whitelist_service.get_webhook_event(event_id)
        if str(event.get("status")) != "ok":
            await message.answer(f"Событие не найдено ({event.get('status')})")
            return
        if str(event.get("provider")) != TBANK_PROVIDER:
            await message.answer("Replay поддерживается только для tbank_sbp")
            return
        payload = event.get("payload")
        if not isinstance(payload, dict):
            await message.answer("В событии нет payload для replay")
            return
        if not tbank_service.verify_notification(payload):
            await message.answer("Token в payload невалидный, replay отменен")
            return

        order_id = str(payload.get("OrderId") or "").strip()
        provider_payment_id = str(payload.get("PaymentId") or "").strip() or None
        status = str(payload.get("Status") or "").strip() or None
        success_value = payload.get("Success")
        if isinstance(success_value, bool):
            success = success_value
        elif isinstance(success_value, (int, float)):
            success = bool(success_value)
        else:
            success = str(success_value or "").strip().lower() in {"1", "true", "yes"}
        amount_kopecks_raw = payload.get("Amount")
        amount_kopecks = None
        if amount_kopecks_raw is not None:
            try:
                amount_kopecks = int(amount_kopecks_raw)
            except Exception:
                amount_kopecks = None
        try:
            result = await whitelist_service.apply_tbank_notification(
                order_id=order_id,
                provider_payment_id=provider_payment_id,
                status=status,
                success=success,
                amount_kopecks=amount_kopecks,
                payload=payload,
                accept_statuses=tbank_service.accepted_statuses(),
            )
        except Exception as exc:
            await whitelist_service.finalize_webhook_event(
                event_id=event_id,
                status="failed",
                error=str(exc),
            )
            await message.answer(f"Replay ошибка: {exc}")
            return

        result_status = str(result.get("status") or "unknown")
        event_status = "processed"
        if result_status in {"ignored", "invalid_amount", "partial_refund_ignored", "not_found"}:
            event_status = "ignored"
        await whitelist_service.finalize_webhook_event(
            event_id=event_id,
            status=event_status,
            error=None,
        )
        await message.answer(f"Replay завершен: result={result_status} event_status={event_status}")

    @router.message(UserStates.processing, F.text.casefold() == _t(LANG_RU, "settings_reset_flow").casefold())
    @router.message(UserStates.processing, F.text.casefold() == _t(LANG_EN, "settings_reset_flow").casefold())
    async def processing_reset_confirm(message: Message, state: FSMContext) -> None:
        lang = await store.get_language(message.chat.id)
        await state.set_state(UserStates.confirm_reset)
        await _show_reset_confirm_screen(message, state, lang)

    @router.message(UserStates.processing, F.photo)
    async def processing_photo_blocked(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await message.answer(_t(lang, "processing_busy"))

    @router.message(UserStates.processing, F.text)
    async def processing_text_blocked(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await message.answer(_t(lang, "processing_busy"))

    @router.message(F.text.casefold() == _t(LANG_RU, "main_menu").casefold())
    @router.message(F.text.casefold() == _t(LANG_EN, "main_menu").casefold())
    async def menu_main(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await state.set_state(UserStates.menu)
        await _show_main_menu_screen(message, state, lang)

    @router.message(F.text.casefold() == _t(LANG_RU, "help_menu").casefold())
    @router.message(F.text.casefold() == _t(LANG_EN, "help_menu").casefold())
    async def menu_help(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await state.set_state(UserStates.menu)
        await _show_help_root_screen(message, state, lang)

    @router.message(F.text.casefold() == _t(LANG_RU, "design_menu").casefold())
    @router.message(F.text.casefold() == _t(LANG_EN, "design_menu").casefold())
    async def menu_design(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await state.set_state(UserStates.mode_select)
        await send_mode_overview(message, state, lang)

    @router.message(UserStates.mode_select, F.text)
    async def mode_select(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        mode = _extract_mode_from_text(message.text, lang)
        if mode is None:
            await send_mode_overview(message, state, lang)
            return
        await store.clear_flow_payload(
            message.chat.id,
            clear_photo=True,
            clear_text=True,
            clear_style_reference=True,
            clear_job_id=True,
            clear_mode=False,
        )
        await store.set_mode(message.chat.id, mode)
        await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
        logger.info("mode_selected chat_id=%s mode=%s", message.chat.id, mode)
        if mode == MODE_RENDER_ONLY:
            await state.set_state(UserStates.photo)
            await _show_render_compose_screen(message, state, lang)
            return
        await state.set_state(UserStates.photo)
        if mode == MODE_FURNITURE_SEARCH:
            await _show_furniture_compose_screen(message, state, lang)
            return
        await message.answer(_t(lang, "ask_photo"))

    @router.message(UserStates.mode_select, F.photo)
    async def mode_select_photo_hint(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await send_mode_overview(message, state, lang)

    @router.message(F.text.casefold() == _t(LANG_RU, "packages_menu").casefold())
    @router.message(F.text.casefold() == _t(LANG_EN, "packages_menu").casefold())
    async def menu_packages(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        await state.set_state(UserStates.packages)
        await show_packages(message, state)

    @router.message(F.text.casefold() == _t(LANG_RU, "settings_menu").casefold())
    @router.message(F.text.casefold() == _t(LANG_EN, "settings_menu").casefold())
    async def menu_settings(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await state.set_state(UserStates.settings)
        await _show_settings_screen(message, state, lang)

    @router.message(F.text.casefold() == _t(LANG_RU, "language_menu").casefold())
    @router.message(F.text.casefold() == _t(LANG_EN, "language_menu").casefold())
    async def menu_language(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await state.set_state(UserStates.language)
        await _show_language_screen(message, state, lang)

    @router.message(UserStates.settings, F.text.casefold() == _t(LANG_RU, "settings_reset_flow").casefold())
    @router.message(UserStates.settings, F.text.casefold() == _t(LANG_EN, "settings_reset_flow").casefold())
    async def settings_reset_confirm(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await state.set_state(UserStates.confirm_reset)
        await _show_reset_confirm_screen(message, state, lang)

    @router.message(UserStates.confirm_reset, F.text.casefold() == _t(LANG_RU, "reset_confirm_yes").casefold())
    @router.message(UserStates.confirm_reset, F.text.casefold() == _t(LANG_EN, "reset_confirm_yes").casefold())
    async def settings_reset_confirm_yes(message: Message, state: FSMContext) -> None:
        await reset_user_session(
            message,
            state,
            reason="settings_reset",
            notice_key="reset_done",
        )

    @router.message(UserStates.confirm_reset, F.text.casefold() == _t(LANG_RU, "reset_confirm_cancel").casefold())
    @router.message(UserStates.confirm_reset, F.text.casefold() == _t(LANG_EN, "reset_confirm_cancel").casefold())
    async def settings_reset_confirm_cancel(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await state.set_state(UserStates.settings)
        await _show_settings_screen(message, state, lang)

    @router.callback_query(F.data.startswith(f"{CALLBACK_PREFIX}|"))
    async def handle_inline_callback(query: CallbackQuery, state: FSMContext) -> None:
        parsed = await _parse_and_validate_callback(query, state)
        if parsed is None:
            return
        action, message, lang = parsed
        chat_id = message.chat.id
        await _record_action_safe(
            chat_id,
            action,
            source="callback",
        )

        if action == "menu:main":
            await state.set_state(UserStates.menu)
            await _show_main_menu_screen(message, state, lang)
            return
        if action == "menu:help":
            await state.set_state(UserStates.menu)
            await _show_help_root_screen(message, state, lang)
            return
        if action == "help:root":
            await state.set_state(UserStates.menu)
            await _show_help_root_screen(message, state, lang)
            return
        if action == "help:examples":
            await state.set_state(UserStates.menu)
            await _show_help_root_screen(message, state, lang)
            return
        if action == "help:limits":
            await state.set_state(UserStates.menu)
            await _show_help_limits_screen(message, state, lang)
            return
        if action == "help:docs":
            await state.set_state(UserStates.menu)
            await _show_help_docs_screen(message, state, lang)
            return
        if action == "menu:design":
            await state.set_state(UserStates.mode_select)
            await send_mode_overview(message, state, lang)
            return
        if action == "menu:settings":
            await state.set_state(UserStates.settings)
            await _show_settings_screen(message, state, lang)
            return
        if action == "menu:balance":
            await state.set_state(UserStates.packages)
            await state.update_data(**{PAYMENT_METHOD_KEY: "stars"})
            await _show_balance_screen(message, state, lang)
            return

        if action in {"mode:render_only", "mode:furniture_search"}:
            mode_map = {
                "mode:render_only": MODE_RENDER_ONLY,
                "mode:furniture_search": MODE_FURNITURE_SEARCH,
            }
            mode = mode_map[action]
            await store.clear_flow_payload(
                chat_id,
                clear_photo=True,
                clear_text=True,
                clear_style_reference=True,
                clear_job_id=True,
                clear_mode=False,
            )
            await store.set_mode(chat_id, mode)
            await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
            logger.info("mode_selected chat_id=%s mode=%s source=inline", chat_id, mode)
            await state.set_state(UserStates.photo)
            if mode == MODE_RENDER_ONLY:
                await _show_render_compose_screen(message, state, lang)
                return
            await _show_furniture_compose_screen(message, state, lang)
            return

        if action == "settings:language":
            await state.set_state(UserStates.language)
            await _show_language_screen(message, state, lang)
            return
        if action == "settings:lang:ru":
            await store.set_language(chat_id, LANG_RU)
            await _set_chat_commands(message.bot, chat_id, LANG_RU)
            await state.set_state(UserStates.settings)
            await message.answer(_t(LANG_RU, "language_updated"))
            await _show_settings_screen(message, state, LANG_RU)
            return
        if action == "settings:lang:en":
            await store.set_language(chat_id, LANG_EN)
            await _set_chat_commands(message.bot, chat_id, LANG_EN)
            await state.set_state(UserStates.settings)
            await message.answer(_t(LANG_EN, "language_updated"))
            await _show_settings_screen(message, state, LANG_EN)
            return
        if action == "settings:reset":
            await state.set_state(UserStates.confirm_reset)
            await _show_reset_confirm_screen(message, state, lang)
            return
        if action == "settings:reset:confirm":
            await reset_user_session(
                message,
                state,
                reason="settings_reset",
                notice_key="reset_done",
            )
            return
        if action == "settings:reset:cancel":
            await state.set_state(UserStates.settings)
            await _show_settings_screen(message, state, lang)
            return

        if action == "pay:method:stars":
            await state.set_state(UserStates.packages)
            await state.update_data(**{PROMO_CAPTURE_KEY: False, PAYMENT_METHOD_KEY: "stars"})
            await _show_packages_screen(message, state, lang)
            return
        if action == "pay:method:tbank":
            await state.set_state(UserStates.packages)
            await state.update_data(**{PROMO_CAPTURE_KEY: False, PAYMENT_METHOD_KEY: "tbank"})
            if not tbank_enabled:
                await message.answer(_t(lang, "tbank_unavailable"))
                await _show_balance_screen(message, state, lang)
                return
            await _show_tbank_packages_screen(message, state, lang)
            return
        if action == "pay:promo_activate":
            await state.set_state(UserStates.packages)
            await state.update_data(**{PROMO_CAPTURE_KEY: True})
            await message.answer(_t(lang, "promo_activate_prompt"))
            return
        if action.startswith("pay:pack:"):
            await state.set_state(UserStates.packages)
            await state.update_data(**{PROMO_CAPTURE_KEY: False, PAYMENT_METHOD_KEY: "stars"})
            try:
                amount = int(action.split(":")[-1])
            except Exception:
                await _show_balance_screen(message, state, lang)
                return
            if amount not in PACKAGE_CATALOG_STARS:
                await _show_balance_screen(message, state, lang)
                return
            await _send_stars_invoice(message, lang, amount)
            return
        if action.startswith("pay:tbank_pack:"):
            await state.set_state(UserStates.packages)
            await state.update_data(**{PROMO_CAPTURE_KEY: False, PAYMENT_METHOD_KEY: "tbank"})
            try:
                amount = int(action.split(":")[-1])
            except Exception:
                await _show_balance_screen(message, state, lang)
                return
            if amount not in tbank_package_catalog:
                await _show_balance_screen(message, state, lang)
                return
            await _send_tbank_payment_link(message, state, lang, amount)
            return

        if action == "flow:new_photo":
            await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
            await store.clear_flow_payload(
                chat_id,
                clear_photo=True,
                clear_text=False,
                clear_job_id=False,
                clear_mode=False,
            )
            await state.set_state(UserStates.photo)
            payload = await store.get_payload(chat_id)
            mode = _resolve_mode(payload.mode)
            if mode == MODE_FURNITURE_SEARCH:
                await message.answer(_t(lang, "new_photo_prompt_furniture"))
            else:
                await message.answer(_t(lang, "new_photo_prompt"))
            return
        if action == "flow:style_ref":
            payload = await store.get_payload(chat_id)
            mode = _resolve_mode(payload.mode)
            if mode != MODE_RENDER_ONLY:
                await state.set_state(UserStates.photo)
                await _show_furniture_compose_screen(message, state, lang)
                return
            await state.update_data(**{STYLE_REF_CAPTURE_KEY: True})
            await state.set_state(UserStates.photo)
            await message.answer(_t(lang, "style_ref_prompt"))
            return
        if action == "flow:style_ref_remove":
            await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
            await store.clear_flow_payload(
                chat_id,
                clear_photo=False,
                clear_text=False,
                clear_style_reference=True,
                clear_job_id=False,
                clear_mode=False,
            )
            await message.answer(_t(lang, "style_ref_removed"))
            await state.set_state(UserStates.photo)
            await _show_render_compose_screen(message, state, lang)
            return
        if action == "flow:edit_text":
            await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
            payload = await store.get_payload(chat_id)
            mode = _resolve_mode(payload.mode)
            if mode == MODE_FURNITURE_SEARCH:
                await state.set_state(UserStates.photo)
                await _show_furniture_compose_screen(message, state, lang)
                return
            await state.set_state(UserStates.text)
            await message.answer(_t(lang, "edit_request_prompt"))
            return
        if action == "flow:edit_from_result":
            await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
            payload = await store.get_payload(chat_id)
            mode = _resolve_mode(payload.mode)
            if not payload.last_result_photo:
                await state.set_state(UserStates.photo)
                await message.answer(_t(lang, "edit_from_result_missing"))
                return
            await store.clear_flow_payload(
                chat_id,
                clear_photo=True,
                clear_text=True,
                clear_job_id=True,
                clear_mode=False,
            )
            await store.set_photo(chat_id, payload.last_result_photo)
            await store.set_mode(chat_id, mode)
            await state.set_state(UserStates.photo)
            if mode == MODE_FURNITURE_SEARCH:
                await _show_furniture_compose_screen(message, state, lang)
                return
            await _show_render_compose_screen_prefilled(
                message,
                state,
                lang,
                prefilled_hint_key="render_compose_edit_result_hint",
            )
            return
        if action == "flow:find_furniture_from_result":
            await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
            payload = await store.get_payload(chat_id)
            if not payload.last_result_photo:
                await state.set_state(UserStates.photo)
                await message.answer(_t(lang, "find_furniture_from_result_missing"))
                return
            await store.clear_flow_payload(
                chat_id,
                clear_photo=True,
                clear_text=True,
                clear_style_reference=True,
                clear_job_id=True,
                clear_mode=False,
            )
            await store.set_photo(chat_id, payload.last_result_photo)
            await store.set_mode(chat_id, MODE_FURNITURE_SEARCH)
            await state.set_state(UserStates.photo)
            await _show_furniture_compose_screen(
                message,
                state,
                lang,
                prefilled_from_render=True,
            )
            return
        if action == "flow:start":
            await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
            payload = await store.get_payload(chat_id)
            await start_processing(message, state, payload, actor_user=query.from_user)
            return
        if action == "flow:retry_variant":
            await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
            payload = await store.get_payload(chat_id)
            mode = _resolve_mode(payload.mode)
            await store.clear_flow_payload(
                chat_id,
                clear_photo=(mode == MODE_FURNITURE_SEARCH),
                clear_text=(mode == MODE_FURNITURE_SEARCH),
                clear_job_id=True,
                clear_mode=False,
            )
            await store.set_mode(chat_id, mode)
            await state.set_state(UserStates.photo)
            if mode == MODE_FURNITURE_SEARCH:
                await _show_furniture_compose_screen(message, state, lang)
                return
            await _show_render_compose_screen_prefilled(
                message,
                state,
                lang,
                prefilled_hint_key="render_compose_retry_hint",
            )
            return

        await state.set_state(UserStates.menu)
        await _show_main_menu_screen(message, state, lang)

    @router.message(F.text.casefold() == _t(LANG_RU, "new_photo").casefold())
    @router.message(F.text.casefold() == _t(LANG_EN, "new_photo").casefold())
    @router.message(F.text.casefold() == _t(LANG_RU, "post_new_photo").casefold())
    @router.message(F.text.casefold() == _t(LANG_EN, "post_new_photo").casefold())
    async def action_new_photo(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
        await store.clear_flow_payload(
            message.chat.id,
            clear_photo=True,
            clear_text=False,
            clear_job_id=False,
            clear_mode=False,
        )
        await state.set_state(UserStates.photo)
        payload = await store.get_payload(message.chat.id)
        mode = _resolve_mode(payload.mode)
        if mode == MODE_FURNITURE_SEARCH:
            await message.answer(_t(lang, "new_photo_prompt_furniture"))
        else:
            await message.answer(_t(lang, "new_photo_prompt"))

    @router.message(F.text.casefold() == _t(LANG_RU, "edit_request").casefold())
    @router.message(F.text.casefold() == _t(LANG_EN, "edit_request").casefold())
    @router.message(F.text.casefold() == _t(LANG_RU, "refine_request").casefold())
    @router.message(F.text.casefold() == _t(LANG_EN, "refine_request").casefold())
    async def action_edit_request(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
        payload = await store.get_payload(message.chat.id)
        mode = _resolve_mode(payload.mode)
        if mode == MODE_FURNITURE_SEARCH:
            await state.set_state(UserStates.photo)
            await _show_furniture_compose_screen(message, state, lang)
            return
        await state.set_state(UserStates.text)
        await message.answer(_t(lang, "edit_request_prompt"))

    @router.message(UserStates.packages, F.text)
    async def packages_select(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        state_data = await state.get_data()
        capture_promo = bool(state_data.get(PROMO_CAPTURE_KEY))
        payment_method = str(state_data.get(PAYMENT_METHOD_KEY) or "stars").strip().lower()
        if (message.text or "").strip().casefold() == _t(lang, "topup_method_tbank").casefold():
            await state.update_data(**{PROMO_CAPTURE_KEY: False, PAYMENT_METHOD_KEY: "tbank"})
            if not tbank_enabled:
                await message.answer(_t(lang, "tbank_unavailable"))
                await _show_balance_screen(message, state, lang)
                return
            await _show_tbank_packages_screen(message, state, lang)
            return
        if (message.text or "").strip().casefold() == _t(lang, "topup_method_stars").casefold():
            await state.update_data(**{PROMO_CAPTURE_KEY: False, PAYMENT_METHOD_KEY: "stars"})
            await _show_packages_screen(message, state, lang)
            return
        if capture_promo:
            code = _normalize_promocode_input(message.text)
            if not code:
                await message.answer(_t(lang, "promo_activate_prompt"))
            else:
                await _apply_promocode(message.chat.id, code, lang, message)
            await state.update_data(**{PROMO_CAPTURE_KEY: False})
            await _show_balance_screen(message, state, lang)
            return
        amount = _extract_package_amount(message.text)
        if amount is None:
            await _show_balance_screen(message, state, lang)
            return
        await state.update_data(**{PROMO_CAPTURE_KEY: False})
        if payment_method == "tbank":
            if amount not in tbank_package_catalog:
                await _show_tbank_packages_screen(message, state, lang)
                return
            await _send_tbank_payment_link(message, state, lang, amount)
            return
        if amount not in PACKAGE_CATALOG_STARS:
            await _show_packages_screen(message, state, lang)
            return
        await _send_stars_invoice(message, lang, amount)

    @router.pre_checkout_query()
    async def handle_pre_checkout_query(query: PreCheckoutQuery) -> None:
        lang = await store.get_language(query.from_user.id)
        payload_text = query.invoice_payload or ""
        payload_data, parse_error = _parse_invoice_payload_detailed(payload_text)
        is_valid, validation_reason, validation_meta = _validate_stars_payment_payload(
            payload_data,
            expected_user_id=int(query.from_user.id),
            currency=query.currency or "",
            total_amount=int(query.total_amount or 0),
        )
        if not is_valid:
            logger.warning(
                "pre_checkout_rejected user_id=%s currency=%s amount=%s reason=%s payload=%s",
                query.from_user.id,
                query.currency,
                query.total_amount,
                validation_reason or parse_error or "validation_failed",
                payload_text,
            )
            await whitelist_service.record_billing_event(
                provider=STARS_PROVIDER,
                event_type="stars_precheckout_rejected",
                user_id=query.from_user.id,
                currency=query.currency,
                stars_amount=int(query.total_amount or 0),
                reason=str(validation_reason or parse_error or "payload_validation_failed"),
                meta={
                    "stage": "pre_checkout",
                    "parse_error": parse_error,
                    **validation_meta,
                    **_payload_fingerprint(payload_text),
                },
            )
            await query.answer(ok=False, error_message=_t(lang, "payment_check_failed"))
            return
        if bool(payload_data.get("has_promocode")):
            promo_check = await whitelist_service.validate_promocode_reservation(
                reservation_id=str(payload_data.get("promo_reservation_id") or ""),
                user_id=int(query.from_user.id),
                promo_code_id=str(payload_data.get("promo_code_id") or ""),
                credits=int(payload_data.get("credits") or 0),
                stars_original=int(payload_data.get("stars_original") or 0),
                discount_stars=int(payload_data.get("discount_stars") or 0),
                stars_final=int(payload_data.get("stars") or 0),
            )
            if str(promo_check.get("status")) != "ok":
                reason = str(promo_check.get("reason", "promocode_validation_failed"))
                await whitelist_service.record_billing_event(
                    provider=STARS_PROVIDER,
                    event_type="stars_precheckout_rejected",
                    user_id=query.from_user.id,
                    currency=query.currency,
                    stars_amount=int(query.total_amount or 0),
                    reason=f"promo_{reason}",
                    meta={
                        "stage": "pre_checkout",
                        "promo_code": payload_data.get("promo_code"),
                        "promo_reservation_id": payload_data.get("promo_reservation_id"),
                        **validation_meta,
                    },
                )
                await query.answer(ok=False, error_message=_t(lang, "payment_check_failed"))
                return
        checkout_payment_id = str(payload_data.get("checkout_payment_id") or "").strip()
        if checkout_payment_id:
            checkout_check = await whitelist_service.validate_stars_checkout_intent(
                payment_id=checkout_payment_id,
                user_id=int(query.from_user.id),
                credits=int(payload_data.get("credits") or 0),
                stars_amount=int(payload_data.get("stars") or 0),
            )
            if str(checkout_check.get("status")) != "ok":
                reason = str(checkout_check.get("status") or "checkout_validation_failed")
                await whitelist_service.record_billing_event(
                    provider=STARS_PROVIDER,
                    event_type="stars_precheckout_rejected",
                    user_id=query.from_user.id,
                    currency=query.currency,
                    stars_amount=int(query.total_amount or 0),
                    reason=reason,
                    meta={
                        "stage": "pre_checkout",
                        "checkout_payment_id": checkout_payment_id,
                        **validation_meta,
                    },
                )
                await query.answer(ok=False, error_message=_t(lang, "payment_check_failed"))
                return
        logger.info(
            "pre_checkout_ok user_id=%s credits=%s stars=%s payload_version=%s",
            query.from_user.id,
            payload_data["credits"],
            payload_data["stars"],
            payload_data["v"],
        )
        await query.answer(ok=True)

    @router.message(F.successful_payment)
    async def handle_successful_payment(message: Message, state: FSMContext) -> None:
        payment = message.successful_payment
        if payment is None:
            return
        lang = await store.get_language(message.chat.id)
        payload_text = payment.invoice_payload or ""
        payload_data, parse_error = _parse_invoice_payload_detailed(payload_text)
        is_valid, validation_reason, validation_meta = _validate_stars_payment_payload(
            payload_data,
            expected_user_id=int(message.chat.id),
            currency=payment.currency or "",
            total_amount=int(payment.total_amount or 0),
        )
        if not is_valid:
            logger.warning(
                "payment_validation_failed chat_id=%s currency=%s amount=%s reason=%s payload=%s",
                message.chat.id,
                payment.currency,
                payment.total_amount,
                validation_reason or parse_error or "validation_failed",
                payload_data,
            )
            await whitelist_service.record_billing_event(
                provider=STARS_PROVIDER,
                event_type="stars_payment_invalid",
                user_id=message.chat.id,
                currency=payment.currency,
                stars_amount=int(payment.total_amount or 0),
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
                reason=str(validation_reason or parse_error or "post_payment_validation_failed"),
                meta={
                    "stage": "successful_payment",
                    "parse_error": parse_error,
                    **validation_meta,
                    **_payload_fingerprint(payload_text),
                },
            )
            checkout_payment_id = (
                str((payload_data or {}).get("checkout_payment_id") or "").strip()
                if isinstance(payload_data, dict)
                else ""
            )
            if checkout_payment_id:
                await whitelist_service.mark_stars_payment_failed(
                    payment_id=checkout_payment_id,
                    reason="post_payment_validation_failed",
                    error_meta={
                        "validation_reason": str(validation_reason or parse_error or "validation_failed"),
                    },
                )
            await state.set_state(UserStates.menu)
            await _show_payment_result_screen(
                message,
                state,
                lang,
                text=_t(lang, "payment_invalid"),
                success=False,
            )
            return
        if bool(payload_data.get("has_promocode")):
            promo_check = await whitelist_service.validate_promocode_reservation(
                reservation_id=str(payload_data.get("promo_reservation_id") or ""),
                user_id=int(message.chat.id),
                promo_code_id=str(payload_data.get("promo_code_id") or ""),
                credits=int(payload_data.get("credits") or 0),
                stars_original=int(payload_data.get("stars_original") or 0),
                discount_stars=int(payload_data.get("discount_stars") or 0),
                stars_final=int(payload_data.get("stars") or 0),
            )
            if str(promo_check.get("status")) != "ok":
                await whitelist_service.record_billing_event(
                    provider=STARS_PROVIDER,
                    event_type="stars_payment_invalid",
                    user_id=message.chat.id,
                    currency=payment.currency,
                    stars_amount=int(payment.total_amount or 0),
                    telegram_payment_charge_id=payment.telegram_payment_charge_id,
                    reason=f"promo_{promo_check.get('reason', 'validation_failed')}",
                    meta={
                        "stage": "successful_payment",
                        **validation_meta,
                        **_payload_fingerprint(payload_text),
                    },
                )
                checkout_payment_id = str(payload_data.get("checkout_payment_id") or "").strip()
                if checkout_payment_id:
                    await whitelist_service.mark_stars_payment_failed(
                        payment_id=checkout_payment_id,
                        reason="promocode_validation_failed",
                        error_meta={"reason": str(promo_check.get("reason", "validation_failed"))},
                    )
                await store.set_promo_reservation_id(message.chat.id, None)
                await state.set_state(UserStates.menu)
                await _show_payment_result_screen(
                    message,
                    state,
                    lang,
                    text=_t(lang, "payment_invalid"),
                    success=False,
                )
                return

        payment_id = _payment_idempotency_key(
            invoice_payload=payment.invoice_payload or "",
            currency=payment.currency or "",
            total_amount=int(payment.total_amount or 0),
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
            provider_payment_charge_id=payment.provider_payment_charge_id,
        )
        result = await whitelist_service.apply_stars_payment(
            user_id=message.chat.id,
            credits=int(payload_data["credits"]),
            stars_amount=int(payload_data["stars"]),
            provider_payment_id=payment_id,
            telegram_payment_charge_id=payment.telegram_payment_charge_id,
            promo_reservation_id=(
                str(payload_data.get("promo_reservation_id") or "")
                if payload_data.get("has_promocode")
                else None
            ),
            promo_code_id=(
                str(payload_data.get("promo_code_id") or "")
                if payload_data.get("has_promocode")
                else None
            ),
            stars_original=(
                int(payload_data.get("stars_original") or 0)
                if payload_data.get("has_promocode")
                else None
            ),
            discount_stars=(
                int(payload_data.get("discount_stars") or 0)
                if payload_data.get("has_promocode")
                else None
            ),
            checkout_payment_id=(
                str(payload_data.get("checkout_payment_id") or "")
                if payload_data.get("checkout_payment_id")
                else None
            ),
        )
        status = str(result.get("status", "invalid"))
        if status == "duplicate":
            if payload_data.get("has_promocode"):
                await whitelist_service.release_promocode_reservation(
                    str(payload_data.get("promo_reservation_id") or ""),
                    user_id=message.chat.id,
                    reason="duplicate_payment",
                )
            await store.set_promo_reservation_id(message.chat.id, None)
            await state.set_state(UserStates.menu)
            await _show_payment_result_screen(
                message,
                state,
                lang,
                text=_t(lang, "payment_duplicate"),
                success=True,
            )
            return
        if status != "applied":
            if payload_data.get("has_promocode"):
                await whitelist_service.release_promocode_reservation(
                    str(payload_data.get("promo_reservation_id") or ""),
                    user_id=message.chat.id,
                    reason="payment_apply_failed",
                )
            await store.set_promo_reservation_id(message.chat.id, None)
            await whitelist_service.record_billing_event(
                provider=STARS_PROVIDER,
                event_type="stars_payment_invalid",
                user_id=message.chat.id,
                provider_payment_id=payment_id,
                telegram_payment_charge_id=payment.telegram_payment_charge_id,
                currency=payment.currency,
                stars_amount=int(payment.total_amount or 0),
                credits_amount=int(payload_data["credits"]),
                reason=f"apply_result_{status}",
                meta=result if isinstance(result, dict) else None,
            )
            checkout_payment_id = str(payload_data.get("checkout_payment_id") or "").strip()
            if checkout_payment_id:
                await whitelist_service.mark_stars_payment_failed(
                    payment_id=checkout_payment_id,
                    reason=f"apply_result_{status}",
                    error_meta=result if isinstance(result, dict) else None,
                )
            await state.set_state(UserStates.menu)
            await _show_payment_result_screen(
                message,
                state,
                lang,
                text=_t(lang, "payment_invalid"),
                success=False,
            )
            return

        remaining_text = _format_remaining_credits(
            lang,
            result.get("remaining_requests"),
        )
        await state.set_state(UserStates.menu)
        await store.set_promo_reservation_id(message.chat.id, None)
        await _show_payment_result_screen(
            message,
            state,
            lang,
            text=_t(
                lang,
                "payment_success",
                credits=int(payload_data["credits"]),
                remaining=remaining_text,
            ),
            success=True,
        )

    @router.message(UserStates.photo, F.photo)
    async def handle_photo(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        payload = await store.get_payload(message.chat.id)
        mode = _resolve_mode(payload.mode)
        state_data = await state.get_data()
        capture_style_reference = bool(state_data.get(STYLE_REF_CAPTURE_KEY))
        buffer = BytesIO()
        try:
            await message.bot.download(message.photo[-1], destination=buffer)
            buffer.seek(0)
        except Exception:
            logger.exception(
                "Failed to download photo for chat_id=%s", message.chat.id
            )
            await message.answer(_t(lang, "photo_download_error"))
            return

        if capture_style_reference:
            try:
                await store.set_style_reference(message.chat.id, buffer.getvalue())
            except Exception:
                logger.exception(
                    "Failed to store style reference for chat_id=%s", message.chat.id
                )
                await message.answer(_t(lang, "photo_store_error"))
                return
            await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
            await state.set_state(UserStates.photo)
            await message.answer(_t(lang, "style_ref_received"))
            if mode == MODE_FURNITURE_SEARCH:
                await _show_furniture_compose_screen(message, state, lang)
                return
            await _show_render_compose_screen(message, state, lang)
            return

        try:
            await on_photo(message.chat.id, buffer.getvalue(), store)
        except Exception:
            logger.exception("Failed to store photo for chat_id=%s", message.chat.id)
            await message.answer(_t(lang, "photo_store_error"))
            return

        caption_text = (message.caption or "").strip()
        if caption_text:
            await on_text(message.chat.id, caption_text, store)

        if mode == MODE_FURNITURE_SEARCH:
            await on_text(message.chat.id, "", store)
            await state.set_state(UserStates.photo)
            await _show_furniture_compose_screen(message, state, lang)
            return

        await state.set_state(UserStates.text)
        if mode == MODE_RENDER_ONLY:
            await _show_render_compose_screen(message, state, lang)
            return

        await _show_render_compose_screen(message, state, lang)

    @router.message(UserStates.photo, F.text)
    async def handle_photo_text(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        state_data = await state.get_data()
        if bool(state_data.get(STYLE_REF_CAPTURE_KEY)):
            await message.answer(_t(lang, "style_ref_need_photo"))
            return
        payload = await store.get_payload(message.chat.id)
        mode = _resolve_mode(payload.mode)
        await on_text(message.chat.id, message.text or "", store)
        if mode == MODE_RENDER_ONLY:
            await state.set_state(UserStates.text)
            await _show_render_compose_screen(message, state, lang)
            return
        if mode == MODE_FURNITURE_SEARCH:
            await on_text(message.chat.id, "", store)
            await message.answer(_t(lang, "ask_photo_furniture"))
            return
        await state.set_state(UserStates.text)
        await _show_render_compose_screen(message, state, lang)

    @router.message(UserStates.text, F.text.casefold() == _t(LANG_RU, "start_process").casefold())
    @router.message(UserStates.text, F.text.casefold() == _t(LANG_EN, "start_process").casefold())
    async def handle_process(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        payload = await store.get_payload(message.chat.id)
        await start_processing(message, state, payload)

    @router.message(UserStates.text, F.text.casefold() == _t(LANG_RU, "no_wishes").casefold())
    @router.message(UserStates.text, F.text.casefold() == _t(LANG_EN, "no_wishes").casefold())
    async def handle_no_wishes(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        payload_before = await store.get_payload(message.chat.id)
        mode = _resolve_mode(payload_before.mode)
        await on_text(message.chat.id, NO_WISHES_SENTINEL, store)
        payload = await store.get_payload(message.chat.id)
        if mode == MODE_RENDER_ONLY:
            await _show_render_compose_screen(message, state, lang)
            return
        await message.answer(
            _build_ready_card(lang, payload),
        )

    @router.message(F.text.casefold() == _t(LANG_RU, "retry_variant").casefold())
    @router.message(F.text.casefold() == _t(LANG_EN, "retry_variant").casefold())
    async def handle_retry_variant(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        payload = await store.get_payload(message.chat.id)
        mode = _resolve_mode(payload.mode)
        await store.clear_flow_payload(
            message.chat.id,
            clear_photo=(mode == MODE_FURNITURE_SEARCH),
            clear_text=(mode == MODE_FURNITURE_SEARCH),
            clear_job_id=True,
            clear_mode=False,
        )
        await store.set_mode(message.chat.id, mode)
        await state.set_state(UserStates.photo)
        if mode == MODE_FURNITURE_SEARCH:
            await _show_furniture_compose_screen(message, state, lang)
            return
        await _show_render_compose_screen_prefilled(
            message,
            state,
            lang,
            prefilled_hint_key="render_compose_retry_hint",
        )

    @router.message(UserStates.text, F.text)
    async def handle_text(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        state_data = await state.get_data()
        if bool(state_data.get(STYLE_REF_CAPTURE_KEY)):
            await message.answer(_t(lang, "style_ref_need_photo"))
            return
        payload_before = await store.get_payload(message.chat.id)
        mode = _resolve_mode(payload_before.mode)
        await on_text(message.chat.id, message.text, store)
        if mode == MODE_RENDER_ONLY:
            await _show_render_compose_screen(message, state, lang)
            return
        if mode == MODE_FURNITURE_SEARCH:
            await on_text(message.chat.id, "", store)
            await _show_furniture_compose_screen(message, state, lang)
            return
        await _show_render_compose_screen(message, state, lang)

    @router.message(UserStates.text, F.photo)
    async def handle_text_photo(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        payload = await store.get_payload(message.chat.id)
        mode = _resolve_mode(payload.mode)
        state_data = await state.get_data()
        capture_style_reference = bool(state_data.get(STYLE_REF_CAPTURE_KEY))
        buffer = BytesIO()
        try:
            await message.bot.download(message.photo[-1], destination=buffer)
            buffer.seek(0)
        except Exception:
            logger.exception(
                "Failed to download photo for chat_id=%s", message.chat.id
            )
            await message.answer(_t(lang, "photo_download_error"))
            return

        if capture_style_reference:
            try:
                await store.set_style_reference(message.chat.id, buffer.getvalue())
            except Exception:
                logger.exception(
                    "Failed to store style reference for chat_id=%s", message.chat.id
                )
                await message.answer(_t(lang, "photo_store_error"))
                return
            await state.update_data(**{STYLE_REF_CAPTURE_KEY: False})
            await state.set_state(UserStates.photo)
            await message.answer(_t(lang, "style_ref_received"))
            if mode == MODE_FURNITURE_SEARCH:
                await _show_furniture_compose_screen(message, state, lang)
                return
            await _show_render_compose_screen(message, state, lang)
            return

        try:
            await on_photo(message.chat.id, buffer.getvalue(), store)
        except Exception:
            logger.exception("Failed to store photo for chat_id=%s", message.chat.id)
            await message.answer(_t(lang, "photo_store_error"))
            return

        caption_text = (message.caption or "").strip()
        if caption_text:
            await on_text(message.chat.id, caption_text, store)

        if mode == MODE_FURNITURE_SEARCH:
            await on_text(message.chat.id, "", store)
            await state.set_state(UserStates.photo)
            await _show_furniture_compose_screen(message, state, lang)
            return

        if mode == MODE_RENDER_ONLY:
            await state.set_state(UserStates.text)
            await _show_render_compose_screen(message, state, lang)
            return

        await state.set_state(UserStates.text)
        await _show_render_compose_screen(message, state, lang)

    @router.message(UserStates.menu, F.text)
    async def handle_menu_text(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await _show_main_menu_screen(message, state, lang)

    @router.message(UserStates.settings, F.text)
    async def handle_settings_text(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await _show_settings_screen(message, state, lang)

    @router.message(UserStates.confirm_reset, F.text)
    async def handle_confirm_reset_text(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        await _show_reset_confirm_screen(message, state, lang)

    @router.message(UserStates.post_result, F.text)
    async def handle_post_result_text(message: Message, state: FSMContext) -> None:
        if not await ensure_fresh_flow(message, state):
            return
        lang = await store.get_language(message.chat.id)
        payload = await store.get_payload(message.chat.id)
        mode = _resolve_mode(payload.mode)
        await _show_post_result_screen(message, state, lang, _post_result_prompt(lang, mode), mode)

    return router
