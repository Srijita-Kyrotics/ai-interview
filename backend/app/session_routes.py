from __future__ import annotations

import json
import re
import uuid
from typing import Any

import google.generativeai as genai
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

    gemini_key = settings.gemini_api_key
    if gemini_key:
        try:
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(settings.gemini_model)
            prompt = f"Score the following {round_key} interview answers out of 100 based on quality, clarity, and depth. Answers: {json.dumps(answers)}. Only return the integer score from 0 to 100."
            response = model.generate_content(prompt)
            match = re.search(r'\b(100|\d{1,2})\b', response.text)
            if match:
                return int(match.group(1))
        except Exception:
            pass

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
def generate_ai_questions(payload: AIQuestionsRequest, user: dict[str, Any] = Depends(require_candidate)):
    if not _check_rate_limit(f"ai:{user['email']}", settings.ai_rate_limit, settings.ai_rate_window):
        raise HTTPException(status_code=429, detail="Too many AI requests. Please wait.")
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    if state.get("user_id", "") != user["email"] and user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Not your session")

    gemini_key = settings.gemini_api_key
    if not gemini_key:
        return {"error": "Gemini API key not configured"}

    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel(settings.gemini_model)

    resume = state.get("resume", {})
    skills = sanitize_for_ai(", ".join(resume.get("skills", [])))
    company = sanitize_for_ai(state.get("selectedCompany", "Unknown"))

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


@router.post("/ai/feedback")
def generate_ai_feedback(payload: AIFeedbackRequest, user: dict[str, Any] = Depends(require_candidate)):
    if not _check_rate_limit(f"ai:{user['email']}", settings.ai_rate_limit, settings.ai_rate_window):
        raise HTTPException(status_code=429, detail="Too many AI requests. Please wait.")
    state = load_session(payload.session_id)
    if not state:
        return {"error": "No active session"}
    if state.get("user_id", "") != user["email"] and user["role"] not in ("recruiter", "admin"):
        raise HTTPException(status_code=403, detail="Not your session")

    gemini_key = settings.gemini_api_key
    if not gemini_key:
        return {"error": "Gemini API key not configured"}

    genai.configure(api_key=gemini_key)
    model = genai.GenerativeModel(settings.gemini_model)

    answers = state.get("answers", {})
    sanitized_answers = {k: sanitize_for_ai(json.dumps(v)) for k, v in answers.items()}
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
