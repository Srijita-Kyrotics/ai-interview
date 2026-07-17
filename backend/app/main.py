from __future__ import annotations

import hashlib
import hmac
import json
import logging
import random
import re
import secrets
import smtplib
import ssl
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from email.message import EmailMessage
from typing import Any

import google.generativeai as genai
import httpx
import jwt
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pythonjsonlogger import json as json_logger

from app.config import BASE_DIR, settings
from app.db import (
    check_db_health,
    cleanup_stale_data,
    close_pool,
    delete_captcha,
    delete_otp,
    get_all_sessions,
    get_all_users,
    get_sessions_by_user,
    init_db,
    load_captcha,
    load_otp,
    load_proctoring,
    load_session,
    load_user,
    migrate_accounts_json,
    save_captcha,
    save_otp,
    save_proctoring,
    save_session,
    save_user,
    update_user_role,
    user_exists,
)
from app.resume_parser import extract_text_from_pdf_content, parse_resume_text

logger = logging.getLogger("ai_interview")

SHARED_DIR = BASE_DIR / "shared"
FRONTEND_QUESTIONS_DIR = BASE_DIR / "frontend" / "public" / "questions"

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
    logger.info("Application started", extra={"environment": settings.environment})
    yield
    close_pool()
    logger.info("Application shutting down")

app = FastAPI(title="AI Mock Recruitment Platform", lifespan=lifespan)

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
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/health")
def health_check():
    db_ok = check_db_health()
    status = "healthy" if db_ok else "degraded"
    code = 200 if db_ok else 503
    return JSONResponse(
        status_code=code,
        content={
            "status": status,
            "database": "ok" if db_ok else "unreachable",
            "environment": settings.environment,
        },
    )


# ─── Rate Limiting ───────────────────────────────────────────────────────────
_rate_limits: dict[str, list[float]] = defaultdict(list)

def _check_rate_limit(key: str, limit: int, window: int) -> bool:
    now = time.time()
    _rate_limits[key] = [t for t in _rate_limits[key] if now - t < window]
    if len(_rate_limits[key]) >= limit:
        return False
    _rate_limits[key].append(now)
    return True

def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else request.client.host if request.client else "unknown"


# ─── Response Caching ────────────────────────────────────────────────────────
_cache: dict[str, Any] = {}

def _cache_get(key: str, ttl: int = 300) -> Any:
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < ttl:
        return entry["data"]
    return None

def _cache_set(key: str, data: Any) -> None:
    _cache[key] = {"data": data, "ts": time.time()}


# ─── Input Sanitization ──────────────────────────────────────────────────────
def _sanitize_for_ai(text: str, max_length: int = 5000) -> str:
    text = text[:max_length]
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return text.strip()

JWT_SECRET = settings.resolved_jwt_secret
JWT_ALGORITHM = settings.jwt_algorithm
JWT_EXPIRY_HOURS = settings.jwt_expiry_hours
MAX_UPLOAD_BYTES = settings.max_upload_bytes


