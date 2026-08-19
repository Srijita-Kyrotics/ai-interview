"""
Observability Module
====================
Provides structured logging, metrics collection, and distributed tracing
for the AI Interview platform.
"""

from __future__ import annotations

import contextlib
import functools
import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

import psutil
from prometheus_client import Counter, Gauge, Histogram, CollectorRegistry, generate_latest

# ── Context Variables for Request Tracking ─────────────────────────────────────

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
session_id_var: ContextVar[str] = ContextVar("session_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
span_id_var: ContextVar[str] = ContextVar("span_id", default="")

# ── Structured Logger ──────────────────────────────────────────────────────────

class StructuredLogger:
    """
    JSON-structured logger with contextual fields.
    
    Adds request_id, session_id, user_id, trace_id to every log entry.
    """
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self._extra_fields: Dict[str, Any] = {}
    
    def _get_context(self) -> Dict[str, Any]:
        """Get current context variables."""
        return {
            "request_id": request_id_var.get(),
            "session_id": session_id_var.get(),
            "user_id": user_id_var.get(),
            "trace_id": trace_id_var.get(),
            "span_id": span_id_var.get(),
        }
    
    def _log(self, level: int, message: str, **kwargs) -> None:
        """Log with structured fields."""
        context = self._get_context()
        extra = {**context, **self._extra_fields, **kwargs}
        
        # Filter out None values
        extra = {k: v for k, v in extra.items() if v is not None and v != ""}
        
        # Create structured log entry
        log_data = {
            "timestamp": time.time(),
            "level": logging.getLevelName(level),
            "message": message,
            **extra,
        }
        
        # Log as JSON if structured logging is enabled
        if os.getenv("STRUCTURED_LOGGING", "true").lower() == "true":
            self.logger.log(level, json.dumps(log_data))
        else:
            # Human-readable format
            extra_str = " ".join(f"{k}={v}" for k, v in extra.items())
            self.logger.log(level, f"{message} {extra_str}")
    
    def bind(self, **kwargs) -> StructuredLogger:
        """Create a new logger with additional bound fields."""
        new_logger = StructuredLogger(self.logger.name)
        new_logger._extra_fields = {**self._extra_fields, **kwargs}
        return new_logger
    
    def debug(self, message: str, **kwargs) -> None:
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        self._log(logging.ERROR, message, **kwargs)
    
    def exception(self, message: str, **kwargs) -> None:
        self._log(logging.ERROR, message, **kwargs)


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)


# ── Metrics Collection ──────────────────────────────────────────────────────────

# Custom registry to avoid conflicts
_metrics_registry = CollectorRegistry()

# HTTP Metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=_metrics_registry,
)

http_request_duration = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    registry=_metrics_registry,
)

# WebSocket Metrics
ws_connections_active = Gauge(
    "ws_connections_active",
    "Active WebSocket connections",
    ["endpoint"],
    registry=_metrics_registry,
)

ws_messages_total = Counter(
    "ws_messages_total",
    "Total WebSocket messages",
    ["endpoint", "direction", "type"],
    registry=_metrics_registry,
)

ws_message_latency = Histogram(
    "ws_message_latency_seconds",
    "WebSocket message processing latency",
    ["endpoint", "type"],
    registry=_metrics_registry,
)

# Interview Metrics
interview_sessions_total = Counter(
    "interview_sessions_total",
    "Total interview sessions",
    ["status", "type"],
    registry=_metrics_registry,
)

interview_duration = Histogram(
    "interview_duration_seconds",
    "Interview session duration",
    ["type"],
    registry=_metrics_registry,
)

interview_questions_total = Counter(
    "interview_questions_total",
    "Total questions asked in interviews",
    ["type", "stage"],
    registry=_metrics_registry,
)

interview_scores = Histogram(
    "interview_scores",
    "Interview scores distribution",
    ["dimension"],
    buckets=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
    registry=_metrics_registry,
)

# LLM Metrics
llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM requests",
    ["provider", "model", "status"],
    registry=_metrics_registry,
)

