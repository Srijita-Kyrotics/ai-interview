from __future__ import annotations

import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel

from app.auth_service import (
    consume_otp_and_captcha,
    create_account,
    generate_captcha_payload,
    has_strong_password,
    hash_password,
    send_email_otp,
    validate_email_format,
    validate_otp_and_captcha,
    verify_password,
)
from app.config import settings
from app.db import delete_otp, load_otp, load_user, save_captcha, save_otp, save_user, user_exists
from app.helpers import create_token, decode_token

router = APIRouter()


class SendOtpRequest(BaseModel):
    email: str


class VerifyAuthRequest(BaseModel):
    email: str
    otp: str
    captcha_token: str
    captcha_answer: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class EmailCheckRequest(BaseModel):
    email: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    token: str
    new_password: str


OTP_TTL_SECONDS = settings.otp_ttl_seconds
CAPTCHA_TTL_SECONDS = settings.captcha_ttl_seconds
OTP_RATE_LIMIT = settings.otp_rate_limit
OTP_RATE_WINDOW = settings.otp_rate_window


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else request.client.host if request.client else "unknown"


async def get_current_user(authorization: str | None = Header(None)) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"email": payload["email"], "role": payload.get("role", "candidate")}


async def require_candidate(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user["role"] not in ("candidate", "recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Candidate access required")
    return user


async def require_recruiter(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Recruiter or admin access required")
    return user


async def require_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/auth/captcha")
def get_captcha():
    captcha = generate_captcha_payload()
    save_captcha(captcha["token"], {"answer": captcha["answer"], "expiresAt": time.time() + CAPTCHA_TTL_SECONDS})
    return {"token": captcha["token"], "question": captcha["question"]}


@router.post("/auth/send-otp")
def send_otp(payload: SendOtpRequest, request: Request):
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "Enter a valid email address."}

    ip = _client_ip(request)
    if not _check_rate_limit(f"otp:{email}", settings.otp_rate_limit, settings.otp_rate_window):
        return {"ok": False, "error": "Too many requests. Please wait a few minutes."}
    if not _check_rate_limit(f"otp_ip:{ip}", settings.otp_ip_rate_limit, settings.otp_rate_window):
        return {"ok": False, "error": "Too many requests from this IP. Please wait."}

    otp = f"{secrets.randbelow(900000) + 100000}"
    save_otp(email, {"otp": otp, "expiresAt": time.time() + OTP_TTL_SECONDS, "attempts": 0})
    sent = send_email_otp(email, otp)
    response = {"ok": True, "sent": sent, "message": "OTP sent to your email."}
    if not sent:
        response["message"] = "SMTP is not configured. Showing development OTP."
        if settings.environment == "development":
            response["dev_otp"] = otp
    return response


@router.get("/health/smtp")
def check_smtp_status(user: dict[str, Any] = Depends(require_admin)):
    return {
        "smtp_host": settings.smtp_host or "NOT SET",
        "smtp_port": settings.smtp_port,
        "smtp_user": settings.smtp_user or "NOT SET",
        "smtp_from": settings.smtp_from or "NOT SET",
        "smtp_password_set": bool(settings.smtp_password),
        "all_configured": settings.smtp_configured,
    }


@router.post("/auth/verify")
def verify_auth(payload: VerifyAuthRequest):
    email = payload.email.strip().lower()
    is_valid, error_message = validate_otp_and_captcha(email, payload.otp, payload.captcha_token, payload.captcha_answer)
    if not is_valid:
        return {"ok": False, "error": error_message}

    consume_otp_and_captcha(email, payload.captcha_token)
    return {"ok": True}


@router.post("/auth/register")
def register(payload: RegisterRequest):
    email = payload.email.strip().lower()
    if not validate_email_format(email):
        return {"ok": False, "error": "Enter a valid email address."}

    if not payload.name.strip():
        return {"ok": False, "error": "Full name is required."}

    if not has_strong_password(payload.password):
        return {"ok": False, "error": "Password must be at least 8 characters and include an uppercase letter and a digit."}

    if user_exists(email):
        return {"ok": False, "error": "An account already exists for this email."}

    account = create_account(email, payload.password, payload.name)
    token = create_token(email, account["role"])
    return {"ok": True, "message": "Account created successfully.", "token": token, "user": {"name": account["name"], "email": email, "role": account["role"]}}


@router.post("/auth/login")
def login(payload: LoginRequest):
    email = payload.email.strip().lower()
    if not validate_email_format(email):
        return {"ok": False, "error": "Enter a valid email address."}

    account = load_user(email)
    if not account or not verify_password(payload.password, account):
        return {"ok": False, "error": "Email or password is incorrect."}

    role = account.get("role", "candidate")
    token = create_token(email, role)
    return {"ok": True, "message": "Login successful.", "name": account.get("name", email.split("@")[0]), "token": token, "user": {"name": account.get("name", email.split("@")[0]), "email": email, "role": role}}


@router.post("/auth/check-email")
def check_email(payload: EmailCheckRequest):
    email = payload.email.strip().lower()
    if not validate_email_format(email):
        return {"ok": False, "exists": False, "error": "Enter a valid email address."}

    exists = user_exists(email)
    return {"ok": True, "exists": exists}


@router.post("/auth/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    email = payload.email.strip().lower()
    if not validate_email_format(email):
        return {"ok": False, "error": "Enter a valid email address."}

    if not user_exists(email):
        return {"ok": False, "error": "No account found with this email."}

    token = "1234" if settings.environment == "development" else secrets.token_urlsafe(32)
    save_otp(email, {"otp": token, "expiresAt": time.time() + OTP_TTL_SECONDS, "attempts": 0})

    sent = send_email_otp(email, token)
    response = {"ok": True, "message": "Password reset token sent to your email."}
    if not sent:
        response["message"] = "SMTP is not configured. Use the development token below."
        if settings.environment == "development":
            response["dev_token"] = token
    return response


@router.post("/auth/reset-password")
def reset_password(payload: ResetPasswordRequest):
    email = payload.email.strip().lower()
    if not validate_email_format(email):
        return {"ok": False, "error": "Enter a valid email address."}

    if not has_strong_password(payload.new_password):
        return {"ok": False, "error": "Password must be at least 8 characters and include an uppercase letter and a digit."}

    otp_state = load_otp(email)
    now = time.time()

    if not otp_state or otp_state["expiresAt"] < now:
        return {"ok": False, "error": "Reset token expired. Please request a new one."}
    if otp_state["otp"] != payload.token.strip():
        otp_state["attempts"] += 1
        save_otp(email, otp_state)
        return {"ok": False, "error": "Invalid reset token."}

    delete_otp(email)

    account = load_user(email)
    if not account:
        return {"ok": False, "error": "Account not found."}

    password_data = hash_password(payload.new_password)
    save_user(email, account.get("name", email.split("@")[0]), password_data["salt"], password_data["hash"], account.get("role", "candidate"))

    return {"ok": True, "message": "Password reset successful. You can now login."}


def _check_rate_limit(key: str, limit: int, window: int) -> bool:
    from app.db import check_rate_limit

    return check_rate_limit(key, limit, window)
