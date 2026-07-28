"""
Persistent Interview State Store
================================
Redis-backed store for interview state with checkpointing, recovery,
and session resumption.  Replaces the in-memory _active_runners dict.

Redis Schema:
  interview:{session_id}:state     → JSON serialized InterviewState
  interview:{session_id}:meta      → JSON metadata (created_at, status, platform_session_id)
  interview:{session_id}:timeline  → JSON list of timeline events
  interview:{session_id}:lock      → Mutex for concurrent access

All keys have a configurable TTL (default 4 hours) that resets on each write.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time

import redis

from app.config import settings

logger = logging.getLogger("ai_interview.state_store")

# ── Redis Connection ──────────────────────────────────────────────────────────

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Get or create the Redis connection singleton."""
    global _redis
    if _redis is None:
        _redis = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        logger.info("Redis connected: %s", settings.redis_url.split("@")[-1])
    return _redis


def close_redis():
    """Close the Redis connection."""
    global _redis
    if _redis:
        _redis.close()
        _redis = None


# ── Key Helpers ───────────────────────────────────────────────────────────────

def _state_key(session_id: str) -> str:
    return f"interview:{session_id}:state"


def _meta_key(session_id: str) -> str:
    return f"interview:{session_id}:meta"


def _timeline_key(session_id: str) -> str:
    return f"interview:{session_id}:timeline"


def _ttl_seconds() -> int:
    return settings.redis_interview_ttl_hours * 3600


# ── State Store ───────────────────────────────────────────────────────────────

class InterviewStateStore:
    """
    Redis-backed persistent store for interview state.

    Provides:
    - save / load / delete for interview state
    - TTL-based automatic expiry
    - Metadata tracking (status, created_at, platform_session_id)
    - Timeline event logging
    - Mutex-based locking for concurrent access
    """

    def __init__(self, redis_client: redis.Redis | None = None):
        self._r = redis_client or get_redis()
        self._ttl = _ttl_seconds()

    # ── State CRUD ────────────────────────────────────────────────────────

    def save_state(self, session_id: str, state: dict) -> None:
        """Persist the full interview state to Redis."""
        try:
            pipe = self._r.pipeline()
            pipe.set(_state_key(session_id), json.dumps(state, default=str), ex=self._ttl)
            pipe.set(
                _meta_key(session_id),
                json.dumps({
                    "status": state.get("phase", "unknown"),
                    "updated_at": time.time(),
                    "questions_asked": state.get("questions_asked", 0),
                }, default=str),
                ex=self._ttl,
            )
            pipe.execute()
        except redis.RedisError as e:
            logger.error("Failed to save state to Redis: %s", e)

    def load_state(self, session_id: str) -> dict | None:
        """Load the full interview state from Redis."""
        try:
            raw = self._r.get(_state_key(session_id))
            if raw:
                # Refresh TTL on access
                self._r.expire(_state_key(session_id), self._ttl)
                self._r.expire(_meta_key(session_id), self._ttl)
                return json.loads(raw)
        except redis.RedisError as e:
            logger.error("Failed to load state from Redis: %s", e)
        return None

    def delete_state(self, session_id: str) -> None:
        """Remove interview state from Redis."""
        try:
            pipe = self._r.pipeline()
            pipe.delete(_state_key(session_id), _meta_key(session_id), _timeline_key(session_id))
            pipe.execute()
        except redis.RedisError as e:
            logger.error("Failed to delete state from Redis: %s", e)

    def exists(self, session_id: str) -> bool:
        """Check if an interview session exists in Redis."""
        try:
            return self._r.exists(_state_key(session_id)) > 0
        except redis.RedisError:
            return False

    # ── Metadata ──────────────────────────────────────────────────────────

    def save_meta(self, session_id: str, meta: dict) -> None:
        """Save session metadata (status, platform_session_id, etc.)."""
        try:
            self._r.set(_meta_key(session_id), json.dumps(meta, default=str), ex=self._ttl)
        except redis.RedisError as e:
            logger.error("Failed to save meta: %s", e)

    def load_meta(self, session_id: str) -> dict | None:
        """Load session metadata."""
        try:
            raw = self._r.get(_meta_key(session_id))
            if raw:
                return json.loads(raw)
        except redis.RedisError as e:
            logger.error("Failed to load meta: %s", e)
        return None

    # ── Timeline Events ───────────────────────────────────────────────────

    def append_timeline_event(self, session_id: str, event: dict) -> None:
        """Append a timestamped event to the interview timeline."""
        try:
            self._r.rpush(_timeline_key(session_id), json.dumps(event, default=str))
            self._r.expire(_timeline_key(session_id), self._ttl)
        except redis.RedisError as e:
            logger.error("Failed to append timeline event: %s", e)

    def get_timeline(self, session_id: str) -> list[dict]:
        """Get all timeline events for an interview session."""
        try:
            items = self._r.lrange(_timeline_key(session_id), 0, -1)
            return [json.loads(item) for item in items]
        except redis.RedisError as e:
            logger.error("Failed to get timeline: %s", e)
            return []

    # ── Session Discovery ─────────────────────────────────────────────────

    def find_active_sessions(self, platform_session_id: str | None = None) -> list[dict]:
        """
        Find all active interview sessions, optionally filtered by platform session.
        Returns list of metadata dicts with session_id.
        """
        try:
            pattern = "interview:*:meta"
            results = []
            for key in self._r.scan_iter(match=pattern, count=100):
                raw = self._r.get(key)
                if raw:
                    meta = json.loads(raw)
                    sid = key.split(":")[1]
                    if (meta.get("status") not in ("completed", "error")
                            and (platform_session_id is None or meta.get("platform_session_id") == platform_session_id)):
                            results.append({"session_id": sid, **meta})
            return results
        except redis.RedisError as e:
            logger.error("Failed to find active sessions: %s", e)
            return []

    def get_resumable_session(self, platform_session_id: str) -> str | None:
        """
        Find the most recent resumable interview session for a platform session.
        Returns interview_session_id if found and not completed, else None.
        """
        sessions = self.find_active_sessions(platform_session_id)
        if sessions:
            # Return the most recently updated
            sessions.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
            return sessions[0]["session_id"]
        return None

    # ── Locking ───────────────────────────────────────────────────────────

    def acquire_lock(self, session_id: str, ttl: int = 30) -> bool:
        """Acquire a distributed lock for a session (prevents concurrent WS handlers)."""
        try:
            return self._r.set(f"interview:{session_id}:lock", "1", nx=True, ex=ttl)
        except redis.RedisError:
            return True  # Fail open if Redis is down

    def release_lock(self, session_id: str) -> None:
        """Release the distributed lock."""
        with contextlib.suppress(redis.RedisError):
            self._r.delete(f"interview:{session_id}:lock")

    # ── Health Check ──────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Check Redis connectivity."""
        try:
            return self._r.ping()
        except redis.RedisError:
            return False


# ── Singleton ─────────────────────────────────────────────────────────────────

_store: InterviewStateStore | None = None


def get_state_store() -> InterviewStateStore:
    """Get or create the singleton state store."""
    global _store
    if _store is None:
        _store = InterviewStateStore()
    return _store
