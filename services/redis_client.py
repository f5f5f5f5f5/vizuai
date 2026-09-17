"""Runtime state helper for job tracking and metrics.

Redis is used when configured. A local in-memory fallback keeps low-traffic
web-first runtimes usable after Memorystore removal, with the explicit tradeoff
that state is process-local and lost on restart.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from redis import Redis

from models.schemas import Job


class RedisClient:
    def __init__(self, redis_url: str, job_ttl_days: int = 7) -> None:
        self._client = Redis.from_url(redis_url, decode_responses=True)
        self._job_ttl_seconds = job_ttl_days * 24 * 60 * 60

    def new_job_id(self, chat_id: int) -> str:
        ts = int(time.time() * 1000)
        return f"{chat_id}-{ts}"

    def store_job(self, job: Job) -> None:
        key = f"job:{job.job_id}"
        self._client.set(key, job.model_dump_json())
        self._client.expire(key, self._job_ttl_seconds)

    def get_job(self, job_id: str) -> Job | None:
        raw = self._client.get(f"job:{job_id}")
        if not raw:
            return None
        return Job.model_validate_json(raw)

    def store_debug(self, job_id: str, payload: dict, ttl_seconds: int | None = None) -> None:
        key = f"debug:{job_id}"
        self._client.set(key, json.dumps(payload))
        self._client.expire(key, ttl_seconds or self._job_ttl_seconds)

    def get_debug(self, job_id: str) -> dict | None:
        raw = self._client.get(f"debug:{job_id}")
        return json.loads(raw) if raw else None

    def set_debug_mode(self, chat_id: int, enabled: bool) -> None:
        key = f"debug_mode:{chat_id}"
        self._client.set(key, "1" if enabled else "0")
        self._client.expire(key, self._job_ttl_seconds)

    def get_debug_mode(self, chat_id: int) -> bool:
        key = f"debug_mode:{chat_id}"
        raw = self._client.get(key)
        if raw is None:
            return False
        return raw == "1"

    def mark_update_seen(self, update_id: int, ttl_seconds: int = 172800) -> bool:
        key = f"update:{update_id}"
        return bool(self._client.set(key, "1", nx=True, ex=ttl_seconds))

    def record_metric(self, chat_id: int, duration: float, success: bool) -> None:
        day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        metrics_key = f"metrics:daily:{day_key}"
        self._client.hincrby(metrics_key, "requests", 1)
        if success:
            self._client.hincrby(metrics_key, "success", 1)
        else:
            self._client.hincrby(metrics_key, "fail", 1)
        self._client.hset(f"user:{chat_id}", mapping={"duration": duration})
        self._client.expire(metrics_key, self._job_ttl_seconds)

    def record_cost(self, service: str, amount: float) -> None:
        day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        costs_key = f"metrics:costs:{day_key}"
        self._client.hincrbyfloat(costs_key, service, amount)
        self._client.expire(costs_key, self._job_ttl_seconds)

    def get_daily_metrics(self, day_key: str | None = None) -> dict[str, int]:
        day_key = day_key or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        metrics_key = f"metrics:daily:{day_key}"
        raw = self._client.hgetall(metrics_key)
        return {key: int(value) for key, value in raw.items()}

    def get_daily_costs(self, day_key: str | None = None) -> dict[str, float]:
        day_key = day_key or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        costs_key = f"metrics:costs:{day_key}"
        raw = self._client.hgetall(costs_key)
        return {key: float(value) for key, value in raw.items()}

    def try_acquire_global_job_slot(
        self,
        job_id: str,
        *,
        limit: int,
        lease_seconds: int,
    ) -> bool:
        safe_limit = max(int(limit or 1), 1)
        lease_ms = max(int(lease_seconds or 1), 1) * 1000
        now_ms = int(time.time() * 1000)
        lua = """
        local key = KEYS[1]
        local now_ms = tonumber(ARGV[1])
        local lease_ms = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local job_id = ARGV[4]
        local expires_at = now_ms + lease_ms

        redis.call("ZREMRANGEBYSCORE", key, "-inf", now_ms)
        local exists = redis.call("ZSCORE", key, job_id)
        if exists then
            redis.call("ZADD", key, expires_at, job_id)
            redis.call("PEXPIRE", key, lease_ms)
            return 1
        end

        local count = redis.call("ZCARD", key)
        if count < limit then
            redis.call("ZADD", key, expires_at, job_id)
            redis.call("PEXPIRE", key, lease_ms)
            return 1
        end
        return 0
        """
        result = self._client.eval(
            lua,
            1,
            "jobs:global:active",
            now_ms,
            lease_ms,
            safe_limit,
            job_id,
        )
        return bool(int(result or 0))

    def release_global_job_slot(self, job_id: str) -> None:
        lua = """
        local key = KEYS[1]
        local job_id = ARGV[1]
        redis.call("ZREM", key, job_id)
        return 1
        """
        self._client.eval(lua, 1, "jobs:global:active", job_id)

    def get_global_active_job_count(self) -> int:
        now_ms = int(time.time() * 1000)
        lua = """
        local key = KEYS[1]
        local now_ms = tonumber(ARGV[1])
        redis.call("ZREMRANGEBYSCORE", key, "-inf", now_ms)
        return redis.call("ZCARD", key)
        """
        result = self._client.eval(lua, 1, "jobs:global:active", now_ms)
        try:
            return int(result or 0)
        except Exception:
            return 0

    def get_global_active_jobs(self, limit: int = 20) -> list[dict[str, int | str]]:
        now_ms = int(time.time() * 1000)
        safe_limit = max(int(limit or 1), 1)
        lua = """
        local key = KEYS[1]
        local now_ms = tonumber(ARGV[1])
        local lim = tonumber(ARGV[2])
        redis.call("ZREMRANGEBYSCORE", key, "-inf", now_ms)
        local rows = redis.call("ZRANGE", key, 0, lim - 1, "WITHSCORES")
        return rows
        """
        rows = self._client.eval(lua, 1, "jobs:global:active", now_ms, safe_limit) or []
        result: list[dict[str, int | str]] = []
        for i in range(0, len(rows), 2):
            try:
                job_id = str(rows[i])
                expires_at_ms = int(float(rows[i + 1]))
            except Exception:
                continue
            ttl_sec = max(int((expires_at_ms - now_ms) / 1000), 0)
            result.append(
                {
                    "job_id": job_id,
                    "expires_at_ms": expires_at_ms,
                    "ttl_sec": ttl_sec,
                }
            )
        return result


class LocalRuntimeStateClient:
    def __init__(self, job_ttl_days: int = 7) -> None:
        self._job_ttl_seconds = job_ttl_days * 24 * 60 * 60
        self._jobs: dict[str, tuple[float, str]] = {}
        self._debug: dict[str, tuple[float, dict]] = {}
        self._debug_mode: dict[int, tuple[float, bool]] = {}
        self._seen_updates: dict[int, float] = {}
        self._metrics: dict[str, dict[str, int]] = {}
        self._costs: dict[str, dict[str, float]] = {}
        self._active_jobs: dict[str, float] = {}

    def new_job_id(self, chat_id: int) -> str:
        ts = int(time.time() * 1000)
        return f"{chat_id}-{ts}"

    def store_job(self, job: Job) -> None:
        self._jobs[job.job_id] = (self._expires_at(self._job_ttl_seconds), job.model_dump_json())

    def get_job(self, job_id: str) -> Job | None:
        row = self._jobs.get(job_id)
        if not row:
            return None
        expires_at, raw = row
        if self._expired(expires_at):
            self._jobs.pop(job_id, None)
            return None
        return Job.model_validate_json(raw)

    def store_debug(self, job_id: str, payload: dict, ttl_seconds: int | None = None) -> None:
        self._debug[job_id] = (self._expires_at(ttl_seconds or self._job_ttl_seconds), dict(payload))

    def get_debug(self, job_id: str) -> dict | None:
        row = self._debug.get(job_id)
        if not row:
            return None
        expires_at, payload = row
        if self._expired(expires_at):
            self._debug.pop(job_id, None)
            return None
        return dict(payload)

    def set_debug_mode(self, chat_id: int, enabled: bool) -> None:
        self._debug_mode[chat_id] = (self._expires_at(self._job_ttl_seconds), bool(enabled))

    def get_debug_mode(self, chat_id: int) -> bool:
        row = self._debug_mode.get(chat_id)
        if not row:
            return False
        expires_at, enabled = row
        if self._expired(expires_at):
            self._debug_mode.pop(chat_id, None)
            return False
        return enabled

    def mark_update_seen(self, update_id: int, ttl_seconds: int = 172800) -> bool:
        self._cleanup_seen_updates()
        if update_id in self._seen_updates:
            return False
        self._seen_updates[update_id] = self._expires_at(ttl_seconds)
        return True

    def record_metric(self, chat_id: int, duration: float, success: bool) -> None:
        day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        metrics = self._metrics.setdefault(day_key, {})
        metrics["requests"] = int(metrics.get("requests", 0)) + 1
        key = "success" if success else "fail"
        metrics[key] = int(metrics.get(key, 0)) + 1

    def record_cost(self, service: str, amount: float) -> None:
        day_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        costs = self._costs.setdefault(day_key, {})
        costs[service] = float(costs.get(service, 0.0)) + float(amount or 0.0)

    def get_daily_metrics(self, day_key: str | None = None) -> dict[str, int]:
        day_key = day_key or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return dict(self._metrics.get(day_key, {}))

    def get_daily_costs(self, day_key: str | None = None) -> dict[str, float]:
        day_key = day_key or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return dict(self._costs.get(day_key, {}))

    def try_acquire_global_job_slot(
        self,
        job_id: str,
        *,
        limit: int,
        lease_seconds: int,
    ) -> bool:
        self._cleanup_active_jobs()
        safe_limit = max(int(limit or 1), 1)
        if job_id in self._active_jobs or len(self._active_jobs) < safe_limit:
            self._active_jobs[job_id] = self._expires_at(max(int(lease_seconds or 1), 1))
            return True
        return False

    def release_global_job_slot(self, job_id: str) -> None:
        self._active_jobs.pop(job_id, None)

    def get_global_active_job_count(self) -> int:
        self._cleanup_active_jobs()
        return len(self._active_jobs)

    def get_global_active_jobs(self, limit: int = 20) -> list[dict[str, int | str]]:
        self._cleanup_active_jobs()
        now = time.time()
        rows: list[dict[str, int | str]] = []
        for job_id, expires_at in list(self._active_jobs.items())[: max(int(limit or 1), 1)]:
            expires_at_ms = int(expires_at * 1000)
            rows.append(
                {
                    "job_id": job_id,
                    "expires_at_ms": expires_at_ms,
                    "ttl_sec": max(int(expires_at - now), 0),
                }
            )
        return rows

    @staticmethod
    def _expires_at(ttl_seconds: int) -> float:
        return time.time() + max(int(ttl_seconds or 1), 1)

    @staticmethod
    def _expired(expires_at: float) -> bool:
        return expires_at <= time.time()

    def _cleanup_seen_updates(self) -> None:
        now = time.time()
        for update_id, expires_at in list(self._seen_updates.items()):
            if expires_at <= now:
                self._seen_updates.pop(update_id, None)

    def _cleanup_active_jobs(self) -> None:
        now = time.time()
        for job_id, expires_at in list(self._active_jobs.items()):
            if expires_at <= now:
                self._active_jobs.pop(job_id, None)


RuntimeStateClient = RedisClient | LocalRuntimeStateClient


def build_runtime_state_client(redis_url: str | None, job_ttl_days: int = 7) -> RuntimeStateClient:
    if redis_url:
        return RedisClient(redis_url, job_ttl_days=job_ttl_days)
    return LocalRuntimeStateClient(job_ttl_days=job_ttl_days)