llm_request_duration = Histogram(
    "llm_request_duration_seconds",
    "LLM request duration",
    ["provider", "model"],
    registry=_metrics_registry,
)

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens used",
    ["provider", "model", "type"],
    registry=_metrics_registry,
)

# STT/TTS Metrics
stt_requests_total = Counter(
    "stt_requests_total",
    "Total STT requests",
    ["provider", "status"],
    registry=_metrics_registry,
)

stt_duration = Histogram(
    "stt_duration_seconds",
    "STT processing duration",
    ["provider"],
    registry=_metrics_registry,
)

tts_requests_total = Counter(
    "tts_requests_total",
    "Total TTS requests",
    ["provider", "status"],
    registry=_metrics_registry,
)

tts_duration = Histogram(
    "tts_duration_seconds",
    "TTS synthesis duration",
    ["provider"],
    registry=_metrics_registry,
)

# Code Execution Metrics
code_execution_total = Counter(
    "code_execution_total",
    "Total code executions",
    ["language", "status"],
    registry=_metrics_registry,
)

code_execution_duration = Histogram(
    "code_execution_duration_seconds",
    "Code execution duration",
    ["language"],
    registry=_metrics_registry,
)

# Proctoring Metrics
proctoring_events_total = Counter(
    "proctoring_events_total",
    "Total proctoring events",
    ["event_type", "severity"],
    registry=_metrics_registry,
)

proctoring_integrity_score = Gauge(
    "proctoring_integrity_score",
    "Current integrity score",
    ["session_id"],
    registry=_metrics_registry,
)

# System Metrics
system_memory_usage = Gauge(
    "system_memory_usage_bytes",
    "System memory usage",
    registry=_metrics_registry,
)

system_cpu_usage = Gauge(
    "system_cpu_usage_percent",
    "System CPU usage percentage",
    registry=_metrics_registry,
)

# Database Metrics
db_query_duration = Histogram(
    "db_query_duration_seconds",
    "Database query duration",
    ["operation"],
    registry=_metrics_registry,
)

db_connections_active = Gauge(
    "db_connections_active",
    "Active database connections",
    registry=_metrics_registry,
)

# Redis Metrics
redis_operations_total = Counter(
    "redis_operations_total",
    "Total Redis operations",
    ["operation", "status"],
    registry=_metrics_registry,
)

redis_operation_duration = Histogram(
    "redis_operation_duration_seconds",
    "Redis operation duration",
    ["operation"],
    registry=_metrics_registry,
)


def record_http_request(method: str, endpoint: str, status: int, duration: float) -> None:
    """Record HTTP request metrics."""
    http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
    http_request_duration.labels(method=method, endpoint=endpoint).observe(duration)


def record_ws_message(endpoint: str, direction: str, msg_type: str, latency: float = 0) -> None:
    """Record WebSocket message metrics."""
    ws_messages_total.labels(endpoint=endpoint, direction=direction, type=msg_type).inc()
    if latency > 0:
        ws_message_latency.labels(endpoint=endpoint, type=msg_type).observe(latency)


def record_interview_session(status: str, interview_type: str, duration: float = 0) -> None:
    """Record interview session metrics."""
    interview_sessions_total.labels(status=status, type=interview_type).inc()
    if duration > 0:
        interview_duration.labels(type=interview_type).observe(duration)


