"""Cloud Tasks client wrapper."""
from __future__ import annotations

import json
import logging

from google.api_core import exceptions as gcp_exceptions
from google.cloud import tasks_v2

from config import Settings


_LOG = logging.getLogger("cloud_tasks")


class CloudTasksQueue:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = tasks_v2.CloudTasksClient()
        self._queue_path = self._client.queue_path(
            settings.cloud_tasks_project_id,
            settings.CLOUD_TASKS_LOCATION,
            settings.CLOUD_TASKS_QUEUE,
        )

    async def enqueue(
        self,
        payload: dict,
        task_id: str | None = None,
        *,
        target_url: str | None = None,
    ) -> None:
        worker_url = target_url or self._settings.CLOUD_TASKS_WORKER_URL
        if not worker_url:
            raise RuntimeError("CLOUD_TASKS_WORKER_URL is not configured.")

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._settings.CLOUD_TASKS_REQUEST_SECRET:
            headers["X-Task-Secret"] = self._settings.CLOUD_TASKS_REQUEST_SECRET

        http_request: dict = {
            "http_method": tasks_v2.HttpMethod.POST,
            "url": worker_url,
            "headers": headers,
            "body": body,
        }
        if self._settings.CLOUD_TASKS_SERVICE_ACCOUNT:
            http_request["oidc_token"] = {
                "service_account_email": self._settings.CLOUD_TASKS_SERVICE_ACCOUNT
            }

        task: dict = {"http_request": http_request}
        if task_id:
            task["name"] = self._client.task_path(
                self._settings.cloud_tasks_project_id,
                self._settings.CLOUD_TASKS_LOCATION,
                self._settings.CLOUD_TASKS_QUEUE,
                task_id,
            )

        try:
            await _run_in_thread(self._client.create_task, parent=self._queue_path, task=task)
        except gcp_exceptions.AlreadyExists:
            _LOG.info("Task already exists: %s", task_id)
        except gcp_exceptions.GoogleAPICallError as exc:
            _LOG.exception("Cloud Tasks enqueue failed: %s", exc)
            raise


async def _run_in_thread(func, *args, **kwargs):
    import asyncio

    return await asyncio.to_thread(func, *args, **kwargs)
