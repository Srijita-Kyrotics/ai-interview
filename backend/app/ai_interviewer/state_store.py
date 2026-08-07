"""
Persistent Interview State Store
================================
Redis-backed store for interview state with checkpointing, recovery,
and session resumption.  Replaces the in-memory _active_runners dict.

When Redis is unavailable (e.g. local development without a Redis server,
or a transient outage), the store automatically falls back to an
in-memory adapter so the interview flow keeps working.  State persisted
through the fallback does NOT survive a process restart and is scoped to
a single worker.

Redis Schema:
  interview:{session_id}:state     → JSON serialized InterviewState
  interview:{session_id}:meta      → JSON metadata (created_at, status, platform_session_id)
  interview:{session_id}:timeline  → JSON list of timeline events
  interview:{session_id}:lock      → Mutex for concurrent access

All keys have a configurable TTL (default 4 hours) that resets on each write.
"""

from __future__ import annotations

import contextlib
import fnmatch
import json
import logging
import threading
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
        logger.info("Redis connection created: %s", settings.redis_url.split("@")[-1])
    return _redis


def close_redis():
    """Close the Redis connection."""
    global _redis
    if _redis:
        with contextlib.suppress(Exception):
            _redis.close()
        _redis = None


# ── In-Memory Fallback Backend ────────────────────────────────────────────────
# Minimal Redis-compatible adapter used when Redis cannot be reached.  It
# mirrors exactly the subset of the redis client API used by
# InterviewStateStore so callers never need to branch on the backend.


class _MemoryPipeline:
    def __init__(self, client: "_MemoryRedisClient"):
        self._client = client
        self._ops: list[tuple] = []

    def set(self, name, value, ex=None):
        self._ops.append(("set", name, value, ex))
        return self

    def expire(self, name, ttl):
        self._ops.append(("expire", name, ttl))
        return self

    def delete(self, *names):
        self._ops.append(("delete", names))
        return self

    def rpush(self, name, value):
        self._ops.append(("rpush", name, value))
        return self

    def execute(self):
        for op in self._ops:
            kind = op[0]
            if kind == "set":
                self._client.set(op[1], op[2], ex=op[3])
            elif kind == "expire":
                self._client.expire(op[1], op[2])
            elif kind == "delete":
                self._client.delete(*op[1])
            elif kind == "rpush":
                self._client.rpush(op[1], op[2])