def record_llm_request(provider: str, model: str, status: str, duration: float, 
                       prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
    """Record LLM request metrics."""
    llm_requests_total.labels(provider=provider, model=model, status=status).inc()
    llm_request_duration.labels(provider=provider, model=model).observe(duration)
    if prompt_tokens > 0:
        llm_tokens_total.labels(provider=provider, model=model, type="prompt").inc(prompt_tokens)
    if completion_tokens > 0:
        llm_tokens_total.labels(provider=provider, model=model, type="completion").inc(completion_tokens)


def record_code_execution(language: str, status: str, duration: float) -> None:
    """Record code execution metrics."""
    code_execution_total.labels(language=language, status=status).inc()
    code_execution_duration.labels(language=language).observe(duration)


def record_proctoring_event(event_type: str, severity: str, session_id: str, 
                           integrity_score: float = 0) -> None:
    """Record proctoring event metrics."""
    proctoring_events_total.labels(event_type=event_type, severity=severity).inc()
    if integrity_score > 0:
        proctoring_integrity_score.labels(session_id=session_id).set(integrity_score)


def update_system_metrics() -> None:
    """Update system-level metrics."""
    try:
        memory = psutil.virtual_memory()
        system_memory_usage.set(memory.used)
        system_cpu_usage.set(psutil.cpu_percent(interval=0.1))
    except Exception:
        pass


# ── Distributed Tracing ────────────────────────────────────────────────────────

@dataclass
class Span:
    """Represents a single span in a trace."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    logs: list = field(default_factory=list)
    
    def finish(self, end_time: float = None) -> None:
        self.end_time = end_time or time.time()
    
    def set_tag(self, key: str, value: Any) -> None:
        self.tags[key] = value
    
    def log(self, message: str, **fields) -> None:
        self.logs.append({
            "timestamp": time.time(),
            "message": message,
            **fields,
        })


class Tracer:
    """
    Simple distributed tracer.
    
    Creates and manages spans for request tracing.
    """
    
    def __init__(self, service_name: str = "ai-interview"):
        self.service_name = service_name
        self._spans: Dict[str, Span] = {}
    
    def start_span(
        self,
        operation_name: str,
        parent_span: Optional[Span] = None,
        trace_id: Optional[str] = None,
    ) -> Span:
        """Start a new span."""
        trace_id = trace_id or parent_span.trace_id if parent_span else str(uuid.uuid4())
        span_id = str(uuid.uuid4())[:16]
        parent_span_id = parent_span.span_id if parent_span else None
        
        span = Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            operation_name=operation_name,
            start_time=time.time(),
        )
        
        # Set context variables
        trace_id_var.set(trace_id)
        span_id_var.set(span_id)
        
        self._spans[span_id] = span
        return span
    
    def finish_span(self, span: Span) -> None:
        """Finish a span and export it."""
        span.finish()
        
        # Export span (in production, send to Jaeger/Zipkin/OTel collector)
        self._export_span(span)
        
        # Clean up
        self._spans.pop(span.span_id, None)
    
    def _export_span(self, span: Span) -> None:
        """Export span to tracing backend."""
        # In production, this would send to Jaeger, Zipkin, or OTel collector
        # For now, log as structured data
        logger = get_logger("tracing")
        logger.info(
            "span_completed",
            trace_id=span.trace_id,
            span_id=span.span_id,
            parent_span_id=span.parent_span_id,
            operation=span.operation_name,
            duration_ms=round((span.end_time - span.start_time) * 1000, 2),
            tags=span.tags,
            logs=span.logs,
        )
    
    def trace(self, operation_name: str):
        """Decorator to trace a function."""
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                span = self.start_span(operation_name)
                span.set_tag("function", func.__name__)
                try:
                    result = await func(*args, **kwargs)
                    span.set_tag("status", "success")
                    return result
                except Exception as e:
                    span.set_tag("status", "error")
                    span.set_tag("error", str(e))
                    span.log("exception", error=str(e), error_type=type(e).__name__)
                    raise
                finally:
                    self.finish_span(span)
            
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                span = self.start_span(operation_name)
                span.set_tag("function", func.__name__)
                try:
                    result = func(*args, **kwargs)
                    span.set_tag("status", "success")
                    return result
                except Exception as e:
                    span.set_tag("status", "error")
                    span.set_tag("error", str(e))
                    span.log("exception", error=str(e), error_type=type(e).__name__)
                    raise
                finally:
                    self.finish_span(span)
            
            import asyncio
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper
        return decorator


# Global tracer instance
_tracer: Optional[Tracer] = None


def get_tracer() -> Tracer:
    """Get the global tracer instance."""
    global _tracer
    if _tracer is None:
        _tracer = Tracer()
    return _tracer


# ── Middleware for FastAPI ────────────────────────────────────────────────────

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware to add observability to all HTTP requests."""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate request ID
        request_id = str(uuid.uuid4())[:8]
        request_id_var.set(request_id)
        
        # Extract trace context from headers
        trace_id = request.headers.get("x-trace-id", str(uuid.uuid4()))
        trace_id_var.set(trace_id)
        
        # Start span
        tracer = get_tracer()
        span = tracer.start_span(
            f"{request.method} {request.url.path}",
            trace_id=trace_id,
        )
        span.set_tag("http.method", request.method)
        span.set_tag("http.url", str(request.url))
        span.set_tag("http.scheme", request.url.scheme)
        
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Record metrics
            duration = time.time() - start_time
            record_http_request(
                method=request.method,
                endpoint=request.url.path,
                status=response.status_code,
                duration=duration,
            )
            
            span.set_tag("http.status_code", response.status_code)
            span.set_tag("duration_ms", round(duration * 1000, 2))
            
            # Add trace headers to response
            response.headers["x-request-id"] = request_id
            response.headers["x-trace-id"] = trace_id
            
            return response
            
        except Exception as e:
            duration = time.time() - start_time
            span.set_tag("status", "error")
            span.set_tag("error", str(e))
            span.log("exception", error=str(e))
            raise
        finally:
            tracer.finish_span(span)


# ── Health Check Metrics ───────────────────────────────────────────────────────

async def get_metrics() -> bytes:
    """Get Prometheus metrics."""
    return generate_latest(_metrics_registry)


async def get_health_status() -> Dict[str, Any]:
    """Get comprehensive health status with metrics."""
    update_system_metrics()
    
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "service": "ai-interview",
        "metrics": {
            "memory_usage_mb": round(psutil.Process().memory_info().rss / 1024 / 1024, 2),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "active_connections": ws_connections_active._value.get(),
        },
    }


