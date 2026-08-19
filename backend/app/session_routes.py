from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.auth_routes import get_current_user, require_admin, require_candidate, require_recruiter
from app.code_executor import execute_local, normalize_output
from app.config import settings
from app.db import (
    cache_get,
    cache_set,
    check_rate_limit,
    get_all_sessions,
    get_all_users,
    get_sessions_by_user,
    load_proctoring,
    load_session,
    load_user,
    save_proctoring,
    save_session,
    update_user_role,
)
from app.helpers import default_scores, sanitize_for_ai
from app.resume_parser import extract_text_from_pdf_content, parse_resume_text

router = APIRouter()

SHARED_DIR = settings.shared_dir_path
FRONTEND_QUESTIONS_DIR = settings.frontend_questions_dir_path


def load_json(name: str) -> Any:
    path = SHARED_DIR / name
    if not path.exists():
        raise RuntimeError(f"Required data file not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_questions_json(name: str) -> Any:
    path = FRONTEND_QUESTIONS_DIR / name
    if not path.exists():
        raise RuntimeError(f"Required questions file not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


COMPANY_PROFILES = load_json("company_profiles.json")
APTITUDE_QUESTIONS = load_questions_json("aptitude.json")
CODING_QUESTIONS = load_json("coding_questions.json")
TECHNICAL_QUESTIONS = load_json("technical_questions.json")
HR_QUESTIONS = load_json("hr_questions.json")

MAX_UPLOAD_BYTES = settings.max_upload_bytes
OTP_TTL_SECONDS = settings.otp_ttl_seconds
CAPTCHA_TTL_SECONDS = settings.captcha_ttl_seconds
OTP_RATE_LIMIT = settings.otp_rate_limit
OTP_RATE_WINDOW = settings.otp_rate_window


def _check_rate_limit(key: str, limit: int, window: int) -> bool:
    return check_rate_limit(key, limit, window)


def _cache_get(key: str, ttl: int = 300) -> Any:
    return cache_get(key, ttl)


def _cache_set(key: str, data: Any, ttl: int = 300) -> None:
    cache_set(key, data, ttl)


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


class RunCodeRequest(BaseModel):
    question_id: int
    language: str
    code: str


class ProctoringViolationRequest(BaseModel):
    session_id: str
    violation: dict[str, Any]
    warnings: int
    integrity_score: int
    assessment_status: str


class ProctoringSnapshotRequest(BaseModel):
    session_id: str
    snapshot: dict[str, Any]


class AIQuestionsRequest(BaseModel):
    session_id: str
    round_type: str
    count: int = 5


class AIFeedbackRequest(BaseModel):
    session_id: str


class UpdateRoleRequest(BaseModel):
    email: str
    role: str


class CompareRequest(BaseModel):
    session_ids: list[str]


class UploadQuestionsRequest(BaseModel):
    round_type: str
    questions: list[dict[str, Any]]


def score_open_round(answers: list[dict[str, Any]], round_key: str) -> int:
    if not answers:
        return 0

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

    account_name = ""
    user_id = state.get("user_id", "")
    if user_id:
        account = load_user(user_id)
        if account:
            account_name = account.get("name", "")

    return {
        "candidateName": account_name or state.get("resume", {}).get("name", "Candidate"),
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


@router.get("/companies")
def get_companies():
    cached = _cache_get("companies")
    if cached is not None:
        return cached
    _cache_set("companies", COMPANY_PROFILES)
    return COMPANY_PROFILES


@router.post("/upload-resume")
async def upload_resume(file: UploadFile = File(...), user: dict[str, Any] = Depends(require_candidate)):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum size is {MAX_UPLOAD_BYTES // (1024*1024)} MB.")

    filename = file.filename.lower()

    if filename.endswith(".pdf"):
        try:
            text = extract_text_from_pdf_content(content)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    elif filename.endswith(".txt"):
        text = content.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(status_code=400, detail="Only PDF and TXT files are supported")

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


@router.post("/select-company")
def select_company(payload: CompanySelection, user: dict[str, Any] = Depends(require_candidate)):
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    if state.get("user_id") and state.get("user_id") != user["email"] and user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Not your session")

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

    return {"session_id": payload.session_id, "companies": payload.companies, "rounds": rounds}


@router.post("/start-round")
def start_round(payload: StartRoundRequest):
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    state["currentRound"] = payload.round_key
    state["currentQuestion"] = 0
    save_session(payload.session_id, state)
    return {"session_id": payload.session_id, "round_key": payload.round_key}


@router.post("/submit-answer")
def submit_answer(payload: SubmitAnswerRequest):
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    state["answers"].setdefault(payload.round_key, [])
    state["answers"][payload.round_key].append({"questionIndex": payload.question_index, "answer": payload.answer})
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
                qid = payload.question_id
                correct_answer = quiz.get("answers", {}).get(qid, quiz.get("answers", {}).get(str(qid), ""))
                is_correct = payload.answer == correct_answer
                state.setdefault("aptitudeScore", {}).setdefault(category, {"correct": 0, "total": 0})
                state["aptitudeScore"][category]["total"] += 1
                if is_correct:
                    state["aptitudeScore"][category]["correct"] += 1
    save_session(payload.session_id, state)
    return {"ok": True}


@router.post("/submit-code")
async def submit_code(payload: SubmitCodeRequest, user: dict[str, Any] = Depends(require_candidate)):
    if not _check_rate_limit(f"code:{user['email']}", settings.code_rate_limit, settings.code_rate_window):
        raise HTTPException(status_code=429, detail="Too many code execution requests. Please wait.")
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    if state.get("user_id", "") != user["email"] and user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Not your session")

    if payload.code == "[Skipped]":
        run = {"ok": True, "score": 0, "results": []}
    else:
        try:
            question = CODING_QUESTIONS[payload.question_index]
        except (IndexError, TypeError):
            question = None
        question_id = question.get("id") if question else payload.question_index + 1
        run = await simulate_code_run(question_id, payload.language, payload.code)

    state["codingSubmissions"].append({
        "roundKey": payload.round_key,
        "questionIndex": payload.question_index,
        "language": payload.language,
        "code": payload.code,
        "score": run.get("score", 0),
        "results": run.get("results", []),
    })

    graded = [s for s in state["codingSubmissions"] if s.get("code") != "[Skipped]"]
    if graded:
        state.setdefault("scores", default_scores())["coding"] = round(
            sum(s.get("score", 0) for s in graded) / len(graded)
        )

    save_session(payload.session_id, state)
    return {"ok": True, "score": run.get("score", 0), "results": run.get("results", [])}


@router.get("/rounds/{company}")
def get_rounds(company: str):
    if company not in COMPANY_PROFILES:
        raise HTTPException(status_code=404, detail=f"Company '{company}' not found")
    return {"company": company, "rounds": company_rounds(company)}


@router.get("/questions/{round_type}")
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


async def _run_local_test_cases(language: str, code: str, test_cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Run every test case through the local execution engine."""
    results: list[dict[str, Any]] = []
    passed = 0
    for case in test_cases:
        expected = case.get("expected", "")
        result = await execute_local(language, code, str(case.get("input", "")))

        if result.get("ok") is False and result.get("error"):
            output = result["error"]
            status = "failed"
        elif result.get("missing_runtime"):
            output = result.get("error") or f"Local runtime not available for {language}"
            status = "failed"
        elif result.get("timed_out"):
            output = result.get("stderr") or "Execution timed out."
            status = "failed"
        elif result.get("stderr"):
            output = result["stderr"]
            status = "failed"
        else:
            output = result.get("stdout", "")
            if normalize_output(output) == normalize_output(expected):
                status = "passed"
                passed += 1
            else:
                status = "failed"

        results.append({"input": case.get("input"), "expected": expected, "output": output, "status": status})
    return results, passed


async def _run_judge0_test_cases(
    language: str, code: str, test_cases: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int, bool]:
    """Run every test case through the Judge0 API.

    Returns ``(results, passed, api_usable)`` where ``api_usable`` is False if
    the Judge0 service itself failed (auth, rate limit, network), so the caller
    can fall back to local execution.
    """
    results: list[dict[str, Any]] = []
    passed = 0
    api_usable = True

    judge0_host = settings.judge0_host
    language_ids = settings.judge0_language_ids
    headers = {
        "x-rapidapi-key": settings.judge0_api_key,
        "x-rapidapi-host": judge0_host,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient() as client:
        for case in test_cases:
            expected = case.get("expected", "")
            payload = {
                "language_id": language_ids[language],
                "source_code": code,
                "stdin": str(case.get("input", "")),
                "expected_output": expected,
            }

            try:
                response = await client.post(
                    f"https://{judge0_host}/submissions?base64_encoded=false&wait=true",
                    json=payload,
                    headers=headers,
                    timeout=settings.judge0_timeout,
                )
            except Exception as e:
                api_usable = False
                results.append({
                    "input": case.get("input"),
                    "expected": expected,
                    "output": f"Judge0 unavailable, falling back to local execution. ({e})",
                    "status": "failed",
                })
                continue

            if response.status_code != 200:
                api_usable = False
                results.append({
                    "input": case.get("input"),
                    "expected": expected,
                    "output": f"Judge0 API error {response.status_code}, falling back to local execution.",
                    "status": "failed",
                })
                continue

            data = response.json()
            stdout = data.get("stdout") or ""
            stderr = data.get("stderr") or ""
            compile_output = data.get("compile_output") or ""
            actual_output = stdout.strip() if stdout else (stderr or compile_output).strip()

            status_id = data.get("status", {}).get("id")
            if status_id == 3:
                status = "passed"
                passed += 1
            else:
                status = "failed"

            results.append({
                "input": case.get("input"),
                "expected": expected,
                "output": actual_output or "No output",
                "status": status,
            })

    return results, passed, api_usable


async def simulate_code_run(question_id: int, language: str, code: str) -> dict[str, Any]:
    question = next((q for q in CODING_QUESTIONS if q.get("id") == question_id), None)
    if not question:
        return {"ok": False, "error": "Coding question not found."}

    test_cases = question.get("testCases", [])

    use_judge0 = bool(settings.judge0_api_key) and language in settings.judge0_language_ids
    if use_judge0:
        results, passed, api_usable = await _run_judge0_test_cases(language, code, test_cases)
        if not api_usable:
            results, passed = await _run_local_test_cases(language, code, test_cases)
    else:
        results, passed = await _run_local_test_cases(language, code, test_cases)

    score = round((passed / len(test_cases)) * 100) if test_cases else 0
    return {
        "ok": True,
        "question_id": question_id,
        "language": language,
        "results": results,
        "passed": passed,
        "total": len(test_cases),
        "score": score,
        "console": "Code executed successfully." if results else "No test cases available.",
    }


@router.post("/run-code")
async def run_code(payload: RunCodeRequest, user: dict[str, Any] = Depends(require_candidate)):
    if not _check_rate_limit(f"code:{user['email']}", settings.code_rate_limit, settings.code_rate_window):
        raise HTTPException(status_code=429, detail="Too many code execution requests. Please wait.")
    return await simulate_code_run(payload.question_id, payload.language, payload.code)


@router.get("/report")
def get_report(session_id: str | None = None, user: dict[str, Any] = Depends(get_current_user)):
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    state = load_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    if state.get("user_id", "") != user["email"] and user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    return make_report(state)


@router.post("/proctoring/violation")
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


@router.post("/proctoring/snapshot")
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


@router.get("/proctoring/report")
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


@router.post("/ai/questions")
async def generate_ai_questions(payload: AIQuestionsRequest, user: dict[str, Any] = Depends(require_candidate)):
    if not _check_rate_limit(f"ai:{user['email']}", settings.ai_rate_limit, settings.ai_rate_window):
        raise HTTPException(status_code=429, detail="Too many AI requests. Please wait.")
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    if state.get("user_id", "") != user["email"] and user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Not your session")

    resume = state.get("resume", {})
    skills = sanitize_for_ai(", ".join(resume.get("skills", [])))
    company = sanitize_for_ai(state.get("selectedCompany", "Unknown"))
    question_count = max(1, min(int(payload.count), 20))

    # Serve repeat requests instantly from the DB-backed cache.
    cache_key = f"ai_q:{payload.round_type}:{company}:{skills[:80]}:{question_count}"
    cached = cache_get(cache_key)
    if cached is not None:
        return {"questions": cached, "cached": True}

    prompt = (
        f"Generate exactly {question_count} {payload.round_type} interview questions "
        f"for a candidate applying to {company} with skills in {skills}. "
        "Respond with a JSON array of objects, each containing a 'question' string and an 'id' integer."
    )

    try:
        from app.ai_interviewer.llm_providers import get_llm_registry

        result = await get_llm_registry().generate_json(
            "You are an expert technical interviewer. Respond with valid JSON only.",
            prompt,
        )
        if isinstance(result, dict) and "questions" in result:
            questions = result["questions"]
        elif isinstance(result, list):
            questions = result
        elif isinstance(result, dict) and any(isinstance(v, list) for v in result.values()):
            questions = next(v for v in result.values() if isinstance(v, list))
        else:
            questions = []
        if questions:
            cache_set(cache_key, questions, ttl=3600)
        return {"questions": questions}
    except Exception as e:
        return {"error": str(e)}


@router.post("/ai/feedback")
async def generate_ai_feedback(payload: AIFeedbackRequest, user: dict[str, Any] = Depends(require_candidate)):
    if not _check_rate_limit(f"ai:{user['email']}", settings.ai_rate_limit, settings.ai_rate_window):
        raise HTTPException(status_code=429, detail="Too many AI requests. Please wait.")
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    if state.get("user_id", "") != user["email"] and user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Not your session")

    answers = state.get("answers", {})
    sanitized_answers = {k: sanitize_for_ai(json.dumps(v)) for k, v in answers.items()}
    prompt = f"Review the following interview answers and provide personalised feedback. Answers: {json.dumps(sanitized_answers)}. Provide strengths, weaknesses, and 3 concrete recommendations in JSON format: {{ 'strengths': ['...'], 'weaknesses': ['...'], 'recommendations': ['...'], 'feedback': {{'technical': '...', 'hr': '...'}} }}"

    try:
        from app.ai_interviewer.llm_providers import get_llm_registry

        feedback = await get_llm_registry().generate_json(
            "You are an expert hiring manager. Respond with valid JSON only.",
            prompt,
        )
        state["aiFeedback"] = feedback
        save_session(payload.session_id, state)
        return {"feedback": feedback}
    except Exception as e:
        return {"error": str(e)}


@router.get("/user/sessions")
def user_sessions(user: dict[str, Any] = Depends(require_candidate)):
    sessions = get_sessions_by_user(user["email"])
    return {"sessions": [_session_summary(s) for s in sessions]}


@router.get("/user/sessions/{session_id}")
def user_session_detail(session_id: str, user: dict[str, Any] = Depends(require_candidate)):
    state = load_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    if state.get("user_id", "") != user["email"] and user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    report = make_report(state)
    proctoring = load_proctoring(session_id)
    return {"session": report, "proctoring": proctoring}


@router.get("/user/stats")
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


@router.get("/admin/candidates")
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


@router.get("/admin/candidates/{candidate_email}")
def admin_candidate_detail(candidate_email: str, user: dict[str, Any] = Depends(require_recruiter)):
    account = load_user(candidate_email)
    if not account:
        raise HTTPException(status_code=404, detail="Candidate not found")
    sessions = get_sessions_by_user(candidate_email)
    return {
        "candidate": {"email": account["email"], "name": account["name"], "role": account["role"]},
        "sessions": [_session_summary(s) for s in sessions],
    }


@router.get("/admin/sessions")
def admin_sessions(user: dict[str, Any] = Depends(require_recruiter)):
    sessions = get_all_sessions()
    return {"sessions": [_session_summary(s) for s in sessions]}


@router.get("/admin/sessions/{session_id}")
def admin_session_detail(session_id: str, user: dict[str, Any] = Depends(require_recruiter)):
    state = load_session(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    report = make_report(state)
    proctoring = load_proctoring(session_id)
    return {"session": report, "proctoring": proctoring}


@router.get("/admin/sessions/{session_id}/proctoring")
def admin_session_proctoring(session_id: str, user: dict[str, Any] = Depends(require_recruiter)):
    logs = load_proctoring(session_id)
    if not logs:
        return {"error": "No proctoring logs found"}
    return logs


@router.get("/admin/stats")
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


@router.get("/admin/benchmark")
def admin_benchmark(user: dict[str, Any] = Depends(require_recruiter)):
    """
    Get platform-wide benchmark data for candidate comparison.
    
    Returns percentile distributions and median scores across dimensions.
    """
    sessions = get_all_sessions()
    
    # Collect all scores from completed sessions
    score_data = {
        "overall": [],
        "technical": [],
        "communication": [],
        "problem_solving": [],
        "system_design": [],
        "coding": [],
        "behavioral": [],
    }
    
    for s in sessions:
        # Check AI interview data first
        ai_interview = s.get("aiInterview", {})
        if ai_interview:
            for interview_id, interview_data in ai_interview.items():
                scores = interview_data.get("scores", {})
                if scores:
                    score_data["overall"].append(scores.get("overall_score", 0))
                    score_data["technical"].append(scores.get("technical_score", 0))
                    score_data["communication"].append(scores.get("communication_score", 0))
                    score_data["problem_solving"].append(scores.get("problem_solving_score", 0))
                    score_data["system_design"].append(scores.get("system_design_score", 0))
                    score_data["coding"].append(scores.get("coding_score", 0))
                    score_data["behavioral"].append(scores.get("behavioral_score", 0))
        
        # Fallback to platform scores
        scores = s.get("scores", {})
        if scores:
            overall = round(sum(scores.values()) / len(scores))
            score_data["overall"].append(overall)
            # Distribute the overall score to dimensions as estimates
            score_data["technical"].append(scores.get("technical", overall))
            score_data["communication"].append(scores.get("communication", overall))
            score_data["problem_solving"].append(scores.get("problem_solving", overall))
    
    def calculate_stats(values):
        if not values:
            return {
                "count": 0,
                "median": 0,
                "mean": 0,
                "std": 0,
                "min": 0,
                "max": 0,
                "p25": 0,
                "p50": 0,
                "p75": 0,
                "p90": 0,
                "p95": 0,
                "percentiles": [],
            }
        
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        
        def percentile(p):
            idx = int(p / 100 * (n - 1))
            return sorted_vals[idx]
        
        return {
            "count": n,
            "median": round(sum(values) / n),
            "mean": round(sum(values) / n),
            "std": round((sum((x - sum(values)/n)**2 for x in values) / n)**0.5),
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "p25": percentile(25),
            "p50": percentile(50),
            "p75": percentile(75),
            "p90": percentile(90),
            "p95": percentile(95),
            "percentiles": sorted_vals,  # For calculating candidate percentiles
        }
    
    benchmark = {}
    for dim, vals in score_data.items():
        benchmark[f"{dim}_stats"] = calculate_stats(vals)
    
    # Flatten for easier frontend consumption
    result = {
        "total_sessions_analyzed": len([s for s in sessions if s.get("scores") or s.get("aiInterview")]),
        "median_overall": benchmark.get("overall_stats", {}).get("median", 0),
        "median_technical": benchmark.get("technical_stats", {}).get("median", 0),
        "median_communication": benchmark.get("communication_stats", {}).get("median", 0),
        "median_problem_solving": benchmark.get("problem_solving_stats", {}).get("median", 0),
        "median_system_design": benchmark.get("system_design_stats", {}).get("median", 0),
        "median_coding": benchmark.get("coding_stats", {}).get("median", 0),
        "median_behavioral": benchmark.get("behavioral_stats", {}).get("median", 0),
        "p75_overall": benchmark.get("overall_stats", {}).get("p75", 0),
        "p90_overall": benchmark.get("overall_stats", {}).get("p90", 0),
        "p95_overall": benchmark.get("overall_stats", {}).get("p95", 0),
        "p75_technical": benchmark.get("technical_stats", {}).get("p75", 0),
        "p90_technical": benchmark.get("technical_stats", {}).get("p90", 0),
        "percentiles": {
            "overall": benchmark.get("overall_stats", {}).get("percentiles", []),
            "technical": benchmark.get("technical_stats", {}).get("percentiles", []),
            "communication": benchmark.get("communication_stats", {}).get("percentiles", []),
            "problem_solving": benchmark.get("problem_solving_stats", {}).get("percentiles", []),
        },
        "distributions": {
            dim: {
                "count": stats["count"],
                "buckets": {
                    "0-40": len([v for v in vals if v < 40]),
                    "40-60": len([v for v in vals if 40 <= v < 60]),
                    "60-75": len([v for v in vals if 60 <= v < 75]),
                    "75-90": len([v for v in vals if 75 <= v < 90]),
                    "90-100": len([v for v in vals if v >= 90]),
                }
            }
            for dim, vals in score_data.items()
            for stats in [benchmark.get(f"{dim}_stats", {})]
        },
    }
    
    return {"benchmark": result}


@router.post("/admin/update-role")
def admin_update_role(payload: UpdateRoleRequest, user: dict[str, Any] = Depends(require_admin)):
    if not _check_rate_limit(f"admin:{user['email']}", settings.admin_rate_limit, settings.admin_rate_window):
        raise HTTPException(status_code=429, detail="Too many requests. Please wait.")
    if payload.role not in ("candidate", "recruiter", "admin"):
        raise HTTPException(status_code=400, detail="Role must be candidate, recruiter, or admin")
    account = load_user(payload.email)
    if not account:
        raise HTTPException(status_code=404, detail="User not found")
    update_user_role(payload.email, payload.role)
    return {"ok": True, "message": f"Role updated to {payload.role}"}


@router.post("/admin/compare")
def admin_compare(payload: CompareRequest, user: dict[str, Any] = Depends(require_recruiter)):
    if len(payload.session_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 sessions required")
    if len(payload.session_ids) > settings.max_compare_sessions:
        raise HTTPException(status_code=400, detail=f"Maximum {settings.max_compare_sessions} sessions for comparison")
    results = []
    for sid in payload.session_ids[:settings.max_compare_sessions]:
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


@router.get("/admin/sessions/{session_id}/timeline")
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


CUSTOM_QUESTIONS_DIR = settings.base_dir / "shared" / "custom_questions"

# ── Interview Templates ────────────────────────────────────────────────────────
TEMPLATES_DIR = settings.shared_dir_path / "interview_templates"
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


class InterviewTemplate(BaseModel):
    id: str
    name: str
    description: str
    role: str
    companies: list[str] = []
    max_questions: int = 12
    voice_enabled: bool = False
    stages: list[dict] = []
    focus_areas: list[str] = []
    created_by: str = ""
    created_at: float = 0
    is_system: bool = False


class CreateTemplateRequest(BaseModel):
    name: str
    description: str
    role: str
    companies: list[str] = []
    max_questions: int = 12
    voice_enabled: bool = False
    stages: list[dict] = []
    focus_areas: list[str] = []


class ApplyTemplateRequest(BaseModel):
    template_id: str
    session_id: str
    role: str
    company: str
    max_questions: int = 12
    voice_enabled: bool = False


def _load_template(template_id: str) -> InterviewTemplate | None:
    """Load a template from disk."""
    filepath = TEMPLATES_DIR / f"{template_id}.json"
    if not filepath.exists():
        return None
    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        return InterviewTemplate(**data)
    except Exception:
        return None


def _save_template(template: InterviewTemplate) -> None:
    """Save a template to disk."""
    filepath = TEMPLATES_DIR / f"{template.id}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(template.model_dump(), f, indent=2)


def _list_templates() -> list[InterviewTemplate]:
    """List all available templates."""
    templates = []
    for filepath in TEMPLATES_DIR.glob("*.json"):
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
            templates.append(InterviewTemplate(**data))
        except Exception:
            continue
    return templates


def _create_system_templates() -> None:
    """Create built-in system templates if they don't exist."""
    system_templates = [
        InterviewTemplate(
            id="google-swe",
            name="Google Software Engineer",
            description="Full Google-style interview: system design, coding, behavioral, Googleyness",
            role="Software Engineer",
            companies=["Google"],
            max_questions=14,
            voice_enabled=True,
            stages=[
                {"id": "warmup", "name": "Warmup & Background", "topics": ["Background", "Motivation"], "target_questions": 2},
                {"id": "coding", "name": "Coding & Algorithms", "topics": ["Data Structures", "Algorithms", "Problem Solving"], "target_questions": 4},
                {"id": "system_design", "name": "System Design", "topics": ["Scalability", "Distributed Systems", "Trade-offs"], "target_questions": 3},
                {"id": "behavioral", "name": "Behavioral & Googleyness", "topics": ["Leadership", "Conflict Resolution", "Growth"], "target_questions": 3},
                {"id": "domain", "name": "Domain Expertise", "topics": ["Specific Role Skills"], "target_questions": 2},
            ],
            focus_areas=["System Design", "Coding", "Scalability", "Leadership"],
            created_by="system",
            created_at=0,
            is_system=True,
        ),
        InterviewTemplate(
            id="amazon-sde",
            name="Amazon SDE (LP Focused)",
            description="Amazon interview with heavy Leadership Principles focus",
            role="Software Development Engineer",
            companies=["Amazon"],
            max_questions=12,
            voice_enabled=True,
            stages=[
                {"id": "lp_behavioral", "name": "Leadership Principles Deep Dive", "topics": ["Customer Obsession", "Ownership", "Bias for Action", "Dive Deep"], "target_questions": 4},
                {"id": "coding", "name": "Coding Challenge", "topics": ["Trees/Graphs", "Dynamic Programming", "System Design (Light)"], "target_questions": 3},
                {"id": "system_design", "name": "System Design", "topics": ["High Availability", "Data Consistency", "Operational Excellence"], "target_questions": 3},
                {"id": "bar_raiser", "name": "Bar Raiser Round", "topics": ["Hiring Bar", "Mentorship", "Innovation"], "target_questions": 2},
            ],
            focus_areas=["Leadership Principles", "Operational Excellence", "Customer Obsession"],
            created_by="system",
            created_at=0,
            is_system=True,
        ),
        InterviewTemplate(
            id="meta-swe",
            name="Meta Software Engineer",
            description="Meta interview: coding, system design, behavioral, product sense",
            role="Software Engineer",
            companies=["Meta", "Facebook"],
            max_questions=13,
            voice_enabled=True,
            stages=[
                {"id": "coding_1", "name": "Coding Interview 1", "topics": ["Arrays/Strings", "Two Pointers", "Sliding Window"], "target_questions": 2},
                {"id": "coding_2", "name": "Coding Interview 2", "topics": ["Trees/Graphs", "Recursion", "Dynamic Programming"], "target_questions": 2},
                {"id": "system_design", "name": "System Design", "topics": ["Social Systems", "Feed Ranking", "Real-time"], "target_questions": 3},
                {"id": "behavioral", "name": "Behavioral & Product Sense", "topics": ["Move Fast", "Impact", "Communication"], "target_questions": 3},
                {"id": "domain", "name": "Domain Round", "topics": ["Role-specific"], "target_questions": 2},
            ],
            focus_areas=["Coding", "System Design", "Product Sense", "Impact"],
            created_by="system",
            created_at=0,
            is_system=True,
        ),
        InterviewTemplate(
            id="startup-fullstack",
            name="Startup Full-Stack Engineer",
            description="Pragmatic startup interview: shipping features, breadth over depth",
            role="Full Stack Engineer",
            companies=[],
            max_questions=10,
            voice_enabled=False,
            stages=[
                {"id": "experience", "name": "Project Deep Dive", "topics": ["Recent Projects", "Tech Choices", "Trade-offs"], "target_questions": 3},
                {"id": "coding", "name": "Practical Coding", "topics": ["API Design", "Database", "Frontend Integration"], "target_questions": 3},
                {"id": "architecture", "name": "Architecture & Decisions", "topics": ["Scaling", "Tech Debt", "Monitoring"], "target_questions": 2},
                {"id": "culture", "name": "Culture & Ownership", "topics": ["Autonomy", "Learning", "Prioritization"], "target_questions": 2},
            ],
            focus_areas=["Shipping", "Pragmatism", "End-to-End Ownership"],
            created_by="system",
            created_at=0,
            is_system=True,
        ),
        InterviewTemplate(
            id="ml-engineer",
            name="ML Engineer / Data Scientist",
            description="ML-focused interview: modeling, MLOps, system design for ML",
            role="ML Engineer",
            companies=[],
            max_questions=12,
            voice_enabled=False,
            stages=[
                {"id": "ml_fundamentals", "name": "ML Fundamentals", "topics": ["Supervised/Unsupervised", "Evaluation", "Bias-Variance"], "target_questions": 3},
                {"id": "ml_system_design", "name": "ML System Design", "topics": ["Training Pipeline", "Serving", "Monitoring", "Feature Stores"], "target_questions": 3},
                {"id": "coding_ml", "name": "ML Coding", "topics": ["PyTorch/TF", "Data Processing", "Custom Layers"], "target_questions": 2},
                {"id": "applied", "name": "Applied Experience", "topics": ["Production Models", "A/B Testing", "Drift Detection"], "target_questions": 2},
                {"id": "behavioral", "name": "Collaboration & Impact", "topics": ["Cross-functional", "Stakeholders", "Research to Prod"], "target_questions": 2},
            ],
            focus_areas=["ML Systems", "Production ML", "Model Evaluation"],
            created_by="system",
            created_at=0,
            is_system=True,
        ),
        InterviewTemplate(
            id="devops-sre",
            name="DevOps / SRE",
            description="Infrastructure, reliability, and automation focus",
            role="DevOps Engineer",
            companies=[],
            max_questions=11,
            voice_enabled=False,
            stages=[
                {"id": "linux_internals", "name": "Linux & Internals", "topics": ["Kernel", "Networking", "Filesystems", "Performance"], "target_questions": 2},
                {"id": "cloud_native", "name": "Cloud Native", "topics": ["Kubernetes", "Service Mesh", "Observability", "GitOps"], "target_questions": 3},
                {"id": "reliability", "name": "Reliability Engineering", "topics": ["SLO/SLI", "Incident Response", "Chaos Engineering", "Capacity Planning"], "target_questions": 3},
                {"id": "automation", "name": "Automation & Tooling", "topics": ["IaC", "CI/CD", "Scripting", "Developer Experience"], "target_questions": 2},
                {"id": "behavioral", "name": "Operational Maturity", "topics": ["On-call", "Postmortems", "Communication"], "target_questions": 1},
            ],
            focus_areas=["Kubernetes", "Observability", "Reliability", "Automation"],
            created_by="system",
            created_at=0,
            is_system=True,
        ),
        InterviewTemplate(
            id="frontend-specialist",
            name="Frontend Specialist",
            description="React, performance, accessibility, and frontend architecture",
            role="Frontend Engineer",
            companies=[],
            max_questions=10,
            voice_enabled=False,
            stages=[
                {"id": "react_deep", "name": "React Internals", "topics": ["Reconciliation", "Hooks", "Suspense", "Server Components"], "target_questions": 2},
                {"id": "performance", "name": "Performance & Core Web Vitals", "topics": ["Bundle Size", "Rendering", "Caching", "Lazy Loading"], "target_questions": 2},
                {"id": "architecture", "name": "Frontend Architecture", "topics": ["State Management", "Micro-frontends", "Design Systems", "Testing"], "target_questions": 2},
                {"id": "coding", "name": "Frontend Coding", "topics": ["Component Design", "Accessibility", "TypeScript", "Animation"], "target_questions": 2},
                {"id": "collab", "name": "Design & Product Collab", "topics": ["Design Systems", "Figma", "Product Thinking"], "target_questions": 2},
            ],
            focus_areas=["React", "Performance", "TypeScript", "Accessibility", "Design Systems"],
            created_by="system",
            created_at=0,
            is_system=True,
        ),
        InterviewTemplate(
            id="backend-specialist",
            name="Backend Specialist",
            description="Distributed systems, databases, APIs, and backend architecture",
            role="Backend Engineer",
            companies=[],
            max_questions=11,
            voice_enabled=False,
            stages=[
                {"id": "distributed", "name": "Distributed Systems", "topics": ["Consensus", "Replication", "Sharding", "Consistency Models"], "target_questions": 3},
                {"id": "databases", "name": "Database Internals", "topics": ["Indexing", "Query Optimization", "Transactions", "NoSQL vs SQL"], "target_questions": 2},
                {"id": "api_design", "name": "API Design & Architecture", "topics": ["REST/gRPC/GraphQL", "Versioning", "Rate Limiting", "Observability"], "target_questions": 2},
                {"id": "coding", "name": "Backend Coding", "topics": ["Concurrency", "Caching", "Queue Systems", "Idempotency"], "target_questions": 2},
                {"id": "operational", "name": "Production Readiness", "topics": ["Migrations", "Deployments", "Debugging", "Cost Optimization"], "target_questions": 2},
            ],
            focus_areas=["Distributed Systems", "Databases", "API Design", "Production Ops"],
            created_by="system",
            created_at=0,
            is_system=True,
        ),
        InterviewTemplate(
            id="generic-technical",
            name="Generic Technical Interview",
            description="Balanced technical interview for any software engineering role",
            role="Software Engineer",
            companies=[],
            max_questions=10,
            voice_enabled=False,
            stages=[
                {"id": "intro", "name": "Introduction & Background", "topics": ["Experience", "Tech Stack", "Projects"], "target_questions": 2},
                {"id": "technical_depth", "name": "Technical Depth", "topics": ["Core CS", "Language Internals", "Frameworks"], "target_questions": 3},
                {"id": "problem_solving", "name": "Problem Solving & Coding", "topics": ["Algorithms", "Data Structures", "Clean Code"], "target_questions": 3},
                {"id": "system_design", "name": "System Design (Light)", "topics": ["Architecture", "Scaling", "Trade-offs"], "target_questions": 2},
            ],
            focus_areas=["Problem Solving", "Technical Depth", "Communication"],
            created_by="system",
            created_at=0,
            is_system=True,
        ),
    ]
    
    for template in system_templates:
        filepath = TEMPLATES_DIR / f"{template.id}.json"
        if not filepath.exists():
            _save_template(template)


# Initialize system templates on module load
_create_system_templates()


@router.post("/admin/upload-questions")
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
    safe_round_type = re.sub(r'[^a-zA-Z0-9_-]', '', round_type)
    if not safe_round_type:
        raise HTTPException(status_code=400, detail="Invalid round_type")
    filepath = CUSTOM_QUESTIONS_DIR / f"{safe_round_type}_custom.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(questions, f, indent=2)
    return {"ok": True, "count": len(questions), "round_type": round_type}


@router.get("/admin/custom-questions")
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


# ── Interview Templates Endpoints ──────────────────────────────────────────────

@router.get("/templates")
def list_interview_templates(user: dict[str, Any] = Depends(get_current_user)):
    """List all available interview templates."""
    templates = _list_templates()
    return {
        "templates": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "role": t.role,
                "companies": t.companies,
                "max_questions": t.max_questions,
                "voice_enabled": t.voice_enabled,
                "stage_count": len(t.stages),
                "focus_areas": t.focus_areas,
                "is_system": t.is_system,
            }
            for t in templates
        ]
    }


@router.get("/templates/{template_id}")
def get_interview_template(template_id: str, user: dict[str, Any] = Depends(get_current_user)):
    """Get a specific interview template."""
    template = _load_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.post("/templates", status_code=201)
def create_interview_template(
    request: CreateTemplateRequest,
    user: dict[str, Any] = Depends(require_recruiter),
):
    """Create a custom interview template (recruiter/admin only)."""
    template_id = f"custom-{uuid.uuid4().hex[:8]}"
    template = InterviewTemplate(
        id=template_id,
        name=request.name,
        description=request.description,
        role=request.role,
        companies=request.companies,
        max_questions=request.max_questions,
        voice_enabled=request.voice_enabled,
        stages=request.stages,
        focus_areas=request.focus_areas,
        created_by=user.get("email", ""),
        created_at=time.time(),
        is_system=False,
    )
    _save_template(template)
    return template


@router.put("/templates/{template_id}")
def update_interview_template(
    template_id: str,
    request: CreateTemplateRequest,
    user: dict[str, Any] = Depends(require_recruiter),
):
    """Update a custom interview template."""
    template = _load_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.is_system:
        raise HTTPException(status_code=403, detail="Cannot modify system templates")
    if template.created_by != user.get("email", "") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Can only edit your own templates")
    
    template.name = request.name
    template.description = request.description
    template.role = request.role
    template.companies = request.companies
    template.max_questions = request.max_questions
    template.voice_enabled = request.voice_enabled
    template.stages = request.stages
    template.focus_areas = request.focus_areas
    _save_template(template)
    return template


@router.delete("/templates/{template_id}")
def delete_interview_template(
    template_id: str,
    user: dict[str, Any] = Depends(require_recruiter),
):
    """Delete a custom interview template."""
    template = _load_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.is_system:
        raise HTTPException(status_code=403, detail="Cannot delete system templates")
    if template.created_by != user.get("email", "") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Can only delete your own templates")
    
    filepath = TEMPLATES_DIR / f"{template_id}.json"
    filepath.unlink(missing_ok=True)
    return {"ok": True, "message": "Template deleted"}


@router.post("/templates/{template_id}/apply")
def apply_interview_template(
    template_id: str,
    request: ApplyTemplateRequest,
    user: dict[str, Any] = Depends(get_current_user),
):
    """Apply a template to create an interview session."""
    template = _load_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    
    # Create session with template settings
    session_id = str(uuid.uuid4())
    
    # Build interview plan from template stages
    stages = []
    for i, stage in enumerate(template.stages):
        stages.append({
            "id": stage.get("id", f"stage_{i}"),
            "name": stage.get("name", f"Stage {i+1}"),
            "description": stage.get("description", ""),
            "topics": stage.get("topics", []),
            "target_questions": stage.get("target_questions", 2),
            "completed": False,
        })
    
    interview_plan = {
        "stages": stages,
        "total_questions": template.max_questions,
        "focus_areas": template.focus_areas,
        "opening_strategy": f"Start with {stages[0]['name'] if stages else 'introduction'}",
        "closing_strategy": "Wrap up with behavioral questions",
        "estimated_duration_minutes": template.max_questions * 4,
    }
    
    state = {
        "sessionId": session_id,
        "user_id": user.get("email", ""),
        "resume": {"name": "", "skills": []},
        "selectedCompany": request.company,
        "selectedCompanies": template.companies if template.companies else [request.company],
        "currentRound": "ai_interview",
        "currentQuestion": 0,
        "answers": {},
        "codingSubmissions": [],
        "scores": default_scores(),
        "ai_interview_plan": interview_plan,
        "ai_interview_role": request.role,
        "ai_interview_max_questions": template.max_questions,
        "ai_interview_voice_enabled": template.voice_enabled,
    }
    
    save_session(session_id, state, user_id=user.get("email", ""))
    
    return {
        "session_id": session_id,
        "template": {
            "id": template.id,
            "name": template.name,
            "role": template.role,
        },
        "interview_plan": interview_plan,
        "message": "Template applied. Start interview via /ai-interview/start",
    }