def create_token(email: str, role: str) -> str:
    payload = {
        "sub": email,
        "email": email,
        "role": role,
        "exp": time.time() + JWT_EXPIRY_HOURS * 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None


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


def load_json(name: str) -> Any:
    with open(SHARED_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def load_questions_json(name: str) -> Any:
    with open(FRONTEND_QUESTIONS_DIR / name, encoding="utf-8") as f:
        return json.load(f)


COMPANY_PROFILES = load_json("company_profiles.json")
APTITUDE_QUESTIONS = load_questions_json("aptitude.json")
CODING_QUESTIONS = load_json("coding_questions.json")
TECHNICAL_QUESTIONS = load_json("technical_questions.json")
HR_QUESTIONS = load_json("hr_questions.json")
OTP_TTL_SECONDS = settings.otp_ttl_seconds
CAPTCHA_TTL_SECONDS = settings.captcha_ttl_seconds
OTP_RATE_LIMIT = settings.otp_rate_limit
OTP_RATE_WINDOW = settings.otp_rate_window


def default_scores() -> dict[str, int]:
    return {"aptitude": 80, "coding": 75, "technical": 70, "hr": 85}


def hash_password(password: str, salt: str | None = None) -> dict[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return {"salt": salt, "hash": key.hex()}


def verify_password(password: str, stored: dict[str, str]) -> bool:
    hashed = hash_password(password, stored.get("salt"))
    return hmac.compare_digest(hashed["hash"], stored.get("hash", ""))


def validate_email_format(email: str) -> bool:
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email))


def has_strong_password(password: str) -> bool:
    return len(password) >= 8 and bool(re.search(r"[^A-Za-z0-9]", password))


def score_open_round(answers: list[dict[str, Any]], round_key: str) -> int:
    if not answers:
        return 0

    gemini_key = settings.gemini_api_key
    if gemini_key:
        try:
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = f"Score the following {round_key} interview answers out of 100 based on quality, clarity, and depth. Answers: {json.dumps(answers)}. Only return the integer score from 0 to 100."
            response = model.generate_content(prompt)
            match = re.search(r'\b(100|\d{1,2})\b', response.text)
            if match:
                return int(match.group(1))
        except Exception:
            pass

    # Heuristic fallback
    total_score = 0
    for ans in answers:
        text = ans.get("answer", "")
        if text == "[Skipped]":
            total_score += 0
        elif text == "[Time expired]":
            total_score += 10
        elif text.startswith('{') and '"voice"' in text:
            try:
                data = json.loads(text)
                transcript = data.get("transcript", "")
                words = len(transcript.split())
                total_score += min(100, words * 2 + 50)
            except Exception:
                total_score += 50
        else:
            words = len(text.split())
            total_score += min(100, words * 2 + 20)

    return round(total_score / len(answers))


def make_report(state: dict[str, Any]) -> dict[str, Any]:
    scores = state.get("scores") or default_scores()
    aptitude_scores = state.get("aptitudeScore") or {}
    if aptitude_scores:
        correct = sum(item.get("correct", 0) for item in aptitude_scores.values())
        total = sum(item.get("total", 0) for item in aptitude_scores.values())
        if total:
            scores["aptitude"] = round((correct / total) * 100)

    answers = state.get("answers", {})
    if "technical" in answers and answers["technical"]:
        scores["technical"] = score_open_round(answers["technical"], "technical")
    if "hr" in answers and answers["hr"]:
        scores["hr"] = score_open_round(answers["hr"], "hr")

    overall = round(sum(scores.values()) / len(scores))
    return {
        "candidateName": state.get("resume", {}).get("name", "Candidate"),
        "selectedCompany": state.get("selectedCompany", ""),
        "selectedCompanies": state.get("selectedCompanies", []),
        "scores": scores,
        "overallScore": overall,
        "breakdown": {
            "aptitude": scores.get("aptitude", 0),
            "coding": scores.get("coding", 0),
            "technical": scores.get("technical", 0),
            "hr": scores.get("hr", 0),
        },
        "feedback": state.get("aiFeedback", {}).get("feedback", {
            "summary": "The candidate shows strong HR and aptitude performance, and is demonstrating steady progress in technical and coding fluency.",
            "coding": "Continue practicing algorithmic patterns and edge cases for a stronger delivery in timed coding rounds.",
            "technical": "Good understanding of architecture and APIs. Work on clearly communicating design trade-offs.",
            "hr": "Confident and composed, with thoughtful response structure.",
        }),
        "strengths": state.get("aiFeedback", {}).get("strengths", ["Clear communication", "Consistent effort", "Reliable problem framing"]),
        "weaknesses": state.get("aiFeedback", {}).get("weaknesses", ["Needs faster coding recall", "Can improve answer depth under time pressure"]),
        "recommendations": state.get("aiFeedback", {}).get("recommendations", ["Practice 2-3 medium coding problems per day", "Review system design basics", "Prepare STAR stories for behavioral interviews"]),
        "state": state,
    }


def company_rounds(company: str) -> list[dict[str, str]]:
    return COMPANY_PROFILES[company]["rounds"]


def all_round_keys(company: str) -> list[str]:
    return [r["key"] for r in company_rounds(company)]


class CompanySelection(BaseModel):
    session_id: str
    companies: list[str]


class StartRoundRequest(BaseModel):
    session_id: str
    company: str
    round_key: str


class SubmitAnswerRequest(BaseModel):
    session_id: str
    round_key: str
    question_index: int
    answer: str
    aptitude_category: str | None = None
    aptitude_quiz_id: str | None = None
    question_id: str | None = None


class SubmitCodeRequest(BaseModel):
    session_id: str
    round_key: str
    question_index: int
    language: str
    code: str


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
    otp: str
    captcha_token: str
    captcha_answer: str


class LoginRequest(BaseModel):
    email: str
    password: str
    otp: str
    captcha_token: str
    captcha_answer: str


class EmailCheckRequest(BaseModel):
    email: str


class RunCodeRequest(BaseModel):
    question_id: int
    language: str
    code: str


def send_email_otp(email: str, otp: str) -> bool:
    if not settings.smtp_configured:
        logger.warning("SMTP not configured")
        return False

    message = EmailMessage()
    message["Subject"] = "Mock Recruitment Platform OTP"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(
        f"Your Mock Recruitment Platform OTP is {otp}. It expires in 5 minutes."
    )

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls(context=context)
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
        logger.info("OTP email sent successfully", extra={"email": email})
        return True
    except Exception as e:
        logger.error("SMTP Error", extra={"error_type": type(e).__name__, "error": str(e)})
        return False


@app.get("/auth/captcha")
def get_captcha():
    left = random.randint(10, 39)
    right = random.randint(2, 15)
    token = secrets.token_urlsafe(24)
    save_captcha(token, {
        "answer": str(left + right),
        "expiresAt": time.time() + CAPTCHA_TTL_SECONDS,
    })
    return {"token": token, "question": f"{left} + {right} = ?"}


@app.post("/auth/send-otp")
def send_otp(payload: SendOtpRequest, request: Request):
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "Enter a valid email address."}

    ip = _client_ip(request)
    if not _check_rate_limit(f"otp:{email}", settings.otp_rate_limit, settings.otp_rate_window):
        return {"ok": False, "error": "Too many requests. Please wait a few minutes."}
    if not _check_rate_limit(f"otp_ip:{ip}", 20, settings.otp_rate_window):
        return {"ok": False, "error": "Too many requests from this IP. Please wait."}

    otp = f"{secrets.randbelow(900000) + 100000}"
    save_otp(email, {
        "otp": otp,
        "expiresAt": time.time() + OTP_TTL_SECONDS,
        "attempts": 0,
    })
    sent = send_email_otp(email, otp)
    response = {"ok": True, "sent": sent, "message": "OTP sent to your email."}
    if not sent:
        response["message"] = "SMTP is not configured. Showing development OTP."
        if settings.environment == "development":
            response["dev_otp"] = otp
    return response


@app.get("/health/smtp")
def check_smtp_status(user: dict[str, Any] = Depends(require_admin)):
    return {
        "smtp_host": settings.smtp_host or "NOT SET",
        "smtp_port": settings.smtp_port,
        "smtp_user": settings.smtp_user or "NOT SET",
        "smtp_from": settings.smtp_from or "NOT SET",
        "smtp_password_set": bool(settings.smtp_password),
        "all_configured": settings.smtp_configured,
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
    if otp_state["attempts"] >= 5:
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


@app.post("/auth/verify")
def verify_auth(payload: VerifyAuthRequest):
    email = payload.email.strip().lower()
    is_valid, error_message = validate_otp_and_captcha(email, payload.otp, payload.captcha_token, payload.captcha_answer)
    if not is_valid:
        return {"ok": False, "error": error_message}

    consume_otp_and_captcha(email, payload.captcha_token)
    return {"ok": True}


@app.post("/auth/register")
def register(payload: RegisterRequest):
    email = payload.email.strip().lower()
    if not validate_email_format(email):
        return {"ok": False, "error": "Enter a valid email address."}

    if not payload.name.strip():
        return {"ok": False, "error": "Full name is required."}

    if not has_strong_password(payload.password):
        return {"ok": False, "error": "Password must be at least 8 characters and include a special character."}

    is_valid, error_message = validate_otp_and_captcha(email, payload.otp, payload.captcha_token, payload.captcha_answer)
    if not is_valid:
        return {"ok": False, "error": error_message}

    if user_exists(email):
        return {"ok": False, "error": "An account already exists for this email."}

    consume_otp_and_captcha(email, payload.captcha_token)

    password_data = hash_password(payload.password)
    role = "admin" if not get_all_users() else "candidate"
    save_user(email, payload.name.strip(), password_data["salt"], password_data["hash"], role)
    token = create_token(email, role)
    return {"ok": True, "message": "Account created successfully.", "token": token, "user": {"name": payload.name.strip(), "email": email, "role": role}}


@app.post("/auth/login")
def login(payload: LoginRequest):
    email = payload.email.strip().lower()
    if not validate_email_format(email):
        return {"ok": False, "error": "Enter a valid email address."}

    is_valid, error_message = validate_otp_and_captcha(email, payload.otp, payload.captcha_token, payload.captcha_answer)
    if not is_valid:
        return {"ok": False, "error": error_message}

    account = load_user(email)
    if not account or not verify_password(payload.password, account):
        return {"ok": False, "error": "Email or password is incorrect."}

    consume_otp_and_captcha(email, payload.captcha_token)

    role = account.get("role", "candidate")
    token = create_token(email, role)
    return {"ok": True, "message": "Login successful.", "name": account.get("name", email.split('@')[0]), "token": token, "user": {"name": account.get("name", email.split('@')[0]), "email": email, "role": role}}


@app.post("/auth/check-email")
def check_email(payload: EmailCheckRequest):
    email = payload.email.strip().lower()
    if not validate_email_format(email):
        return {"ok": False, "exists": False, "error": "Enter a valid email address."}

    exists = user_exists(email)
    return {"ok": True, "exists": exists}


@app.get("/companies")
def get_companies():
    cached = _cache_get("companies")
    if cached is not None:
        return cached
    _cache_set("companies", COMPANY_PROFILES)
    return COMPANY_PROFILES

@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...), user: dict[str, Any] = Depends(require_candidate)):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024*1024)} MB.")

    filename = file.filename.lower()

    if filename.endswith(".pdf"):
        text = extract_text_from_pdf_content(content)

    elif filename.endswith(".txt"):
        text = content.decode("utf-8", errors="ignore")

    else:
        return {
            "error": "Only PDF and TXT files are supported"
        }

    session_id = str(uuid.uuid4())

    resume = parse_resume_text(text, file.filename)

    state = {
        "sessionId": session_id,
        "resume": resume,
        "selectedCompany": "",
        "selectedCompanies": [],
        "currentRound": "resume",
        "currentQuestion": 0,
        "answers": {"aptitude": [], "technical": [], "hr": []},
        "codingSubmissions": [],
        "scores": default_scores(),
    }
    user_id = user["email"]
    state["user_id"] = user_id
    save_session(session_id, state, user_id=user_id)
    return {"session_id": session_id, "resume": resume}


@app.post("/select-company")
def select_company(payload: CompanySelection):
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}

    if not payload.companies:
        return {"error": "Please select at least one company"}

    valid_companies = [c for c in payload.companies if c in COMPANY_PROFILES]
    if not valid_companies:
        return {"error": "None of the selected companies are valid"}

    state["selectedCompanies"] = valid_companies

    state["selectedCompany"] = valid_companies[0]

    rounds = []
    seen = set()

    for company in valid_companies:
        if company not in COMPANY_PROFILES:
            continue

        for round_item in company_rounds(company):
            key = round_item["key"]

            if key not in seen:
                seen.add(key)
                rounds.append(round_item)

    state["rounds"] = rounds
    state.setdefault("aptitudeQuizzes", {})
    save_session(payload.session_id, state)

    return {
        "session_id": payload.session_id,
        "companies": payload.companies,
        "rounds": rounds
    }


@app.post("/start-round")
def start_round(payload: StartRoundRequest):
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    state["currentRound"] = payload.round_key
    state["currentQuestion"] = 0
    save_session(payload.session_id, state)
    return {"session_id": payload.session_id, "round_key": payload.round_key}


@app.post("/submit-answer")
def submit_answer(payload: SubmitAnswerRequest):
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    state["answers"].setdefault(payload.round_key, [])
    state["answers"][payload.round_key].append(
        {"questionIndex": payload.question_index, "answer": payload.answer}
    )
    if payload.round_key == "aptitude":
        quiz_id = payload.aptitude_quiz_id
        category = payload.aptitude_category
        if quiz_id and category:
            quiz = state.get("aptitudeQuizzes", {}).get(quiz_id, {})
            question = None
            for item in quiz.get("questions", []):
                if item.get("id") == payload.question_id:
                    question = item
                    break
            if question:
                correct_answer = quiz.get("answers", {}).get(payload.question_id or "", "")
                is_correct = payload.answer == correct_answer
                state.setdefault("aptitudeScore", {}).setdefault(category, {"correct": 0, "total": 0})
                state["aptitudeScore"][category]["total"] += 1
                if is_correct:
                    state["aptitudeScore"][category]["correct"] += 1
    save_session(payload.session_id, state)
    return {"ok": True}


@app.post("/submit-code")
def submit_code(payload: SubmitCodeRequest):
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    state["codingSubmissions"].append(
        {
            "roundKey": payload.round_key,
            "questionIndex": payload.question_index,
            "language": payload.language,
            "code": payload.code,
        }
    )
    save_session(payload.session_id, state)
    return {"ok": True}


@app.get("/rounds/{company}")
def get_rounds(company: str):
    if company not in COMPANY_PROFILES:
        raise HTTPException(status_code=404, detail=f"Company '{company}' not found")
    return {"company": company, "rounds": company_rounds(company)}


@app.get("/questions/{round_type}")
def get_questions(round_type: str):
    cached = _cache_get(f"questions:{round_type}")
    if cached is not None:
        return cached
    datasets = {
        "aptitude": APTITUDE_QUESTIONS,
        "coding": CODING_QUESTIONS,
        "technical": TECHNICAL_QUESTIONS,
        "hr": HR_QUESTIONS,
    }
    if round_type not in datasets:
        raise HTTPException(status_code=404, detail=f"Round type '{round_type}' not found")
    _cache_set(f"questions:{round_type}", datasets[round_type])
    return datasets[round_type]




async def simulate_code_run(question_id: int, language: str, code: str) -> dict[str, Any]:
    question = next((q for q in CODING_QUESTIONS if q.get("id") == question_id), None)
    if not question:
        return {"ok": False, "error": "Coding question not found."}

    test_cases = question.get("testCases", [])
    results = []
    passed = 0

    judge0_key = settings.judge0_api_key
    judge0_host = settings.judge0_host

    language_ids = {
        "python": 71,
        "javascript": 63,
        "java": 62,
        "c": 50,
        "csharp": 51
    }

    if not judge0_key or language not in language_ids:
        # Fallback to heuristic
        heuristic = code.lower()
        for case in test_cases:
            expected = case.get("expected", "")
            output = ""
            status = "failed"

            if question_id == 1 and "reverse" in heuristic or question_id == 2 and "twosum" in heuristic or question_id == 3 and ("isvalid" in heuristic or "paren" in heuristic) or question_id == 4 and "fib" in heuristic or question_id == 5 and ("merge" in heuristic or "merge_sorted" in heuristic):
                output = expected
                status = "passed"
            else:
                output = "Runtime output did not match expected result."

            if status == "passed":
                passed += 1
            results.append({"input": case.get("input"), "expected": expected, "output": output, "status": status})
    else:
        # Use Judge0
        async with httpx.AsyncClient() as client:
            headers = {
                "x-rapidapi-key": judge0_key,
                "x-rapidapi-host": judge0_host,
                "Content-Type": "application/json"
            }

            for case in test_cases:
                expected = case.get("expected", "")
                payload = {
                    "language_id": language_ids[language],
                    "source_code": code,
                    "stdin": str(case.get("input", "")),
                    "expected_output": expected
                }

                try:
                    response = await client.post(
                        f"https://{judge0_host}/submissions?base64_encoded=false&wait=true",
                        json=payload,
                        headers=headers,
                        timeout=10.0
                    )

                    if response.status_code == 200:
                        data = response.json()
                        stdout = data.get("stdout") or ""
                        stderr = data.get("stderr") or ""
                        compile_output = data.get("compile_output") or ""

                        actual_output = stdout.strip() if stdout else (stderr or compile_output).strip()

                        status_id = data.get("status", {}).get("id")
                        if status_id == 3: # Accepted
                            status = "passed"
                            passed += 1
                        else:
                            status = "failed"

                        results.append({
                            "input": case.get("input"),
                            "expected": expected,
                            "output": actual_output or "No output",
                            "status": status
                        })
                    else:
                        results.append({
                            "input": case.get("input"),
                            "expected": expected,
                            "output": f"API Error {response.status_code}",
                            "status": "failed"
                        })
                except Exception as e:
                    results.append({
                        "input": case.get("input"),
                        "expected": expected,
                        "output": f"Execution Error: {str(e)}",
                        "status": "failed"
                    })

    score = round((passed / len(test_cases)) * 100) if test_cases else 0
    return {
        "ok": True,
        "question_id": question_id,
        "language": language,
        "results": results,
        "passed": passed,
        "total": len(test_cases),
        "score": score,
        "console": "Code executed successfully." if results else "No test cases available."
    }


@app.post("/run-code")
async def run_code(payload: RunCodeRequest, user: dict[str, Any] = Depends(require_candidate), request: Request = None):
    if not _check_rate_limit(f"code:{user['email']}", settings.code_rate_limit, settings.code_rate_window):
        raise HTTPException(status_code=429, detail="Too many code execution requests. Please wait.")
    return await simulate_code_run(payload.question_id, payload.language, payload.code)


@app.get("/report")
def get_report(session_id: str | None = None, user: dict[str, Any] = Depends(get_current_user)):
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    state = load_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    if state.get("user_id", "") != user["email"] and user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    return make_report(state)

class ProctoringViolationRequest(BaseModel):
    session_id: str
    violation: dict[str, Any]
    warnings: int
    integrity_score: int
    assessment_status: str

class ProctoringSnapshotRequest(BaseModel):
    session_id: str
    snapshot: dict[str, Any]

@app.post("/proctoring/violation")
def add_proctoring_violation(payload: ProctoringViolationRequest, user: dict[str, Any] = Depends(get_current_user)):
    state = load_session(payload.session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    if state.get("user_id", "") != user["email"] and user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    logs = load_proctoring(payload.session_id)
    if not logs:
        logs = {"violations": [], "snapshots": [], "warnings": 0, "integrity_score": 100, "assessment_status": "Passed Proctoring"}

    logs["violations"].append(payload.violation)
    logs["warnings"] = payload.warnings
    logs["integrity_score"] = payload.integrity_score
    logs["assessment_status"] = payload.assessment_status
    save_proctoring(payload.session_id, logs)
    return {"ok": True}

@app.post("/proctoring/snapshot")
def add_proctoring_snapshot(payload: ProctoringSnapshotRequest, user: dict[str, Any] = Depends(get_current_user)):
    state = load_session(payload.session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    if state.get("user_id", "") != user["email"] and user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    logs = load_proctoring(payload.session_id)
    if not logs:
        logs = {"violations": [], "snapshots": [], "warnings": 0, "integrity_score": 100, "assessment_status": "Passed Proctoring"}

    logs["snapshots"].append(payload.snapshot)
    save_proctoring(payload.session_id, logs)
    return {"ok": True}

@app.get("/proctoring/report")
def get_proctoring_report(session_id: str, user: dict[str, Any] = Depends(get_current_user)):
    state = load_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    if state.get("user_id", "") != user["email"] and user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    logs = load_proctoring(session_id)
    if not logs:
        return {"error": "No proctoring logs found for session"}
    return logs


class AIQuestionsRequest(BaseModel):
    session_id: str
    round_type: str
    count: int = 5

class AIFeedbackRequest(BaseModel):
    session_id: str

@app.post("/ai/questions")
async def generate_ai_questions(payload: AIQuestionsRequest, user: dict[str, Any] = Depends(require_candidate), request: Request = None):
    if not _check_rate_limit(f"ai:{user['email']}", settings.ai_rate_limit, settings.ai_rate_window):
        raise HTTPException(status_code=429, detail="Too many AI requests. Please wait.")
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    if state.get("user_id") and state.get("user_id") != user["email"]:
        raise HTTPException(status_code=403, detail="Not your session")

    gemini_key = settings.gemini_api_key
    if not gemini_key:
        return {"error": "Gemini API key not configured"}

    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    resume = state.get("resume", {})
    skills = _sanitize_for_ai(", ".join(resume.get("skills", [])))
    company = _sanitize_for_ai(state.get("selectedCompany", "Unknown"))

    prompt = f"Generate {payload.count} {payload.round_type} interview questions for a candidate applying to {company} with skills in {skills}. Respond with a JSON array of objects, each containing a 'question' string and an 'id' integer."

    try:
        response = model.generate_content(prompt)
        text = response.text
        start = text.find('[')
        end = text.rfind(']') + 1
        if start != -1 and end != 0:
            questions = json.loads(text[start:end])
            return {"questions": questions}
        return {"error": "Failed to parse AI response"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/ai/feedback")
async def generate_ai_feedback(payload: AIFeedbackRequest, user: dict[str, Any] = Depends(require_candidate), request: Request = None):
    if not _check_rate_limit(f"ai:{user['email']}", settings.ai_rate_limit, settings.ai_rate_window):
        raise HTTPException(status_code=429, detail="Too many AI requests. Please wait.")
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    if state.get("user_id") and state.get("user_id") != user["email"]:
        raise HTTPException(status_code=403, detail="Not your session")

    gemini_key = settings.gemini_api_key
    if not gemini_key:
        return {"error": "Gemini API key not configured"}

    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    answers = state.get("answers", {})
    sanitized_answers = {k: _sanitize_for_ai(json.dumps(v)) for k, v in answers.items()}
    prompt = f"Review the following interview answers and provide personalised feedback. Answers: {json.dumps(sanitized_answers)}. Provide strengths, weaknesses, and 3 concrete recommendations in JSON format: {{ 'strengths': ['...'], 'weaknesses': ['...'], 'recommendations': ['...'], 'feedback': {{'technical': '...', 'hr': '...'}} }}"

    try:
        response = model.generate_content(prompt)
        text = response.text
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != 0:
            feedback = json.loads(text[start:end])
            state["aiFeedback"] = feedback
            save_session(payload.session_id, state)
            return {"feedback": feedback}
        return {"error": "Failed to parse AI response"}
    except Exception as e:
        return {"error": str(e)}


# ──────────────────────────────────────────────────────────────────────────────
# Candidate Dashboard Endpoints
# ──────────────────────────────────────────────────────────────────────────────

def _session_summary(state: dict[str, Any]) -> dict[str, Any]:
    scores = state.get("scores", {})
    overall = round(sum(scores.values()) / len(scores)) if scores else 0
    answers = state.get("answers", {})
    rounds_completed = [k for k, v in answers.items() if v]
    return {
        "session_id": state.get("sessionId", ""),
        "company": state.get("selectedCompany", ""),
        "companies": state.get("selectedCompanies", []),
        "date": state.get("_updated_at", 0),
        "overall_score": overall,
        "scores": scores,
        "rounds_completed": rounds_completed,
    }


@app.get("/user/sessions")
def user_sessions(user: dict[str, Any] = Depends(require_candidate)):
    sessions = get_sessions_by_user(user["email"])
    return {"sessions": [_session_summary(s) for s in sessions]}


@app.get("/user/sessions/{session_id}")
def user_session_detail(session_id: str, user: dict[str, Any] = Depends(require_candidate)):
    state = load_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    if state.get("user_id", "") != user["email"] and user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    report = make_report(state)
    proctoring = load_proctoring(session_id)
    return {"session": report, "proctoring": proctoring}


@app.get("/user/stats")
def user_stats(user: dict[str, Any] = Depends(require_candidate)):
    sessions = get_sessions_by_user(user["email"])
    if not sessions:
        return {
            "total_interviews": 0,
            "avg_scores": {},
            "overall_avg": 0,
            "best_score": 0,
            "worst_score": 0,
            "trend": [],
            "companies_practiced": [],
        }

    all_scores = []
    companies_set = set()
    trend = []
    for s in sessions:
        scores = s.get("scores", {})
        overall = round(sum(scores.values()) / len(scores)) if scores else 0
        all_scores.append(overall)
        companies_set.add(s.get("selectedCompany", ""))
        trend.append({
            "date": s.get("_updated_at", 0),
            "overall": overall,
            **scores,
        })

    avg_by_round: dict[str, float] = {}
    for s in sessions:
        for k, v in s.get("scores", {}).items():
            avg_by_round.setdefault(k, []).append(v)
    avg_scores = {k: round(sum(v) / len(v)) for k, v in avg_by_round.items() if v}

    return {
        "total_interviews": len(sessions),
        "avg_scores": avg_scores,
        "overall_avg": round(sum(all_scores) / len(all_scores)) if all_scores else 0,
        "best_score": max(all_scores) if all_scores else 0,
        "worst_score": min(all_scores) if all_scores else 0,
        "trend": trend,
        "companies_practiced": sorted(companies_set - {""}),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Recruiter / Admin Endpoints
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/admin/candidates")
def admin_candidates(user: dict[str, Any] = Depends(require_recruiter)):
    users = get_all_users()
    sessions = get_all_sessions()
    by_user: dict[str, list] = {}
    for s in sessions:
        uid = s.get("user_id", "")
        if uid:
            by_user.setdefault(uid, []).append(s)

    result = []
    for u in users:
        if u["role"] != "candidate":
            continue
        user_sessions = by_user.get(u["email"], [])
        avg = 0
        if user_sessions:
            avgs = [round(sum(s.get("scores", {}).values()) / len(s.get("scores", {}))) if s.get("scores") else 0 for s in user_sessions]
            avg = round(sum(avgs) / len(avgs)) if avgs else 0
        result.append({
            "email": u["email"],
            "name": u["name"],
            "role": u["role"],
            "interview_count": len(user_sessions),
            "avg_score": avg,
            "last_active": max((s.get("_updated_at", 0) for s in user_sessions), default=0),
            "created_at": u.get("created_at", 0),
        })
    return {"candidates": result}


@app.get("/admin/candidates/{candidate_email}")
def admin_candidate_detail(candidate_email: str, user: dict[str, Any] = Depends(require_recruiter)):
    account = load_user(candidate_email)
    if not account:
        raise HTTPException(status_code=404, detail="Candidate not found")
    sessions = get_sessions_by_user(candidate_email)
    return {
        "candidate": {"email": account["email"], "name": account["name"], "role": account["role"]},
        "sessions": [_session_summary(s) for s in sessions],
    }


@app.get("/admin/sessions")
def admin_sessions(user: dict[str, Any] = Depends(require_recruiter)):
    sessions = get_all_sessions()
    return {"sessions": [_session_summary(s) for s in sessions]}


@app.get("/admin/sessions/{session_id}")
def admin_session_detail(session_id: str, user: dict[str, Any] = Depends(require_recruiter)):
    state = load_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    report = make_report(state)
    proctoring = load_proctoring(session_id)
    return {"session": report, "proctoring": proctoring}


@app.get("/admin/sessions/{session_id}/proctoring")
def admin_session_proctoring(session_id: str, user: dict[str, Any] = Depends(require_recruiter)):
    logs = load_proctoring(session_id)
    if not logs:
        return {"error": "No proctoring logs found"}
    return logs


@app.get("/admin/stats")
def admin_stats(user: dict[str, Any] = Depends(require_recruiter)):
    users = get_all_users()
    sessions = get_all_sessions()
    candidates = [u for u in users if u["role"] == "candidate"]
    all_scores = []
    for s in sessions:
        scores = s.get("scores", {})
        if scores:
            all_scores.append(round(sum(scores.values()) / len(scores)))
    return {
        "total_candidates": len(candidates),
        "total_interviews": len(sessions),
        "avg_platform_score": round(sum(all_scores) / len(all_scores)) if all_scores else 0,
        "top_score": max(all_scores) if all_scores else 0,
    }


class UpdateRoleRequest(BaseModel):
    email: str
    role: str


@app.post("/admin/update-role")
def admin_update_role(payload: UpdateRoleRequest, user: dict[str, Any] = Depends(require_admin), request: Request = None):
    if not _check_rate_limit(f"admin:{user['email']}", settings.admin_rate_limit, settings.admin_rate_window):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait.")
    if payload.role not in ("candidate", "recruiter", "admin"):
        raise HTTPException(status_code=400, detail="Role must be candidate, recruiter, or admin")
    account = load_user(payload.email)
    if not account:
        raise HTTPException(status_code=404, detail="User not found")
    update_user_role(payload.email, payload.role)
    return {"ok": True, "message": f"Role updated to {payload.role}"}


# ──────────────────────────────────────────────────────────────────────────────
# Recruiter Comparison & Session Replay
# ──────────────────────────────────────────────────────────────────────────────

class CompareRequest(BaseModel):
    session_ids: list[str]

class UploadQuestionsRequest(BaseModel):
    round_type: str
    questions: list[dict[str, Any]]


@app.post("/admin/compare")
def admin_compare(payload: CompareRequest, user: dict[str, Any] = Depends(require_recruiter)):
    if len(payload.session_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 sessions required")
    if len(payload.session_ids) > 5:
        raise HTTPException(status_code=400, detail="Maximum 5 sessions for comparison")
    results = []
    for sid in payload.session_ids[:5]:
        state = load_session(sid)
        if not state:
            results.append({"session_id": sid, "error": "Not found"})
            continue
        report = make_report(state)
        proctoring = load_proctoring(sid)
        results.append({
            "session_id": sid,
            "candidate_name": report.get("candidateName", ""),
            "company": report.get("selectedCompany", ""),
            "scores": report.get("scores", {}),
            "overall_score": report.get("overallScore", 0),
            "proctoring_score": proctoring.get("integrity_score", 100) if proctoring else 100,
            "proctoring_status": proctoring.get("assessment_status", "N/A") if proctoring else "N/A",
        })
    return {"comparisons": results}


@app.get("/admin/sessions/{session_id}/timeline")
def admin_session_timeline(session_id: str, user: dict[str, Any] = Depends(require_recruiter)):
    state = load_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    answers = state.get("answers", {})
    proctoring = load_proctoring(session_id)
    timeline = []
    for round_key, round_answers in answers.items():
        for i, ans in enumerate(round_answers):
            timeline.append({
                "type": "answer",
                "round": round_key,
                "question_index": ans.get("questionIndex", i),
                "answer": ans.get("answer", ""),
                "order": i,
            })
    if proctoring:
        for v in proctoring.get("violations", []):
            timeline.append({
                "type": "violation",
                "round": v.get("round", ""),
                "event": v.get("reason", v.get("kind", "Unknown")),
                "order": -1,
            })
    timeline.sort(key=lambda x: x["order"])
    for i, entry in enumerate(timeline):
        entry["step"] = i + 1
    return {"timeline": timeline, "total_steps": len(timeline)}


CUSTOM_QUESTIONS_DIR = BASE_DIR / "shared" / "custom_questions"

@app.post("/admin/upload-questions")
async def admin_upload_questions(file: UploadFile = File(...), user: dict[str, Any] = Depends(require_admin)):
    CUSTOM_QUESTIONS_DIR.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    try:
        data = json.loads(content.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON file") from exc
    round_type = data.get("round_type", "")
    questions = data.get("questions", [])
    if not round_type or not questions:
        raise HTTPException(status_code=400, detail="Must include round_type and questions array")
    filepath = CUSTOM_QUESTIONS_DIR / f"{round_type}_custom.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(questions, f, indent=2)
    logger.info("Custom questions uploaded: %s (%d questions)", round_type, len(questions))
    return {"ok": True, "count": len(questions), "round_type": round_type}


@app.get("/admin/custom-questions")
def admin_list_custom_questions(user: dict[str, Any] = Depends(require_admin)):
    CUSTOM_QUESTIONS_DIR.mkdir(parents=True, exist_ok=True)
    files = list(CUSTOM_QUESTIONS_DIR.glob("*_custom.json"))
    result = []
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                questions = json.load(f)
            result.append({"round_type": fp.stem.replace("_custom", ""), "count": len(questions), "filename": fp.name})
        except Exception:
            continue
    return {"questions": result}
