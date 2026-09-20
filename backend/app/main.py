from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pythonjsonlogger import json as json_logger

from app.ai_interviewer.router import router as ai_interviewer_router
from app.auth_routes import router as auth_router
from app.auth_service import has_strong_password, hash_password, validate_email_format, verify_password
from app.config import BASE_DIR, settings
from app.db import (
    check_db_health,
    cleanup_expired_cache,
    cleanup_stale_data,
    close_pool,
    init_db,
    migrate_accounts_json,
)
from app.helpers import create_token, decode_token, default_scores
from app.observability import (
    ObservabilityMiddleware,
    configure_logging,
    get_health_status,
    get_metrics,
)
from app.session_routes import router as session_router
from app.session_routes import score_open_round

__all__ = [
    "app",
    "create_token",
    "decode_token",
    "default_scores",
    "has_strong_password",
    "hash_password",
    "score_open_round",
    "validate_email_format",
    "verify_password",
]

logger = logging.getLogger("ai_interview")

if settings.log_format == "json":
    handler = logging.StreamHandler()
    handler.setFormatter(json_logger.JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), handlers=[handler])
else:
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")


@asynccontextmanager
async def lifespan(app):
    init_db()
    _accounts_file = BASE_DIR / "backend" / "accounts.json"
    migrate_accounts_json(_accounts_file)
    cleanup_stale_data(
        otp_ttl=settings.otp_ttl_seconds,
        captcha_ttl=settings.captcha_ttl_seconds,
        session_retention_days=settings.session_retention_days,
    )
    cleanup_expired_cache()

    try:
        from app.ai_interviewer.state_store import get_state_store

        store = get_state_store()
        if store.backend == "redis":
            logger.info("Interview state store: Redis connected (persistent)")
        else:
            logger.warning(
                "Interview state store: in-memory fallback (Redis unavailable) — "
                "state will NOT survive a process restart"
            )
    except Exception as exc:
        logger.warning("Interview state store: in-memory fallback (%s)", exc)

    logger.info("Application started", extra={"environment": settings.environment})
    yield

    try:
        from app.ai_interviewer.state_store import close_redis

        close_redis()
    except Exception:
        pass
    close_pool()
    logger.info("Application shutting down")


app = FastAPI(title="AI Mock Recruitment Platform", lifespan=lifespan)
app.include_router(ai_interviewer_router)
app.include_router(auth_router)
app.include_router(session_router)

from fastapi import APIRouter
api_router = APIRouter(prefix="/api")
api_router.include_router(ai_interviewer_router)
api_router.include_router(auth_router)
api_router.include_router(session_router)
app.include_router(api_router)

# Add observability middleware (must be first to capture all requests)
app.add_middleware(ObservabilityMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob:; "
        f"connect-src 'self' {settings.csp_connect_sources} ws://localhost:* wss://localhost:*"
    )
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/health")
async def health_check():
    db_ok = check_db_health()
    redis_ok = False
    state_store = "unavailable"
    try:
        from app.ai_interviewer.state_store import get_state_store

        store = get_state_store()
        state_store = store.backend
        redis_ok = store.backend == "redis" and store.health_check()
    except Exception:
        pass

    status = "healthy" if db_ok else "degraded"
    code = 200 if db_ok else 503
    return JSONResponse(
        status_code=code,
        content={
            "status": status,
            "database": "ok" if db_ok else "unreachable",
            "redis": "ok" if redis_ok else "unavailable",
            "state_store": state_store,
            "environment": settings.environment,
        },
    )


@app.get("/health/detailed")
async def health_detailed():
    """Detailed health check with system metrics."""
    health = await get_health_status()
    health["database"] = "ok" if check_db_health() else "unreachable"
    return health


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=await get_metrics(), media_type="text/plain")


import os
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

static_dir = os.path.join(settings.base_dir, "static")
if not os.path.exists(static_dir):
    static_dir = os.path.join(os.getcwd(), "static")

if os.path.exists(static_dir):
    assets_dir = os.path.join(static_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        path = os.path.join(static_dir, full_path)
        if full_path and os.path.isfile(path):
            return FileResponse(path)
        index_file = os.path.join(static_dir, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        return JSONResponse(status_code=404, content={"message": "Frontend not found"})
