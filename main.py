"""Bot entry point."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiohttp import web

from config import Settings
from app_services.billing.checkout_service import CheckoutService
from app_services.jobs.service import JobsService
from pipeline.orchestrator import OrchestratorConfig, PipelineOrchestrator
from services.cloud_tasks import CloudTasksQueue
from services.redis_client import RuntimeStateClient, build_runtime_state_client
from services.searchapi import SearchApiService
from services.storage import S3Storage
from services.tbank_acquiring import TBankAcquiringService
from services.telegram_bot import UserDataStore, build_main_menu_screen, build_router
from services.vision import GoogleVisionService
from services.whitelist_service import WhitelistService
from utils.logging_setup import configure_logging


@dataclass
class BotRuntime:
    bot: Bot
    dispatcher: Dispatcher
    user_store: UserDataStore


@dataclass
class Runtime:
    session: aiohttp.ClientSession
    orchestrator: PipelineOrchestrator
    bot_runtime: BotRuntime | None = None


def _webhook_idempotency_key(provider: str, payload: dict[str, object]) -> str:
    order_id = str(payload.get("OrderId") or "").strip()
    payment_id = str(payload.get("PaymentId") or "").strip()
    status = str(payload.get("Status") or "").strip().upper()
    success = str(payload.get("Success") or "").strip().lower()
    amount = str(payload.get("Amount") or "").strip()
    basis = "|".join([provider.strip().lower(), order_id, payment_id, status, success, amount])
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


def _setup_logging(settings: Settings) -> None:
    configure_logging(
        level=settings.LOG_LEVEL,
        app_mode=settings.APP_MODE,
        json_logs=settings.LOG_JSON,
    )


def _build_orchestrator(settings: Settings, session: aiohttp.ClientSession) -> PipelineOrchestrator:
    storage = S3Storage(settings, prefix="crops/")
    redis_client = build_runtime_state_client(settings.REDIS_URL)
    vision = GoogleVisionService(settings, max_results=settings.VISION_MAX_RESULTS)
    search = SearchApiService(settings, session=session)

    return PipelineOrchestrator(
        settings=settings,
        redis_client=redis_client,
        storage=storage,
        vision=vision,
        search=search,
        config=OrchestratorConfig(
            max_objects=settings.MAX_OBJECTS,
            min_score=settings.VISION_MIN_SCORE,
            min_area=settings.VISION_MIN_AREA,
            prefetch_n=settings.VISION_PREFETCH_N,
            iou_threshold=settings.VISION_IOU_THRESHOLD,
            containment_threshold=settings.VISION_CONTAINMENT_THRESHOLD,
            max_per_label=settings.VISION_MAX_PER_LABEL,
        ),
    )


async def _build_bot_runtime(
    settings: Settings,
    orchestrator: PipelineOrchestrator,
) -> BotRuntime:
    bot = Bot(token=settings.TELEGRAM_TOKEN)
    dispatcher = Dispatcher()
    user_store = UserDataStore(redis_url=settings.REDIS_URL)
    redis_client = build_runtime_state_client(settings.REDIS_URL)
    whitelist_service = WhitelistService()
    dispatcher.include_router(
        build_router(
            orchestrator,
            user_store,
            redis_client,
            settings.admin_chat_ids,
            whitelist_service,
            settings=settings,
        )
    )
    return BotRuntime(
        bot=bot,
        dispatcher=dispatcher,
        user_store=user_store,
    )


async def _build_runtime(settings: Settings, *, include_bot_runtime: bool) -> Runtime:
    session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=settings.TIMEOUT))
    orchestrator = _build_orchestrator(settings, session)
    bot_runtime = None
    if include_bot_runtime:
        if not settings.TELEGRAM_TOKEN:
            raise RuntimeError("TELEGRAM_TOKEN is required when Telegram runtime is enabled")
        try:
            bot_runtime = await _build_bot_runtime(settings, orchestrator)
        except Exception:
            if (settings.APP_MODE or "").lower().strip() == "worker":
                logging.getLogger("worker").exception(
                    "bot_runtime_init_failed worker will continue without Telegram runtime"
                )
                bot_runtime = None
            else:
                raise
    return Runtime(
        session=session,
        orchestrator=orchestrator,
        bot_runtime=bot_runtime,
    )


async def run_polling() -> None:
    settings = Settings()
    _setup_logging(settings)
    runtime = await _build_runtime(settings, include_bot_runtime=True)
    assert runtime.bot_runtime is not None
    try:
        await runtime.bot_runtime.dispatcher.start_polling(runtime.bot_runtime.bot)
    finally:
        await runtime.session.close()
        await runtime.bot_runtime.bot.session.close()


async def run_webhook() -> None:
    settings = Settings()
    _setup_logging(settings)
    queue = CloudTasksQueue(settings)
    redis_client: RuntimeStateClient | None = None
    try:
        redis_client = build_runtime_state_client(settings.REDIS_URL)
    except Exception:
        logging.getLogger("webhook").exception("Failed to init runtime state client")

    async def handle_webhook(request: web.Request) -> web.Response:
        secret = settings.TELEGRAM_WEBHOOK_SECRET
        if secret:
            header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if header != secret:
                return web.Response(status=401, text="unauthorized")
        try:
            payload = await request.json()
        except Exception:
            return web.Response(status=400, text="invalid json")
        update_id = payload.get("update_id")
        task_id = f"telegram-{update_id}" if update_id is not None else None
        if update_id is not None and redis_client is not None:
            try:
                is_new = redis_client.mark_update_seen(int(update_id))
                if not is_new:
                    logging.getLogger("webhook").info(
                        "Duplicate update_id=%s, skipping enqueue", update_id
                    )
                    return web.Response(text="duplicate")
            except Exception:
                logging.getLogger("webhook").exception(
                    "Failed to check duplicate update_id=%s", update_id
                )
                return web.Response(status=503, text="dedupe_unavailable")
        await queue.enqueue(payload, task_id=task_id)
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_post(settings.TELEGRAM_WEBHOOK_PATH, handle_webhook)
    port = int(os.getenv("PORT", "8080"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logging.getLogger("webhook").info("Webhook server started on port %s", port)
    while True:
        await asyncio.sleep(3600)


async def run_worker() -> None:
    settings = Settings()
    _setup_logging(settings)
    runtime = await _build_runtime(settings, include_bot_runtime=bool(settings.TELEGRAM_TOKEN))
    tbank_service = TBankAcquiringService(settings)
    whitelist_service = WhitelistService()
    checkout_service = CheckoutService(settings)

    async def handle_task(request: web.Request) -> web.Response:
        secret = settings.CLOUD_TASKS_REQUEST_SECRET
        if secret and request.headers.get("X-Task-Secret") != secret:
            return web.Response(status=401, text="unauthorized")
        queue_header = request.headers.get("X-CloudTasks-QueueName") or request.headers.get(
            "X-Cloud-Tasks-QueueName"
        )
        task_name = request.headers.get("X-CloudTasks-TaskName") or request.headers.get(
            "X-Cloud-Tasks-TaskName"
        )
        task_eta = request.headers.get("X-CloudTasks-TaskETA") or request.headers.get(
            "X-Cloud-Tasks-TaskETA"
        )
        task_exec = request.headers.get("X-CloudTasks-TaskExecutionCount") or request.headers.get(
            "X-Cloud-Tasks-TaskExecutionCount"
        )
        if not queue_header:
            logging.getLogger("worker").warning(
                "Missing Cloud Tasks queue header; proceeding due to valid auth."
            )
        try:
            payload = await request.json()
        except Exception as exc:
            logging.getLogger("worker").warning("Invalid JSON payload: %s", exc)
            return web.Response(status=400, text="invalid json")
        try:
            update = Update.model_validate(payload)
        except Exception as exc:
            logging.getLogger("worker").warning("Invalid Telegram update: %s", exc)
            return web.Response(status=400, text="invalid update")
        queue_delay = None
        if task_eta:
            try:
                from datetime import datetime, timezone

                eta_dt = datetime.fromisoformat(task_eta.replace("Z", "+00:00"))
                queue_delay = (datetime.now(timezone.utc) - eta_dt).total_seconds()
            except Exception:
                queue_delay = None
        logging.getLogger("worker").info(
            "task_received update_id=%s task=%s queue=%s eta=%s exec_count=%s queue_delay_s=%s",
            update.update_id,
            task_name,
            queue_header,
            task_eta,
            task_exec,
            None if queue_delay is None else f"{queue_delay:.2f}",
        )
        if runtime.bot_runtime is None:
            logging.getLogger("worker").error("telegram_task_rejected bot_runtime_unavailable")
            return web.Response(status=503, text="bot_runtime_unavailable")
        await runtime.bot_runtime.dispatcher.feed_update(runtime.bot_runtime.bot, update)
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_post("/tasks/telegram", handle_task)

    async def handle_web_job(request: web.Request) -> web.Response:
        secret = settings.CLOUD_TASKS_REQUEST_SECRET
        if secret and request.headers.get("X-Task-Secret") != secret:
            return web.Response(status=401, text="unauthorized")
        try:
            payload = await request.json()
        except Exception:
            return web.Response(status=400, text="invalid json")
        job_id = str(payload.get("job_id") or "").strip()
        if not job_id:
            return web.Response(status=400, text="missing job_id")
        jobs_service = JobsService(settings)
        result = await jobs_service.run_job_async(job_id, runtime.orchestrator)
        result_status = str(result.get("status") or "").strip().lower()
        if result_status in {"failed", "not_found", "skipped"}:
            logging.getLogger("worker").warning(
                "web_job_terminal_status job_id=%s status=%s",
                job_id,
                result_status,
            )
            return web.Response(text=result_status or "ok")
        return web.Response(text="ok")

    app.router.add_post("/tasks/web-job", handle_web_job)

    async def handle_tbank_notify(request: web.Request) -> web.Response:
        if not tbank_service.is_configured():
            return web.Response(status=503, text="tbank_disabled")
        try:
            payload = await request.json()
        except Exception:
            return web.Response(status=400, text="invalid json")
        if not isinstance(payload, dict):
            return web.Response(status=400, text="invalid payload")
        if not tbank_service.verify_notification(payload):
            logging.getLogger("worker").warning(
                "tbank_notify_invalid_token order_id=%s payment_id=%s status=%s",
                payload.get("OrderId"),
                payload.get("PaymentId"),
                payload.get("Status"),
            )
            return web.Response(status=401, text="unauthorized")

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

        webhook_event = await whitelist_service.register_webhook_event(
            provider="tbank_sbp",
            event_type="payment_notification",
            idempotency_key=_webhook_idempotency_key("tbank_sbp", payload),
            order_id=order_id or None,
            provider_payment_id=provider_payment_id,
            payload=payload,
            max_attempts=int(settings.BILLING_WEBHOOK_MAX_ATTEMPTS or 3),
        )
        webhook_event_id = str(webhook_event.get("event_id") or "").strip()
        if not bool(webhook_event.get("should_process")):
            logging.getLogger("worker").info(
                "tbank_notify_skipped order_id=%s payment_id=%s webhook_status=%s attempts=%s",
                order_id,
                provider_payment_id,
                webhook_event.get("status"),
                webhook_event.get("attempts"),
            )
            return web.Response(text="OK")

        try:
            result = await checkout_service.apply_tbank_notification(
                order_id=order_id,
                provider_payment_id=provider_payment_id,
                status=status,
                success=success,
                amount_kopecks=amount_kopecks,
                payload=payload,
                accept_statuses=tbank_service.accepted_statuses(),
            )
            if result.get("status") in {"not_found", "not_applicable"}:
                result = await whitelist_service.apply_tbank_notification(
                    order_id=order_id,
                    provider_payment_id=provider_payment_id,
                    status=status,
                    success=success,
                    amount_kopecks=amount_kopecks,
                    payload=payload,
                    accept_statuses=tbank_service.accepted_statuses(),
                )
        except Exception:
            logging.getLogger("worker").exception(
                "tbank_notify_apply_failed order_id=%s payment_id=%s status=%s",
                order_id,
                provider_payment_id,
                status,
            )
            if webhook_event_id:
                await whitelist_service.finalize_webhook_event(
                    event_id=webhook_event_id,
                    status="failed",
                    error="apply_exception",
                )
            return web.Response(status=500, text="failed")

        result_status = str(result.get("status", "unknown"))
        if webhook_event_id:
            final_status = "processed"
            if result_status in {"ignored", "invalid_amount", "partial_refund_ignored", "not_found"}:
                final_status = "ignored"
            await whitelist_service.finalize_webhook_event(
                event_id=webhook_event_id,
                status=final_status,
                error=None,
            )
        logging.getLogger("worker").info(
            "tbank_notify_processed order_id=%s payment_id=%s status=%s result=%s",
            order_id,
            provider_payment_id,
            status,
            result_status,
        )
        if result_status == "applied":
            user_id = int(result.get("user_id") or 0)
            credits = int(result.get("credits") or 0)
            remaining = result.get("remaining_requests")
            payment_id = str(result.get("payment_id") or "").strip()
            if payment_id:
                try:
                    link_message = await whitelist_service.get_tbank_payment_link_message(payment_id)
                    if str(link_message.get("status")) == "ok":
                        if runtime.bot_runtime is None:
                            logging.getLogger("worker").warning(
                                "tbank_notify_skip_menu_cleanup payment_id=%s reason=bot_runtime_unavailable",
                                payment_id,
                            )
                        else:
                            await runtime.bot_runtime.bot.edit_message_reply_markup(
                                chat_id=int(link_message["chat_id"]),
                                message_id=int(link_message["message_id"]),
                                reply_markup=None,
                            )
                except Exception:
                    logging.getLogger("worker").exception(
                        "tbank_notify_clear_payment_menu_failed payment_id=%s",
                        payment_id,
                    )
            if user_id > 0:
                remaining_text = "unlimited" if remaining is None else f"{int(remaining)}🎟️"
                try:
                    if runtime.bot_runtime is None:
                        logging.getLogger("worker").warning(
                            "tbank_notify_skip_user_message user_id=%s order_id=%s reason=bot_runtime_unavailable",
                            user_id,
                            order_id,
                        )
                    else:
                        await runtime.bot_runtime.bot.send_message(
                            chat_id=user_id,
                            text=(
                                f"Оплата получена. Зачислено: {credits}🎟️. Доступно: {remaining_text}."
                                if credits > 0
                                else "Оплата получена. Баланс обновлен."
                            ),
                        )
                        language = await runtime.bot_runtime.user_store.get_language(user_id)
                        version = await runtime.bot_runtime.user_store.bump_ui_version(user_id)
                        menu_text, menu_markup = build_main_menu_screen(
                            language,
                            version=version,
                            issued_ts=int(time.time()),
                        )
                        await runtime.bot_runtime.bot.send_message(
                            chat_id=user_id,
                            text=menu_text,
                            reply_markup=menu_markup,
                            parse_mode="HTML",
                        )
                except Exception:
                    logging.getLogger("worker").exception(
                        "tbank_notify_send_message_failed user_id=%s order_id=%s",
                        user_id,
                        order_id,
                    )
        elif result_status == "refunded":
            user_id = int(result.get("user_id") or 0)
            credits = int(result.get("credits") or 0)
            remaining = result.get("remaining_requests")
            payment_id = str(result.get("payment_id") or "").strip()
            if payment_id:
                try:
                    link_message = await whitelist_service.get_tbank_payment_link_message(payment_id)
                    if str(link_message.get("status")) == "ok":
                        if runtime.bot_runtime is None:
                            logging.getLogger("worker").warning(
                                "tbank_notify_skip_menu_cleanup payment_id=%s reason=bot_runtime_unavailable",
                                payment_id,
                            )
                        else:
                            await runtime.bot_runtime.bot.edit_message_reply_markup(
                                chat_id=int(link_message["chat_id"]),
                                message_id=int(link_message["message_id"]),
                                reply_markup=None,
                            )
                except Exception:
                    logging.getLogger("worker").exception(
                        "tbank_notify_clear_payment_menu_failed payment_id=%s",
                        payment_id,
                    )
            if user_id > 0:
                remaining_text = "unlimited" if remaining is None else f"{int(remaining)}🎟️"
                try:
                    if runtime.bot_runtime is None:
                        logging.getLogger("worker").warning(
                            "tbank_notify_skip_refund_message user_id=%s order_id=%s reason=bot_runtime_unavailable",
                            user_id,
                            order_id,
                        )
                    else:
                        await runtime.bot_runtime.bot.send_message(
                            chat_id=user_id,
                            text=(
                                f"Платеж отменен/возвращен. Списано: {credits}🎟️. Доступно: {remaining_text}."
                                if credits > 0
                                else "Платеж отменен/возвращен. Баланс обновлен."
                            ),
                        )
                except Exception:
                    logging.getLogger("worker").exception(
                        "tbank_notify_send_refund_message_failed user_id=%s order_id=%s",
                        user_id,
                        order_id,
                    )
        return web.Response(text="OK")

    notify_path = str(settings.TBANK_NOTIFICATION_PATH or "/payments/tbank/notify")
    if not notify_path.startswith("/"):
        notify_path = "/" + notify_path
    app.router.add_post(notify_path, handle_tbank_notify)

    async def on_cleanup(_: web.Application) -> None:
        await runtime.session.close()
        await TBankAcquiringService.close_shared_session()
        if runtime.bot_runtime is not None:
            await runtime.bot_runtime.bot.session.close()

    app.on_cleanup.append(on_cleanup)
    port = int(os.getenv("PORT", "8080"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logging.getLogger("worker").info("Worker server started on port %s", port)
    while True:
        await asyncio.sleep(3600)


def main() -> None:
    settings = Settings()
    mode = settings.APP_MODE.lower().strip()
    if mode == "webhook":
        asyncio.run(run_webhook())
        return
    if mode == "worker":
        asyncio.run(run_worker())
        return
    asyncio.run(run_polling())


if __name__ == "__main__":
    main()
