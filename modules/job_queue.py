"""
Redis-backed job queue helpers.
"""
from __future__ import annotations

import os
from typing import Optional

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
JOB_QUEUE_KEY = os.getenv("JOB_QUEUE_KEY", "jarvis:jobs")


class JobQueue:
    def __init__(self, redis_url: str = REDIS_URL, queue_key: str = JOB_QUEUE_KEY):
        self._queue_key = queue_key
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def enqueue(self, job_id: str) -> None:
        self._client.rpush(self._queue_key, job_id)

    def dequeue(self, timeout: int = 5) -> Optional[str]:
        item = self._client.blpop(self._queue_key, timeout=timeout)
        if not item:
            return None
        return item[1]
