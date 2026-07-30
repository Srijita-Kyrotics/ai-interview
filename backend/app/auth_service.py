from __future__ import annotations

import hashlib
import hmac
import logging
import random
import re
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from typing import Any

from app.config import settings
from app.db import (
    delete_captcha,
    delete_otp,
    get_all_users,
    load_captcha,
    load_otp,
    load_user,
    save_captcha,
    save_otp,
    save_user,
    user_exists,
)

logger = logging.getLogger("ai_interview")


def hash_password(password: str, salt: str | None = None) -> dict[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), settings.pbkdf2_iterations)
    return {"salt": salt, "hash": key.hex()}


def verify_password(password: str, stored: dict[str, str]) -> bool:
    hashed = hash_password(password, stored.get("salt"))
    return hmac.compare_digest(hashed["hash"], stored.get("hash", ""))


def validate_email_format(email: str) -> bool:
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email))


def has_strong_password(password: str) -> bool:
    return (
        len(password) >= settings.min_password_length
        and bool(re.search(r"[A-Z]", password))
        and bool(re.search(r"[0-9]", password))
    )


def send_email_otp(email: str, otp: str) -> bool:
    if not settings.smtp_configured:
        logger.warning("SMTP not configured")
        return False

    message = EmailMessage()
    message["Subject"] = settings.email_subject
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(f"Your Mock Recruitment Platform OTP is {otp}. It expires in 5 minutes.")

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls(context=context)
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
        logger.info("OTP email sent successfully", extra={"email": email})
        return True
    except Exception as e:  # pragma: no cover - depends on SMTP config
        logger.error("SMTP Error", extra={"error_type": type(e).__name__, "error": str(e)})
        return False


def generate_captcha_payload() -> dict[str, Any]:
    left = random.randint(10, 39)
    right = random.randint(2, 15)
    token = secrets.token_urlsafe(24)
    return {
        "token": token,
        "question": f"{left} + {right} = ?",
        "answer": str(left + right),
    }


def validate_otp_and_captcha(email: str, otp: str, captcha_token: str, captcha_answer: str) -> tuple[bool, str]:
    """Validate OTP and CAPTCHA without consuming them. Returns (is_valid, error_message)."""
    otp_state = load_otp(email)
    captcha_state = load_captcha(captcha_token)
    now = time.time()

    if not captcha_state or captcha_state["expiresAt"] < now:
        return False, "Captcha expired. Please refresh it."
    if captcha_state["answer"] != captcha_answer.strip():
        return False, "Captcha answer is incorrect."

    if not otp_state or otp_state["expiresAt"] < now:
        return False, "OTP expired. Please request a new OTP."
    if otp_state["attempts"] >= settings.max_otp_attempts:
        return False, "Too many OTP attempts. Please request a new OTP."
    if otp_state["otp"] != otp.strip():
        otp_state["attempts"] += 1
        save_otp(email, otp_state)
        return False, "Invalid OTP. Please enter the latest verification code."

    return True, ""


def consume_otp_and_captcha(email: str, captcha_token: str) -> None:
    """Remove OTP and CAPTCHA from state after successful verification."""
    delete_otp(email)
    delete_captcha(captcha_token)


def create_account(email: str, password: str, name: str, role: str | None = None) -> dict[str, Any]:
    password_data = hash_password(password)
    resolved_role = role or ("admin" if not get_all_users() else "candidate")
    save_user(email, name.strip(), password_data["salt"], password_data["hash"], resolved_role)
    return {"email": email, "name": name.strip(), "role": resolved_role, "password_data": password_data}