class _MemoryRedisClient:
    """Thread-safe, TTL-aware in-memory store mimicking the redis client subset."""

    def __init__(self):
        self._data: dict[str, tuple[str, float | None]] = {}
        self._lists: dict[str, list[str]] = {}
        self._mu = threading.RLock()

    def _now(self) -> float:
        return time.time()

    def _prune(self, name: str) -> bool:
        entry = self._data.get(name)
        if entry is None:
            return False
        value, expires_at = entry
        if expires_at is not None and self._now() > expires_at:
            del self._data[name]
            return True
        return False

    def set(self, name, value, ex=None, nx=None):
        expires_at = self._now() + ex if ex is not None else None
        with self._mu:
            if nx:
                if self._data.get(name) is not None:
                    return None
                self._data[name] = (value, expires_at)
                return True
            self._data[name] = (value, expires_at)
        return True

    def get(self, name):
        with self._mu:
            if self._prune(name):
                return None
            entry = self._data.get(name)
            return entry[0] if entry else None

    def expire(self, name, ttl):
        with self._mu:
            entry = self._data.get(name)
            if entry is None:
                return False
            self._data[name] = (entry[0], self._now() + ttl)
            return True

    def delete(self, *names):
        removed = 0
        with self._mu:
            for name in names:
                if name in self._data:
                    del self._data[name]
                    removed += 1
                if name in self._lists:
                    del self._lists[name]
        return removed

    def exists(self, *names):
        count = 0
        with self._mu:
            for name in names:
                if self._data.get(name) is not None and not self._prune(name):
                    count += 1
        return count

    def rpush(self, name, value):
        with self._mu:
            self._lists.setdefault(name, []).append(value)
        return True

    def lrange(self, name, start, end):
        with self._mu:
            items = self._lists.get(name, [])
            if not items:
                return []
            # Emulate redis negative indexing semantics
            size = len(items)
            if start < 0:
                start = max(size + start, 0)
            if end < 0:
                end = size + end
            end = min(end, size - 1)
            if start > end or start >= size:
                return []
            return items[start : end + 1]

    def scan_iter(self, match=None, count=None):
        with self._mu:
            names = list(self._data.keys())
        for name in names:
            with self._mu:
                if self._prune(name):
                    continue
            if match and not fnmatch.fnmatchcase(name, match):
                continue
            yield name

    def pipeline(self):
        return _MemoryPipeline(self)

    def ping(self):
        return True


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
    Persistent store for interview state.

    Backed by Redis when available; transparently falls back to an
    in-memory adapter when Redis is unreachable so development and demo
    flows keep working.

    Provides:
    - save / load / delete for interview state
    - TTL-based automatic expiry
    - Metadata tracking (status, created_at, platform_session_id)
    - Timeline event logging
    - Mutex-based locking for concurrent access
    """

    def __init__(self, redis_client=None):
        if redis_client is None:
            redis_client = get_redis()
        self._r = redis_client
        self._ttl = _ttl_seconds()
        self.backend = "redis" if isinstance(redis_client, redis.Redis) else "memory"

    # ── State CRUD ────────────────────────────────────────────────────────

    def save_state(self, session_id: str, state: dict) -> None:
        """Persist the full interview state to the store."""
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
            logger.error("Failed to save state to store: %s", e)

    def load_state(self, session_id: str) -> dict | None:
        """Load the full interview state from the store."""
        try:
            raw = self._r.get(_state_key(session_id))
            if raw:
                # Refresh TTL on access
                self._r.expire(_state_key(session_id), self._ttl)
                self._r.expire(_meta_key(session_id), self._ttl)
                return json.loads(raw)
        except redis.RedisError as e:
            logger.error("Failed to load state from store: %s", e)
        return None

    def delete_state(self, session_id: str) -> None:
        """Remove interview state from the store."""
        try:
            pipe = self._r.pipeline()
            pipe.delete(_state_key(session_id), _meta_key(session_id), _timeline_key(session_id))
            pipe.execute()
        except redis.RedisError as e:
            logger.error("Failed to delete state from store: %s", e)

    def exists(self, session_id: str) -> bool:
        """Check if an interview session exists in the store."""
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
        """Acquire a lock for a session (prevents concurrent WS handlers)."""
        try:
            return self._r.set(f"interview:{session_id}:lock", "1", nx=True, ex=ttl)
        except redis.RedisError:
            return True  # Fail open if store is down

    def release_lock(self, session_id: str) -> None:
        """Release the lock."""
        with contextlib.suppress(redis.RedisError):
            self._r.delete(f"interview:{session_id}:lock")

    # ── Health Check ──────────────────────────────────────────────────────

    def health_check(self) -> bool:
        """Check store connectivity."""
        try:
            return bool(self._r.ping())
        except redis.RedisError:
            return False


# ── Singleton ─────────────────────────────────────────────────────────────────

_store: InterviewStateStore | None = None


def get_state_store() -> InterviewStateStore:
    """Get or create the singleton state store, falling back to memory when
    Redis is unreachable so the interview flow always works."""
    global _store
    if _store is None:
        try:
            client = get_redis()
            store = InterviewStateStore(redis_client=client)
            if store.health_check():
                _store = store
                logger.info("Interview state store: Redis (persistent)")
            else:
                _store = InterviewStateStore(redis_client=_MemoryRedisClient())
                logger.warning(
                    "Redis unavailable — interview state store using in-memory fallback "
                    "(state will NOT survive a process restart)"
                )
        except Exception as exc:
            _store = InterviewStateStore(redis_client=_MemoryRedisClient())
            logger.warning(
                "Redis unavailable (%s) — interview state store using in-memory fallback "
                "(state will NOT survive a process restart)",
                exc,
            )
    return _store
