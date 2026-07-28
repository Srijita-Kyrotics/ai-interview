"""Shared helpers used by both main.py and interview_ws.py."""

from __future__ import annotations

import re
import time
from typing import Any

import jwt

from app.config import settings

JWT_SECRET = settings.resolved_jwt_secret
JWT_ALGORITHM = settings.jwt_algorithm


def create_token(email: str, role: str) -> str:
    payload = {
        "sub": email,
        "email": email,
        "role": role,
        "exp": time.time() + settings.jwt_expiry_hours * 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None


def sanitize_for_ai(text: str, max_length: int = 5000) -> str:
    text = text[:max_length]
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


def default_scores() -> dict[str, int]:
    return dict(settings.default_scores)
