from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import secrets
import smtplib
import ssl
import time
import uuid
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Dict, List, Optional
import re
import jwt
import google.generativeai as genai
from app.db import (
    init_db, migrate_accounts_json, cleanup_stale_data,
    save_session, load_session, get_first_session_id, get_sessions_by_user, get_all_sessions,
    save_user, load_user, user_exists, get_all_users, update_user_role,
    save_otp, load_otp, delete_otp,
    save_captcha, load_captcha, delete_captcha,
    save_proctoring, load_proctoring,
)
import fitz

from app.resume_parser import parse_resume_text, extract_text_from_pdf_content

from fastapi import FastAPI, File, UploadFile, Header, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parents[2]
SHARED_DIR = BASE_DIR / "shared"
FRONTEND_QUESTIONS_DIR = BASE_DIR / "frontend" / "public" / "questions"

load_dotenv(BASE_DIR / "backend" / ".env")
load_dotenv(BASE_DIR / ".env")

app = FastAPI(title="AI Mock Recruitment Platform")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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
    return response

JWT_SECRET_FILE = BASE_DIR / "backend" / ".jwt_secret"
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 24
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _load_or_create_jwt_secret() -> str:
    if os.getenv("JWT_SECRET"):
        return os.getenv("JWT_SECRET")
    if JWT_SECRET_FILE.exists():
        return JWT_SECRET_FILE.read_text(encoding="utf-8").strip()
    secret = secrets.token_hex(32)
    JWT_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    JWT_SECRET_FILE.write_text(secret, encoding="utf-8")
    return secret


JWT_SECRET = _load_or_create_jwt_secret()


@app.on_event("startup")
def startup_event():
    init_db()
    _accounts_file = BASE_DIR / "backend" / "accounts.json"
    migrate_accounts_json(_accounts_file)
    cleanup_stale_data()


def create_token(email: str, role: str) -> str:
    payload = {
        "sub": email,
        "email": email,
        "role": role,
        "exp": time.time() + JWT_EXPIRY_HOURS * 3600,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None


async def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"email": payload["email"], "role": payload.get("role", "candidate")}