# ── Logging Configuration ──────────────────────────────────────────────────────

def configure_logging(
    level: int = logging.INFO,
    structured: bool = True,
    json_format: bool = True,
) -> None:
    """
    Configure application-wide logging.
    
    Args:
        level: Logging level
        structured: Enable structured logging
        json_format: Output logs as JSON
    """
    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
    
    # Set environment variables for structured logger
    os.environ["STRUCTURED_LOGGING"] = "true" if structured else "false"
    
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    # Set specific loggers to DEBUG if needed
    if level <= logging.DEBUG:
        logging.getLogger("ai_interview").setLevel(logging.DEBUG)
    
    # Capture warnings
    logging.captureWarnings(True)
    
    # Log startup
    logger = get_logger("startup")
    logger.info(
        "Logging configured",
        level=logging.getLevelName(level),
        structured=structured,
        json_format=json_format,
    )


# ── Context Manager for Request Scoping ────────────────────────────────────────

@contextlib.contextmanager
def request_context(
    request_id: str = None,
    session_id: str = None,
    user_id: str = None,
    trace_id: str = None,
):
    """Context manager to set request-scoped variables."""
    tokens = []
    
    if request_id:
        tokens.append(request_id_var.set(request_id))
    if session_id:
        tokens.append(session_id_var.set(session_id))
    if user_id:
        tokens.append(user_id_var.set(user_id))
    if trace_id:
        tokens.append(trace_id_var.set(trace_id))
    
    try:
        yield
    finally:
        for token in tokens:
            if token:
                token.var.reset(token)


# ── Utility Decorators ────────────────────────────────────────────────────────

def trace_function(operation_name: str = None):
    """Decorator to trace a function with the global tracer."""
    tracer = get_tracer()
    op_name = operation_name or ""
    return tracer.trace(op_name)


def measure_time(metric_name: str, labels: Dict[str, str] = None):
    """Decorator to measure function execution time."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = time.time() - start
                # Record to appropriate metric
                pass
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start
                pass
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator