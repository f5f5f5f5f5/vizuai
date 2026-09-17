"""Historical Telegram flow tests; target removed APIs, see docs/validation.md."""

import asyncio
import json
import time

import pytest

import services.telegram_bot as telegram_bot
from services.telegram_bot import FLOW_TIMEOUT_SECONDS_FULL, UserDataStore, build_router


class _FakeBot:
    def __init__(self) -> None:
        self.sent_messages = []
        self.sent_documents = []
        self.sent_photos = []
        self.sent_invoices = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append((chat_id, text))

    async def send_document(self, chat_id: int, document: bytes, filename: str | None = None) -> None:
        self.sent_documents.append((chat_id, document, filename))

    async def send_photo(self, chat_id: int, photo: bytes, caption: str | None = None) -> None:
        self.sent_photos.append((chat_id, photo, caption))

    async def send_invoice(
        self,
        chat_id: int,
        title: str,
        description: str,
        payload: str,
        currency: str,
        prices: list,
        **kwargs,
    ) -> None:
        self.sent_invoices.append(
            {
                "chat_id": chat_id,
                "title": title,
                "description": description,
                "payload": payload,
                "currency": currency,
                "prices": prices,
                "kwargs": kwargs,
            }
        )


class _FakeChat:
    def __init__(self, chat_id: int) -> None:
        self.id = chat_id


class _FakeUser:
    def __init__(self, username: str | None = None) -> None:
        self.username = username
        self.first_name = None
        self.last_name = None


class _FakeMessage:
    def __init__(self, chat_id: int, bot: _FakeBot, text: str | None = None) -> None:
        self.chat = _FakeChat(chat_id)
        self.from_user = _FakeUser("tester")
        self.bot = bot
        self.text = text

    async def answer(self, text: str, reply_markup=None, **kwargs) -> None:
        self.bot.sent_messages.append((self.chat.id, text))

    async def answer_document(self, document: bytes, filename: str | None = None) -> None:
        self.bot.sent_documents.append((self.chat.id, document, filename))


class _FakeState:
    def __init__(self) -> None:
        self.state = None
        self.data = {}

    async def set_state(self, state) -> None:
        self.state = state

    async def clear(self) -> None:
        self.state = None

    async def get_state(self):
        if hasattr(self.state, "state"):
            return self.state.state
        return self.state

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, **kwargs):
        self.data.update(kwargs)
        return dict(self.data)


class _FakeOrchestrator:
    def __init__(self, status: str = "done") -> None:
        self.started = []
        self.selected = []
        self._status = status

    async def start_job(
        self,
        chat_id: int,
        photo: bytes,
        text: str,
        style_reference: bytes | None = None,
        mode: str = "full",
        units_spent: int = 0,
    ) -> str:
        self.started.append((chat_id, photo, text, style_reference, mode, units_spent))
        return "job-1"

    async def poll_job(self, job_id: str):
        if self._status == "done":
            return "done", b"%PDF-1.4 test"
        return "failed", None


class _FakeRedis:
    def __init__(self) -> None:
        self._jobs = {}

    def get_daily_metrics(self):
        return {}

    def get_daily_costs(self):
        return {}

    def get_debug(self, job_id: str):
        return None

    def get_job(self, job_id: str):
        return self._jobs.get(job_id)


class _FakeWhitelist:
    def __init__(self, whitelisted: bool = True, reason: str = "ok") -> None:
        self._whitelisted = whitelisted
        self._reason = reason
        self.reserve_calls: list[tuple[int, int]] = []
        self.add_calls: list[tuple[int, int | None, int | None]] = []

    async def ensure_user(self, *args, **kwargs):
        class _User:
            usage_count = 2
            last_request_at = None

        return _User()

    async def get_whitelist_status(self, user_id: int) -> dict:
        return {"whitelisted": self._whitelisted, "reason": self._reason}

    async def record_request(self, user_id: int, count: int = 1):
        return None

    async def reserve_units(self, user_id: int, units: int) -> dict:
        self.reserve_calls.append((user_id, units))
        if self._whitelisted:
            return {"allowed": True, "reason": "ok", "remaining_requests": 100}
        return {"allowed": False, "reason": self._reason, "remaining_requests": 0}

    async def list_whitelisted_users(self):
        return []

    async def add_user_to_whitelist(self, user_id: int, days: int | None, requests: int | None):
        self.add_calls.append((user_id, days, requests))
        return None

    async def remove_user_from_whitelist(self, *args, **kwargs):
        return None

    async def reset_quota(self, *args, **kwargs):
        return None

    async def apply_stars_payment(
        self,
        user_id: int,
        credits: int,
        stars_amount: int,
        provider_payment_id: str,
        telegram_payment_charge_id: str | None = None,
        promo_reservation_id: str | None = None,
        promo_code_id: str | None = None,
        stars_original: int | None = None,
        discount_stars: int | None = None,
        checkout_payment_id: str | None = None,
    ) -> dict:
        return {"status": "applied", "remaining_requests": 100}

    async def create_stars_payment_intent(
        self,
        *,
        user_id: int,
        credits: int,
        stars_amount: int,
        promo_reservation_id: str | None = None,
        promo_code_id: str | None = None,
        stars_original: int | None = None,
        discount_stars: int | None = None,
    ) -> dict:
        return {"status": "ok", "payment_id": "33333333-3333-3333-3333-333333333333"}

    async def create_checkout_intent(
        self,
        *,
        provider: str,
        user_id: int,
        credits: int,
        amount,
        currency: str,
        promo_reservation_id: str | None = None,
        promo_code_id: str | None = None,
        amount_original=None,
        discount_amount=None,
    ) -> dict:
        return {"status": "ok", "payment_id": "33333333-3333-3333-3333-333333333333"}

    async def mark_stars_payment_invoice_sent(
        self,
        *,
        payment_id: str,
        invoice_meta: dict[str, object] | None = None,
    ) -> dict:
        return {"status": "ok"}

    async def mark_stars_payment_failed(
        self,
        *,
        payment_id: str,
        reason: str,
        error_meta: dict[str, object] | None = None,
    ) -> dict:
        return {"status": "ok"}

    async def validate_stars_checkout_intent(
        self,
        *,
        payment_id: str,
        user_id: int,
        credits: int,
        stars_amount: int,
    ) -> dict:
        return {"status": "ok"}

    async def list_webhook_dead_letters(self, *, provider: str, limit: int = 20) -> dict:
        return {"status": "ok", "provider": provider, "items": []}

    async def get_webhook_event(self, event_id: str) -> dict:
        return {"status": "not_found"}

    async def finalize_webhook_event(self, *, event_id: str, status: str, error: str | None = None) -> dict:
        return {"status": "ok"}

    async def check_promocode(self, user_id: int, code: str) -> dict:
        return {"status": "ok", "code_id": "11111111-1111-1111-1111-111111111111", "code": code}

    async def reserve_promocode(
        self,
        *,
        user_id: int,
        code: str,
        credits: int,
        stars_original: int,
        ttl_seconds: int = 3600,
        previous_reservation_id: str | None = None,
        provider: str = "telegram_stars",
        currency: str = "XTR",
    ) -> dict:
        return {
            "status": "ok",
            "reservation_id": "22222222-2222-2222-2222-222222222222",
            "code_id": "11111111-1111-1111-1111-111111111111",
            "code": code,
            "stars_original": stars_original,
            "discount_stars": 10,
            "stars_final": max(stars_original - 10, 1),
        }

    async def release_promocode_reservation(
        self,
        reservation_id: str,
        *,
        user_id: int,
        reason: str,
        provider: str = "telegram_stars",
        currency: str = "XTR",
    ) -> dict:
        return {"status": "released"}

    async def validate_promocode_reservation(
        self,
        *,
        reservation_id: str,
        user_id: int,
        promo_code_id: str,
        credits: int,
        stars_original: int,
        discount_stars: int,
        stars_final: int,
    ) -> dict:
        return {"status": "ok"}

    async def lookup_stars_payment(self, query: str) -> dict:
        return {"status": "not_found"}

    async def start_stars_refund(self, payment_id: str) -> dict:
        return {"status": "not_found"}

    async def finalize_stars_refund(
        self,
        payment_id: str,
        *,
        success: bool,
        reason: str | None = None,
        telegram_error: str | None = None,
    ) -> dict:
        return {"status": "not_found"}

    async def record_billing_event(self, *args, **kwargs):
        return None


def _get_handler(router, name: str):
    for handler in router.message.handlers:
        if handler.callback.__name__ == name:
            return handler.callback
    raise AssertionError(f"Handler not found: {name}")


@pytest.mark.asyncio
async def test_handle_process_denied_by_whitelist():
    bot = _FakeBot()
    message = _FakeMessage(1, bot, text="Обработать")
    state = _FakeState()

    store = UserDataStore(redis_url=None)
    await store.set_photo(1, b"photo")
    await store.set_text(1, "text")

    router = build_router(
        orchestrator=_FakeOrchestrator(),
        store=store,
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=_FakeWhitelist(whitelisted=False, reason="no_subscription"),
    )
    handler = _get_handler(router, "handle_process")
    await handler(message, state)

    assert any("Сейчас запуск недоступен" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_handle_process_success_flow():
    bot = _FakeBot()
    message = _FakeMessage(3, bot, text="Обработать")
    state = _FakeState()

    store = UserDataStore(redis_url=None)
    await store.set_photo(3, b"photo")
    await store.set_text(3, "text")

    whitelist = _FakeWhitelist(whitelisted=True)
    router = build_router(
        orchestrator=_FakeOrchestrator(status="done"),
        store=store,
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=whitelist,
    )
    handler = _get_handler(router, "handle_process")
    await handler(message, state)

    assert whitelist.reserve_calls == [(3, 10)]
    assert any("Обработка запущена, верну результат через несколько минут" in text for _, text in bot.sent_messages)

    for _ in range(10):
        if bot.sent_documents:
            break
        await asyncio.sleep(0.01)

    assert len(bot.sent_documents) == 1


@pytest.mark.asyncio
async def test_handle_process_passes_style_reference_and_notifies_user():
    bot = _FakeBot()
    message = _FakeMessage(33, bot, text="Обработать")
    state = _FakeState()

    store = UserDataStore(redis_url=None)
    await store.set_mode(33, "render_only")
    await store.set_photo(33, b"room-photo")
    await store.set_text(33, "make it warm")
    await store.set_style_reference(33, b"style-photo")

    orchestrator = _FakeOrchestrator(status="done")
    whitelist = _FakeWhitelist(whitelisted=True)
    router = build_router(
        orchestrator=orchestrator,
        store=store,
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=whitelist,
    )
    handler = _get_handler(router, "handle_process")
    await handler(message, state)

    assert orchestrator.started
    started = orchestrator.started[0]
    assert started[0] == 33
    assert started[1] == b"room-photo"
    assert started[2] == "make it warm"
    assert started[3] == b"style-photo"
    assert started[4] == "render_only"
    assert any("Использую стиль с референса ✅" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_retry_variant_returns_to_prefilled_render_only_flow():
    bot = _FakeBot()
    message = _FakeMessage(30, bot, text="🔁 Ещё вариант")
    state = _FakeState()
    store = UserDataStore(redis_url=None)
    await store.set_mode(30, "render_only")
    await store.set_photo(30, b"photo")
    await store.set_text(30, "text")
    await store.add_active_job(30, "job-in-flight")

    orchestrator = _FakeOrchestrator(status="done")
    whitelist = _FakeWhitelist(whitelisted=True)
    router = build_router(
        orchestrator=orchestrator,
        store=store,
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=whitelist,
    )
    handler = _get_handler(router, "handle_retry_variant")
    await handler(message, state)

    payload = await store.get_payload(30)
    assert whitelist.reserve_calls == []
    assert orchestrator.started == []
    assert payload.mode == "render_only"
    assert payload.job_id is None
    assert payload.photo == b"photo"
    assert payload.text == "text"
    assert payload.active_jobs == ("job-in-flight",)
    assert any("Подгрузил прошлое фото и описание" in text for _, text in bot.sent_messages)
    assert any("Пришли мне фото комнаты и напиши, что хочешь сделать" in text for _, text in bot.sent_messages)
    assert any("Стоимость: 10🎟️" in text for _, text in bot.sent_messages)
    assert any("<b>🏠 Дизайн комнаты</b>" in text for _, text in bot.sent_messages)


def test_render_compose_keyboard_style_reference_states():
    payload = telegram_bot.UserPayload(mode="render_only")
    keyboard = telegram_bot._render_compose_inline_keyboard("ru", payload, 1, int(time.time()))
    texts = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "📷 Фото комнаты ❌" in texts
    assert "📝 Описание ❌" in texts
    assert "🎨 Стиль по фото" in texts
    assert "▶️ Сгенерировать" not in texts
    assert "🗑️ Убрать стиль" not in texts

    payload.photo = b"photo"
    payload.text = "new design"
    payload.style_reference = b"style"
    keyboard2 = telegram_bot._render_compose_inline_keyboard("ru", payload, 2, int(time.time()))
    texts2 = [button.text for row in keyboard2.inline_keyboard for button in row]
    assert "📷 Фото комнаты ✅" in texts2
    assert "📝 Описание ✅" in texts2
    assert "🎨 Стиль по фото ✅" in texts2
    assert "▶️ Сгенерировать" in texts2
    assert "🗑️ Убрать стиль" in texts2


def test_validate_stars_payload_rejects_unsupported_version():
    payload = json.dumps(
        {
            "v": telegram_bot.INVOICE_VERSION + 1,
            "kind": telegram_bot.INVOICE_KIND_CREDITS,
            "user_id": 100,
            "credits": 10,
            "stars": telegram_bot.PACKAGE_CATALOG_STARS[10],
        },
        ensure_ascii=False,
    )
    parsed, parse_error = telegram_bot._parse_invoice_payload_detailed(payload)
    assert parse_error is None
    ok, reason, meta = telegram_bot._validate_stars_payment_payload(
        parsed,
        expected_user_id=100,
        currency=telegram_bot.STARS_CURRENCY,
        total_amount=telegram_bot.PACKAGE_CATALOG_STARS[10],
    )
    assert ok is False
    assert reason == "unsupported_payload_version"
    assert meta["payload_version"] == telegram_bot.INVOICE_VERSION + 1


def test_validate_stars_payload_rejects_total_amount_mismatch():
    payload = telegram_bot._build_invoice_payload(
        user_id=100,
        credits=10,
        stars=telegram_bot.PACKAGE_CATALOG_STARS[10],
        checkout_payment_id="33333333-3333-3333-3333-333333333333",
    )
    parsed, parse_error = telegram_bot._parse_invoice_payload_detailed(payload)
    assert parse_error is None
    ok, reason, meta = telegram_bot._validate_stars_payment_payload(
        parsed,
        expected_user_id=100,
        currency=telegram_bot.STARS_CURRENCY,
        total_amount=telegram_bot.PACKAGE_CATALOG_STARS[10] + 1,
    )
    assert ok is False
    assert reason == "total_amount_mismatch"
    assert meta["payload_stars"] == telegram_bot.PACKAGE_CATALOG_STARS[10]


def test_validate_stars_payload_with_promocode_ok():
    payload = json.dumps(
        {
            "v": 3,
            "kind": telegram_bot.INVOICE_KIND_CREDITS,
            "user_id": 100,
            "credits": 10,
            "stars": 159,
            "checkout_payment_id": "33333333-3333-3333-3333-333333333333",
            "promo_reservation_id": "22222222-2222-2222-2222-222222222222",
            "promo_code_id": "11111111-1111-1111-1111-111111111111",
            "promo_code": "SALE20",
            "stars_original": 199,
            "discount_stars": 40,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    parsed, parse_error = telegram_bot._parse_invoice_payload_detailed(payload)
    assert parse_error is None
    ok, reason, meta = telegram_bot._validate_stars_payment_payload(
        parsed,
        expected_user_id=100,
        currency=telegram_bot.STARS_CURRENCY,
        total_amount=159,
    )
    assert ok is True
    assert reason is None
    assert meta["has_promocode"] is True
    assert meta["discount_stars"] == 40


def test_validate_stars_payload_with_promocode_rejects_price_mismatch():
    payload = json.dumps(
        {
            "v": 3,
            "kind": telegram_bot.INVOICE_KIND_CREDITS,
            "user_id": 100,
            "credits": 10,
            "stars": 170,
            "checkout_payment_id": "33333333-3333-3333-3333-333333333333",
            "promo_reservation_id": "22222222-2222-2222-2222-222222222222",
            "promo_code_id": "11111111-1111-1111-1111-111111111111",
            "promo_code": "SALE20",
            "stars_original": 199,
            "discount_stars": 40,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    parsed, parse_error = telegram_bot._parse_invoice_payload_detailed(payload)
    assert parse_error is None
    ok, reason, _meta = telegram_bot._validate_stars_payment_payload(
        parsed,
        expected_user_id=100,
        currency=telegram_bot.STARS_CURRENCY,
        total_amount=170,
    )
    assert ok is False
    assert reason == "promocode_price_mismatch"


def test_build_invoice_payload_compact_v4_fits_telegram_limit():
    payload = telegram_bot._build_invoice_payload(
        user_id=421936302,
        credits=10,
        stars=199,
        checkout_payment_id="33333333-3333-3333-3333-333333333333",
    )
    assert len(payload) <= 128
    parsed, parse_error = telegram_bot._parse_invoice_payload_detailed(payload)
    assert parse_error is None
    assert parsed is not None
    assert parsed["v"] == telegram_bot.INVOICE_VERSION
    assert parsed["kind"] == telegram_bot.INVOICE_KIND_CREDITS
    assert parsed["checkout_payment_id"] == "33333333-3333-3333-3333-333333333333"


def test_normalize_refund_reason_supports_known_and_custom_values():
    assert telegram_bot._normalize_refund_reason("service_failure_no_result") == "service_failure_no_result"
    assert telegram_bot._normalize_refund_reason("") == "support_manual_unspecified"
    assert telegram_bot._normalize_refund_reason("My Own Reason") == "custom:my_own_reason"


def test_render_compose_card_style_reference_copy_is_user_friendly():
    payload = telegram_bot.UserPayload(mode="render_only")
    card = telegram_bot._render_compose_card("ru", payload)
    assert "Стиль по фото не обязателен" in card
    assert "❌" not in card

    payload.style_reference = b"style"
    card2 = telegram_bot._render_compose_card("ru", payload)
    assert "Стиль по фото добавлен ✅" in card2


def test_payment_success_keyboard_has_expected_cta_buttons():
    keyboard = telegram_bot._payment_success_inline_keyboard("ru", 1, int(time.time()))
    texts = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "🎨 Сделать дизайн" in texts
    assert "⭐ Баланс" in texts
    assert "🏠 Меню" in texts


def test_payment_issue_keyboard_has_balance_and_menu_buttons():
    keyboard = telegram_bot._payment_issue_inline_keyboard("ru", 1, int(time.time()))
    texts = [button.text for row in keyboard.inline_keyboard for button in row]
    assert "⭐ Баланс" in texts
    assert "🏠 Меню" in texts


@pytest.mark.asyncio
async def test_menu_packages_shows_balance_and_topup_methods():
    bot = _FakeBot()
    message = _FakeMessage(10, bot, text="⭐ Баланс")
    state = _FakeState()

    router = build_router(
        orchestrator=_FakeOrchestrator(),
        store=UserDataStore(redis_url=None),
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=_FakeWhitelist(whitelisted=True),
    )
    handler = _get_handler(router, "menu_packages")
    await handler(message, state)

    assert any("Баланс:" in text for _, text in bot.sent_messages)
    assert any("Можешь выбрать удобный способ пополнения ниже" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_packages_select_shows_stub_message():
    bot = _FakeBot()
    message = _FakeMessage(11, bot, text="10🎟️ • 199⭐")
    state = _FakeState()

    router = build_router(
        orchestrator=_FakeOrchestrator(),
        store=UserDataStore(redis_url=None),
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=_FakeWhitelist(whitelisted=True),
    )
    handler = _get_handler(router, "packages_select")
    await handler(message, state)

    assert len(bot.sent_invoices) == 1
    assert bot.sent_invoices[0]["currency"] == "XTR"
    assert any("Пакет: 10🎟️ за 199⭐" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_photo_state_accepts_text_and_requests_photo_next():
    bot = _FakeBot()
    message = _FakeMessage(21, bot, text="Сделай светлый интерьер")
    state = _FakeState()
    store = UserDataStore(redis_url=None)
    await store.set_mode(21, "render_only")

    router = build_router(
        orchestrator=_FakeOrchestrator(),
        store=store,
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=_FakeWhitelist(whitelisted=True),
    )
    handler = _get_handler(router, "handle_photo_text")
    await handler(message, state)

    payload = await store.get_payload(21)
    assert payload.text == "Сделай светлый интерьер"
    assert any("Пришли мне фото комнаты и напиши, что хочешь сделать" in text for _, text in bot.sent_messages)
    assert any("Стоимость: 10🎟️" in text for _, text in bot.sent_messages)
    assert any("<b>🏠 Дизайн комнаты</b>" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_new_photo_is_allowed_while_active_job_processing():
    bot = _FakeBot()
    message = _FakeMessage(22, bot, text="📷 Изменить фото")
    state = _FakeState()
    store = UserDataStore(redis_url=None)
    await store.set_mode(22, "render_only")
    await store.set_photo(22, b"photo-old")
    await store.set_text(22, "old text")
    await store.set_job_id(22, "job-active")
    await store.add_active_job(22, "job-active")

    router = build_router(
        orchestrator=_FakeOrchestrator(),
        store=store,
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=_FakeWhitelist(whitelisted=True),
    )
    handler = _get_handler(router, "action_new_photo")
    await handler(message, state)

    payload = await store.get_payload(22)
    assert payload.job_id == "job-active"
    assert payload.photo is None
    assert payload.text == "old text"
    assert payload.mode == "render_only"
    assert payload.active_jobs == ("job-active",)
    assert any(
        "Отправь фото комнаты, которую хочешь изменить" in text
        for _, text in bot.sent_messages
    )


@pytest.mark.asyncio
async def test_mode_select_clears_stale_text_and_photo_before_new_flow():
    bot = _FakeBot()
    message = _FakeMessage(31, bot, text="🏠 Дизайн комнаты • 10🎟️")
    state = _FakeState()
    store = UserDataStore(redis_url=None)
    await store.set_mode(31, "render_only")
    await store.set_photo(31, b"stale-photo")
    await store.set_text(31, "stale text")
    await store.set_job_id(31, "job-stale")
    await store.add_active_job(31, "job-stale")

    router = build_router(
        orchestrator=_FakeOrchestrator(),
        store=store,
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=_FakeWhitelist(whitelisted=True),
    )
    handler = _get_handler(router, "mode_select")
    await handler(message, state)

    payload = await store.get_payload(31)
    assert payload.mode == "render_only"
    assert payload.photo is None
    assert payload.text is None
    assert payload.job_id is None
    assert payload.active_jobs == ("job-stale",)
    assert any("Пришли мне фото комнаты и напиши, что хочешь сделать" in text for _, text in bot.sent_messages)
    assert any("Стоимость: 10🎟️" in text for _, text in bot.sent_messages)
    assert any("<b>🏠 Дизайн комнаты</b>" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_start_shows_help_in_ru():
    bot = _FakeBot()
    message = _FakeMessage(12, bot, text="/start")
    state = _FakeState()

    router = build_router(
        orchestrator=_FakeOrchestrator(),
        store=UserDataStore(redis_url=None),
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=_FakeWhitelist(whitelisted=True),
    )
    handler = _get_handler(router, "cmd_start")
    await handler(message, state)

    assert any("Я делаю редизайн интерьера по фото и ищу мебель на маркетплейсах" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_paysupport_contains_contact_and_response_time():
    bot = _FakeBot()

    router = build_router(
        orchestrator=_FakeOrchestrator(),
        store=UserDataStore(redis_url=None),
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=_FakeWhitelist(whitelisted=True),
    )
    handler = _get_handler(router, "cmd_paysupport")
    await handler(_FakeMessage(121, bot, text="/paysupport"))

    assert any("t.me/vizuai_app?direct" in text for _, text in bot.sent_messages)
    assert any("Время ответа" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_choose_english_affects_help_text():
    bot = _FakeBot()
    state = _FakeState()
    store = UserDataStore(redis_url=None)

    router = build_router(
        orchestrator=_FakeOrchestrator(),
        store=store,
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=_FakeWhitelist(whitelisted=True),
    )

    choose_handler = _get_handler(router, "choose_language")
    await choose_handler(_FakeMessage(13, bot, text="English"), state)
    assert any("Language updated" in text for _, text in bot.sent_messages)

    bot.sent_messages.clear()
    help_handler = _get_handler(router, "cmd_help")
    await help_handler(_FakeMessage(13, bot, text="/help"), state)
    assert any("<b>Help</b>" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_text_reset_requires_confirmation_then_clears_flow_payload():
    bot = _FakeBot()
    message = _FakeMessage(14, bot, text="/reset")
    state = _FakeState()
    store = UserDataStore(redis_url=None)
    await store.set_photo(14, b"photo")
    await store.set_text(14, "text")
    await store.set_job_id(14, "job-legacy")

    router = build_router(
        orchestrator=_FakeOrchestrator(),
        store=store,
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=_FakeWhitelist(whitelisted=True),
    )
    handler = _get_handler(router, "cmd_reset")
    await handler(message, state)

    payload_before = await store.get_payload(14)
    assert payload_before.photo == b"photo"
    assert payload_before.text == "text"
    assert payload_before.job_id == "job-legacy"
    assert any("Точно сбросить текущий сценарий?" in text for _, text in bot.sent_messages)

    confirm_handler = _get_handler(router, "settings_reset_confirm_yes")
    await confirm_handler(
        _FakeMessage(14, bot, text="✅ Да, сбросить"),
        state,
    )

    payload = await store.get_payload(14)
    assert payload.photo is None
    assert payload.text is None
    assert payload.job_id is None
    assert any("Сбросил текущий сценарий" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_handle_process_timeout_resets_flow_and_skips_start():
    bot = _FakeBot()
    message = _FakeMessage(15, bot, text="Обработать")
    state = _FakeState()
    store = UserDataStore(redis_url=None)
    await store.set_photo(15, b"photo")
    await store.set_text(15, "text")
    await store.set_mode(15, "full")
    stale_payload = await store.get_payload(15)
    stale_payload.last_activity_ts = time.time() - FLOW_TIMEOUT_SECONDS_FULL - 5
    store._memory[15] = stale_payload

    orchestrator = _FakeOrchestrator(status="done")
    router = build_router(
        orchestrator=orchestrator,
        store=store,
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=_FakeWhitelist(whitelisted=True),
    )
    handler = _get_handler(router, "handle_process")
    await handler(message, state)

    assert orchestrator.started == []
    assert any("длинная пауза" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_admin_whitelist_add_uses_new_credits_format():
    bot = _FakeBot()
    message = _FakeMessage(90, bot, text="/whitelist_add 421936302 11")
    state = _FakeState()
    whitelist = _FakeWhitelist(whitelisted=True)

    router = build_router(
        orchestrator=_FakeOrchestrator(),
        store=UserDataStore(redis_url=None),
        redis_client=_FakeRedis(),
        admin_ids={90},
        whitelist_service=whitelist,
    )
    handler = _get_handler(router, "cmd_whitelist_add")
    await handler(message)

    assert whitelist.add_calls == [(421936302, None, 11)]
    assert any("выдано 11 кредитов" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_admin_whitelist_add_keeps_legacy_format_compatible():
    bot = _FakeBot()
    message = _FakeMessage(91, bot, text="/whitelist_add 421936302 0 11")
    whitelist = _FakeWhitelist(whitelisted=True)

    router = build_router(
        orchestrator=_FakeOrchestrator(),
        store=UserDataStore(redis_url=None),
        redis_client=_FakeRedis(),
        admin_ids={91},
        whitelist_service=whitelist,
    )
    handler = _get_handler(router, "cmd_whitelist_add")
    await handler(message)

    assert whitelist.add_calls == [(421936302, None, 11)]
    assert any("legacy-формат" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_help_after_stale_menu_payload_cleans_silently():
    bot = _FakeBot()
    message = _FakeMessage(16, bot, text="❓ Помощь")
    state = _FakeState()
    await state.set_state("UserStates:menu")
    store = UserDataStore(redis_url=None)
    await store.set_photo(16, b"photo")
    await store.set_text(16, "text")
    payload = await store.get_payload(16)
    payload.last_activity_ts = time.time() - FLOW_TIMEOUT_SECONDS_FULL - 5
    store._memory[16] = payload

    router = build_router(
        orchestrator=_FakeOrchestrator(status="done"),
        store=store,
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=_FakeWhitelist(whitelisted=True),
    )
    handler = _get_handler(router, "menu_help")
    await handler(message, state)

    assert not any("длинная пауза" in text for _, text in bot.sent_messages)
    assert any("<b>Помощь</b>" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_menu_language_shows_selector_in_current_language():
    bot = _FakeBot()
    state = _FakeState()
    store = UserDataStore(redis_url=None)
    await store.set_language(14, "en")

    router = build_router(
        orchestrator=_FakeOrchestrator(),
        store=store,
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=_FakeWhitelist(whitelisted=True),
    )

    handler = _get_handler(router, "menu_language")
    await handler(_FakeMessage(14, bot, text="Language"), state)

    assert any("Choose interface language" in text for _, text in bot.sent_messages)


@pytest.mark.asyncio
async def test_invalid_language_choice_shows_hint():
    bot = _FakeBot()
    store = UserDataStore(redis_url=None)
    await store.set_language(15, "en")

    router = build_router(
        orchestrator=_FakeOrchestrator(),
        store=store,
        redis_client=_FakeRedis(),
        admin_ids=set(),
        whitelist_service=_FakeWhitelist(whitelisted=True),
    )

    handler = _get_handler(router, "choose_language_unknown")
    await handler(_FakeMessage(15, bot, text="Deutsch"))

    assert any("Please choose a language" in text for _, text in bot.sent_messages)