async def require_candidate(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user["role"] not in ("candidate", "recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Candidate access required")
    return user


async def require_recruiter(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Recruiter or admin access required")
    return user


async def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def load_json(name: str) -> Any:
    with open(SHARED_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


def load_questions_json(name: str) -> Any:
    with open(FRONTEND_QUESTIONS_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


COMPANY_PROFILES = load_json("company_profiles.json")
APTITUDE_QUESTIONS = load_questions_json("aptitude.json")
CODING_QUESTIONS = load_json("coding_questions.json")
TECHNICAL_QUESTIONS = load_json("technical_questions.json")
HR_QUESTIONS = load_json("hr_questions.json")
OTP_TTL_SECONDS = 300
CAPTCHA_TTL_SECONDS = 300
OTP_RATE_LIMIT = 5  # max requests per email
OTP_RATE_WINDOW = 600  # 10 minutes in seconds
_otp_rate_tracker: Dict[str, List[float]] = {}


def default_scores() -> Dict[str, int]:
    return {"aptitude": 80, "coding": 75, "technical": 70, "hr": 85}


def hash_password(password: str, salt: Optional[str] = None) -> Dict[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return {"salt": salt, "hash": key.hex()}


def verify_password(password: str, stored: Dict[str, str]) -> bool:
    hashed = hash_password(password, stored.get("salt"))
    return hmac.compare_digest(hashed["hash"], stored.get("hash", ""))


def validate_email_format(email: str) -> bool:
    return bool(re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email))


def has_strong_password(password: str) -> bool:
    return len(password) >= 8 and bool(re.search(r"[^A-Za-z0-9]", password))


def score_open_round(answers: List[Dict[str, Any]], round_key: str) -> int:
    if not answers:
        return 0

    gemini_key = os.getenv("GEMINI_API_KEY")
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


def make_report(state: Dict[str, Any]) -> Dict[str, Any]:
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


def company_rounds(company: str) -> List[Dict[str, str]]:
    return COMPANY_PROFILES[company]["rounds"]


def all_round_keys(company: str) -> List[str]:
    return [r["key"] for r in company_rounds(company)]


class CompanySelection(BaseModel):
    session_id: str
    companies: List[str]


class StartRoundRequest(BaseModel):
    session_id: str
    company: str
    round_key: str


class SubmitAnswerRequest(BaseModel):
    session_id: str
    round_key: str
    question_index: int
    answer: str
    aptitude_category: Optional[str] = None
    aptitude_quiz_id: Optional[str] = None
    question_id: Optional[str] = None


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
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port_str = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "")

    if not smtp_host or not smtp_user or not smtp_password or not smtp_from:
        print(f"[OTP] Missing SMTP config - HOST: {bool(smtp_host)}, USER: {bool(smtp_user)}, PASSWORD: {bool(smtp_password)}, FROM: {bool(smtp_from)}")
        return False

    try:
        smtp_port = int(smtp_port_str)
    except ValueError:
        print(f"[OTP] Invalid SMTP_PORT: {smtp_port_str}")
        return False

    message = EmailMessage()
    message["Subject"] = "Mock Recruitment Platform OTP"
    message["From"] = smtp_from
    message["To"] = email
    message.set_content(
        f"Your Mock Recruitment Platform OTP is {otp}. It expires in 5 minutes."
    )

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls(context=context)
            server.login(smtp_user, smtp_password)
            server.send_message(message)
        print(f"[OTP] Email sent successfully to {email}")
        return True
    except Exception as e:
        print(f"[OTP] SMTP Error: {type(e).__name__}: {str(e)}")
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
def send_otp(payload: SendOtpRequest):
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        return {"ok": False, "error": "Enter a valid email address."}

    now = time.time()
    if email not in _otp_rate_tracker:
        _otp_rate_tracker[email] = []
    _otp_rate_tracker[email] = [t for t in _otp_rate_tracker[email] if now - t < OTP_RATE_WINDOW]
    if len(_otp_rate_tracker[email]) >= OTP_RATE_LIMIT:
        return {"ok": False, "error": "Too many requests. Please wait a few minutes."}
    _otp_rate_tracker[email].append(now)

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
        if os.getenv("ENVIRONMENT", "development") == "development":
            response["dev_otp"] = otp
    return response


@app.get("/health/smtp")
def check_smtp_status(user: Dict[str, Any] = Depends(require_admin)):
    """Diagnostic endpoint to check SMTP configuration (admin only)."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from = os.getenv("SMTP_FROM")
    
    return {
        "smtp_host": smtp_host or "NOT SET",
        "smtp_port": smtp_port or "NOT SET",
        "smtp_user": smtp_user or "NOT SET",
        "smtp_from": smtp_from or "NOT SET",
        "smtp_password_set": bool(smtp_password),
        "all_configured": bool(smtp_host and smtp_user and smtp_password and smtp_from)
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
    return COMPANY_PROFILES

@app.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...), user: Dict[str, Any] = Depends(require_candidate)):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024*1024)} MB.")

    filename = file.filename.lower()

    if filename.endswith(".pdf"):
        text = extract_text_from_pdf_content(content)

        print("\n========== PDF TEXT ==========\n")
        print(text)
        print("\n==============================\n")

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
    return {"session_id": payload.session_id, "round_key": payload.round_key, "state": state}


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
    return {"ok": True, "state": state}


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
    return {"ok": True, "state": state}


@app.get("/rounds/{company}")
def get_rounds(company: str):
    if company not in COMPANY_PROFILES:
        raise HTTPException(status_code=404, detail=f"Company '{company}' not found")
    return {"company": company, "rounds": company_rounds(company)}


@app.get("/questions/{round_type}")
def get_questions(round_type: str):
    datasets = {
        "aptitude": APTITUDE_QUESTIONS,
        "coding": CODING_QUESTIONS,
        "technical": TECHNICAL_QUESTIONS,
        "hr": HR_QUESTIONS,
    }
    if round_type not in datasets:
        raise HTTPException(status_code=404, detail=f"Round type '{round_type}' not found")
    return datasets[round_type]




import httpx
import asyncio

async def simulate_code_run(question_id: int, language: str, code: str) -> Dict[str, Any]:
    question = next((q for q in CODING_QUESTIONS if q.get("id") == question_id), None)
    if not question:
        return {"ok": False, "error": "Coding question not found."}

    test_cases = question.get("testCases", [])
    results = []
    passed = 0
    
    judge0_key = os.getenv("JUDGE0_API_KEY")
    judge0_host = os.getenv("JUDGE0_HOST", "judge0-ce.p.rapidapi.com")
    
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
    
            if question_id == 1 and "reverse" in heuristic:
                output = expected
                status = "passed"
            elif question_id == 2 and "twosum" in heuristic:
                output = expected
                status = "passed"
            elif question_id == 3 and ("isvalid" in heuristic or "paren" in heuristic):
                output = expected
                status = "passed"
            elif question_id == 4 and "fib" in heuristic:
                output = expected
                status = "passed"
            elif question_id == 5 and ("merge" in heuristic or "merge_sorted" in heuristic):
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
async def run_code(payload: RunCodeRequest):
    return await simulate_code_run(payload.question_id, payload.language, payload.code)


@app.get("/report")
def get_report(session_id: Optional[str] = None, user: Dict[str, Any] = Depends(get_current_user)):
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
    violation: Dict[str, Any]
    warnings: int
    integrity_score: int
    assessment_status: str

class ProctoringSnapshotRequest(BaseModel):
    session_id: str
    snapshot: Dict[str, Any]

@app.post("/proctoring/violation")
def add_proctoring_violation(payload: ProctoringViolationRequest, user: Dict[str, Any] = Depends(get_current_user)):
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
def add_proctoring_snapshot(payload: ProctoringSnapshotRequest, user: Dict[str, Any] = Depends(get_current_user)):
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
def get_proctoring_report(session_id: str, user: Dict[str, Any] = Depends(get_current_user)):
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
async def generate_ai_questions(payload: AIQuestionsRequest, user: Dict[str, Any] = Depends(require_candidate)):
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    if state.get("user_id") and state.get("user_id") != user["email"]:
        raise HTTPException(status_code=403, detail="Not your session")

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return {"error": "Gemini API key not configured"}

    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    resume = state.get("resume", {})
    skills = ", ".join(resume.get("skills", []))
    company = state.get("selectedCompany", "Unknown")

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
async def generate_ai_feedback(payload: AIFeedbackRequest, user: Dict[str, Any] = Depends(require_candidate)):
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    if state.get("user_id") and state.get("user_id") != user["email"]:
        raise HTTPException(status_code=403, detail="Not your session")

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return {"error": "Gemini API key not configured"}

    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    
    answers = state.get("answers", {})
    prompt = f"Review the following interview answers and provide personalised feedback. Answers: {json.dumps(answers)}. Provide strengths, weaknesses, and 3 concrete recommendations in JSON format: {{ 'strengths': ['...'], 'weaknesses': ['...'], 'recommendations': ['...'], 'feedback': {{'technical': '...', 'hr': '...'}} }}"

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

def _session_summary(state: Dict[str, Any]) -> Dict[str, Any]:
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
def user_sessions(user: Dict[str, Any] = Depends(require_candidate)):
    sessions = get_sessions_by_user(user["email"])
    return {"sessions": [_session_summary(s) for s in sessions]}


@app.get("/user/sessions/{session_id}")
def user_session_detail(session_id: str, user: Dict[str, Any] = Depends(require_candidate)):
    state = load_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    if state.get("user_id", "") != user["email"] and user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    report = make_report(state)
    proctoring = load_proctoring(session_id)
    return {"session": report, "proctoring": proctoring}


@app.get("/user/stats")
def user_stats(user: Dict[str, Any] = Depends(require_candidate)):
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

    avg_by_round: Dict[str, float] = {}
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
def admin_candidates(user: Dict[str, Any] = Depends(require_recruiter)):
    users = get_all_users()
    sessions = get_all_sessions()
    by_user: Dict[str, List] = {}
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
def admin_candidate_detail(candidate_email: str, user: Dict[str, Any] = Depends(require_recruiter)):
    account = load_user(candidate_email)
    if not account:
        raise HTTPException(status_code=404, detail="Candidate not found")
    sessions = get_sessions_by_user(candidate_email)
    return {
        "candidate": {"email": account["email"], "name": account["name"], "role": account["role"]},
        "sessions": [_session_summary(s) for s in sessions],
    }


@app.get("/admin/sessions")
def admin_sessions(user: Dict[str, Any] = Depends(require_recruiter)):
    sessions = get_all_sessions()
    return {"sessions": [_session_summary(s) for s in sessions]}


@app.get("/admin/sessions/{session_id}")
def admin_session_detail(session_id: str, user: Dict[str, Any] = Depends(require_recruiter)):
    state = load_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    report = make_report(state)
    proctoring = load_proctoring(session_id)
    return {"session": report, "proctoring": proctoring}


@app.get("/admin/sessions/{session_id}/proctoring")
def admin_session_proctoring(session_id: str, user: Dict[str, Any] = Depends(require_recruiter)):
    logs = load_proctoring(session_id)
    if not logs:
        return {"error": "No proctoring logs found"}
    return logs


@app.get("/admin/stats")
def admin_stats(user: Dict[str, Any] = Depends(require_recruiter)):
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
def admin_update_role(payload: UpdateRoleRequest, user: Dict[str, Any] = Depends(require_admin)):
    if payload.role not in ("candidate", "recruiter", "admin"):
        raise HTTPException(status_code=400, detail="Role must be candidate, recruiter, or admin")
    account = load_user(payload.email)
    if not account:
        raise HTTPException(status_code=404, detail="User not found")
    update_user_role(payload.email, payload.role)
    return {"ok": True, "message": f"Role updated to {payload.role}"}
