"""
AI Interviewer FastAPI Router
==============================
Provides REST endpoints and a WebSocket for the AI interviewer.

Endpoints:
  POST /ai-interview/start         → Start a new AI interview session
  POST /ai-interview/resume        → Resume an interrupted interview
  GET  /ai-interview/{session}/state → Get current session state
  GET  /ai-interview/{session}/report → Get final report
  GET  /ai-interview/{session}/timeline → Get interview timeline (P6)
  GET  /ai-interview/{session}/refresh-token → Refresh JWT for WS (P3)
  WS   /ws/ai-interview            → Real-time interview WebSocket
  WS   /ws/ai-interview/voice      → Voice interview WebSocket

WebSocket Protocol (text mode):
  Client → Server:
    {"type": "answer", "text": "candidate answer text", "duration_ms": 5000}
    {"type": "answer", "text": "...", "code": "snapshot", "language": "python"}
    Binary: raw audio bytes (WebM/opus)  → voice mode, then:
    {"type": "audio_end"}               → transcribe buffered audio + process answer
    {"type": "end"}
    {"type": "ping"}
    {"type": "refresh_token", "token": "new_jwt_token"}  (P3)

  Server → Client:
    {"type": "session_ready", "opening_text": "...", "session_id": "..."}
    {"type": "question", "text": "...", "question_id": "...", "is_follow_up": false}
    {"type": "coding_problem", "problem": {...}}   (Feature 9: live coding round)
    {"type": "thinking"}
    {"type": "transition", "text": "..."}
    {"type": "processing"} / {"type": "stt_result", "text": "...", "is_final": true}
    {"type": "ai_response_text", "text": "..."}    (voice mode)
    Binary: TTS audio bytes (MP3)                  (voice mode)
    {"type": "interview_complete", "closing_text": "...", "report": {...}}
    {"type": "token_refreshed"}
    {"type": "error", "message": "..."}
    {"type": "pong"}

WebSocket Protocol (voice mode):
  Client → Server:
    Binary: raw audio bytes (WebM/opus)
    {"type": "end_voice"}

  Server → Client:
    {"type": "stt_result", "text": "...", "is_final": true}
    {"type": "ai_response_text", "text": "..."}
    Binary: TTS audio bytes (MP3)
    {"type": "interview_complete", "report": {...}}
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from starlette.websockets import WebSocketState

from app.ai_interviewer.graph import InterviewGraphRunner
from app.ai_interviewer.nodes import GeminiUnavailableError
from app.ai_interviewer.state import make_initial_state
from app.ai_interviewer.state_store import InterviewStateStore, get_state_store
from app.ai_interviewer.voice import VoicePipeline
from app.code_executor import execute_local
from app.config import settings
from app.db import check_rate_limit, load_session, save_session
from app.helpers import create_token, decode_token, default_scores
from app.resume_parser import parse_resume_text

logger = logging.getLogger("ai_interview.router")

router = APIRouter(prefix="/ai-interview", tags=["AI Interviewer"])

# ── State Store (Redis-backed, replaces in-memory _active_runners) ───────────
_store: InterviewStateStore | None = None


def _get_store() -> InterviewStateStore:
    global _store
    if _store is None:
        _store = get_state_store()
    return _store


# ── Request/Response Models ──────────────────────────────────────────────────

class StartInterviewRequest(BaseModel):
    session_id: str
    role: str
    company: str = "the company"
    max_questions: int = 12
    voice_enabled: bool = False


class StartInterviewResponse(BaseModel):
    session_id: str
    interview_session_id: str
    status: str
    message: str


class ResumeInterviewRequest(BaseModel):
    interview_session_id: str
    session_id: str  # Original platform session


class RunCodeRequest(BaseModel):
    language: str
    code: str
    stdin: str = ""


# ── Dependency: Auth ──────────────────────────────────────────────────────────

def get_current_user(
    authorization: str | None = Header(None),
    token: str = Query(default=""),
) -> dict:
    # Accept the JWT from the Authorization: Bearer header (app-wide convention)
    # or from the ?token= query string (legacy / WS-style callers).
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


# ── REST Endpoints ───────────────────────────────────────────────────────────

DEFAULT_AI_INTERVIEW_RESUME = """Name: AI Interview Candidate
Email: candidate@example.com
Phone: +91 0000000000
Summary: Software Engineer with strong fundamentals in data structures, algorithms, system design, and software engineering best practices.
Skills: Python, JavaScript, SQL, Data Structures, Algorithms, System Design, REST APIs, Git, Problem Solving
Experience:
- Software Engineer, 2+ years: Built REST APIs, optimized query performance, and collaborated in agile teams.
Projects:
- Implemented data structures and algorithms to solve complex problems efficiently.
Education: Bachelor of Technology in Computer Science
Certifications: Data Structures and Algorithms, System Design"""


@router.post("/create-session", response_model=dict)
async def create_ai_interview_session(user: dict = Depends(get_current_user)):
    """
    Create a platform session for the direct AI interview flow.

    Lets a candidate jump straight into the Obi interview without a prior
    resume upload. The session is seeded with a generic resume so the
    interview pipeline always has resume context to work from.
    """
    session_id = str(uuid.uuid4())
    resume = parse_resume_text(DEFAULT_AI_INTERVIEW_RESUME, "direct-ai-interview.txt")
    user_id = user.get("email", "")
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
        "user_id": user_id,
    }
    save_session(session_id, state, user_id=user_id)
    logger.info("AI interview session created directly", extra={"session_id": session_id, "email": user_id})
    return {"session_id": session_id, "resume": resume}


@router.post("/start", response_model=StartInterviewResponse)
async def start_ai_interview(
    request: StartInterviewRequest,
    user: dict = Depends(get_current_user),
):
    """
    Initialize an AI interview session.

    This endpoint:
    1. Loads the session (which contains the parsed resume)
    2. Creates an InterviewGraphRunner
    3. Stores initial state in Redis
    4. Returns the interview session ID (WS does the actual initialization)
    """
    session_data = load_session(request.session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    resume_parsed = session_data.get("resume", {})
    resume_raw = resume_parsed.get("rawText", "") or session_data.get("resume_raw_text", "")

    if not resume_parsed and not resume_raw:
        # No uploaded resume — start a generic interview seeded with a
        # placeholder profile so the pipeline always has context to work from.
        resume_parsed = parse_resume_text(DEFAULT_AI_INTERVIEW_RESUME, "generic-interview.txt")
        resume_raw = DEFAULT_AI_INTERVIEW_RESUME
        logger.info(
            "No resume found, falling back to generic profile",
            extra={"session_id": request.session_id},
        )

    store = _get_store()

    # Check for existing resumable session
    existing_id = store.get_resumable_session(request.session_id)
    if existing_id:
        return StartInterviewResponse(
            session_id=request.session_id,
            interview_session_id=existing_id,
            status="resumable",
            message="An existing interview session was found. Use /resume to continue.",
        )

    # Create the interview state
    interview_session_id = str(uuid.uuid4())
    initial_state = make_initial_state(
        session_id=interview_session_id,
        candidate_email=user.get("email", ""),
        role=request.role,
        company=request.company,
        resume_raw_text=resume_raw,
        resume_parsed=resume_parsed,
        max_questions=min(request.max_questions, 20),
        voice_enabled=request.voice_enabled,
    )

    # Create runner with state store
    runner = InterviewGraphRunner(
        session_id=interview_session_id,
        initial_state=initial_state,
        platform_session_id=request.session_id,
        state_store=store,
    )

    # Persist to Redis
    store.save_state(interview_session_id, runner.state)
    store.save_meta(interview_session_id, {
        "platform_session_id": request.session_id,
        "status": "created",
        "created_at": time.time(),
        "updated_at": time.time(),
        "candidate_email": user.get("email", ""),
    })

    logger.info(
        "AI interview session created",
        extra={
            "session_id": request.session_id,
            "interview_session_id": interview_session_id,
            "role": request.role,
            "email": user.get("email"),
        }
    )

    return StartInterviewResponse(
        session_id=request.session_id,
        interview_session_id=interview_session_id,
        status="ready",
        message="Session initialized. Connect via WebSocket to begin.",
    )


@router.post("/run-code")
async def run_interview_code(
    request: RunCodeRequest,
    user: dict = Depends(get_current_user),
):
    """
    Execute candidate code in a sandboxed subprocess and return raw output.

    Unlike the coding-round ``/run-code`` grader, this endpoint has no test
    cases: Obi's coding questions are LLM-generated, so the candidate just
    runs their code against optional stdin and inspects stdout/stderr.
    """
    if not request.code.strip():
        raise HTTPException(status_code=400, detail="Code cannot be empty")

    if not check_rate_limit(f"code:{user.get('email', '')}", settings.code_rate_limit, settings.code_rate_window):
        raise HTTPException(status_code=429, detail="Too many code execution requests. Please wait.")

    result = await execute_local(request.language, request.code, request.stdin)
    logger.info(
        "AI interview code run",
        extra={"email": user.get("email"), "language": request.language, "timed_out": result.get("timed_out")},
    )
    return {
        "ok": result.get("ok"),
        "missing_runtime": result.get("missing_runtime"),
        "timed_out": result.get("timed_out"),
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
        "error": result.get("error", ""),
    }


@router.post("/resume", response_model=StartInterviewResponse)
async def resume_ai_interview(
    request: ResumeInterviewRequest,
    user: dict = Depends(get_current_user),
):
    """
    Resume an interrupted AI interview session (P2).

    Restores state from Redis checkpoint and returns the session ID
    for the client to reconnect via WebSocket.
    """
    store = _get_store()

    # Try to load from Redis
    state = store.load_state(request.interview_session_id)
    if not state:
        raise HTTPException(status_code=404, detail="No resumable session found in Redis")

    meta = store.load_meta(request.interview_session_id)
    if meta and meta.get("status") in ("completed", "error"):
        raise HTTPException(status_code=410, detail="This interview session is no longer resumable")

    # Verify platform session matches
    if meta and meta.get("platform_session_id") != request.session_id:
        raise HTTPException(status_code=403, detail="Session does not belong to this user")

    # Update meta
    store.save_meta(request.interview_session_id, {
        **(meta or {}),
        "status": "resuming",
        "updated_at": time.time(),
    })

    logger.info(
        "AI interview session resumed",
        extra={
            "interview_session_id": request.interview_session_id,
            "phase": state.get("phase"),
            "questions_asked": state.get("questions_asked", 0),
        }
    )

    return StartInterviewResponse(
        session_id=request.session_id,
        interview_session_id=request.interview_session_id,
        status="resuming",
        message="Session restored. Connect via WebSocket to continue.",
    )


@router.get("/refresh-token")
async def refresh_interview_token(
    interview_session_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Issue a fresh JWT for WebSocket re-authentication (P3).

    Call this before the current token expires to get a new one,
    then send it to the WebSocket via a 'refresh_token' message.
    """
    new_token = create_token(user["email"], user.get("role", "candidate"))
    return {"token": new_token, "expires_in": settings.jwt_expiry_hours * 3600}


@router.get("/{interview_session_id}/state")
async def get_interview_state(
    interview_session_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Get current state of an active interview session."""
    store = _get_store()
    state = store.load_state(interview_session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Interview session not found or expired")

    return {
        "phase": state.get("phase"),
        "questions_asked": state.get("questions_asked"),
        "max_questions": state.get("max_questions"),
        "current_stage": state.get("current_stage", {}).get("name"),
        "topics_covered": state.get("memory", {}).get("topics_covered", []),
        "should_end": state.get("should_end"),
        "claims_summary": {
            "total": len(state.get("resume_claims", [])),
            "verified": len([c for c in state.get("resume_claims", []) if c.get("verification_status") == "VERIFIED"]),
            "failed": len([c for c in state.get("resume_claims", []) if c.get("verification_status") == "FAILED_VERIFICATION"]),
            "unverified": len([c for c in state.get("resume_claims", []) if c.get("verification_status") == "UNVERIFIED"]),
        },
        "topic_mastery": {
            t: m["mastery_score"]
            for t, m in state.get("topic_mastery", {}).items()
        },
        "contradictions_found": len([
            f for f in state.get("candidate_facts", []) if f.get("contradicted", False)
        ]),
        "difficulty_level": state.get("difficulty_level", {}).get("level", "intermediate"),
        "code_versions": len(state.get("code_history", [])),
        "replan_count": state.get("replan_count", 0),
        "current_comm_metrics": state.get("current_comm_metrics"),
        "active_coding_problem": {
            "id": p["id"],
            "title": p["title"],
            "difficulty": p["difficulty"],
            "topic": p["topic"],
            "description": p["description"],
            "constraints": p.get("constraints", []),
            "examples": p.get("examples", []),
            "languages": p.get("languages", []),
            "starter_code": p.get("starter_code", {}),
        } if (p := state.get("active_coding_problem")) else None,
        "coding_submissions": [
            {
                "problem_id": s["problem_id"],
                "quality": s["quality"],
                "language": s.get("language", ""),
            }
            for s in state.get("coding_submissions", [])
        ],
    }


@router.get("/{interview_session_id}/report")
async def get_interview_report(
    interview_session_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Get the final interview report (only available after completion)."""
    store = _get_store()
    state = store.load_state(interview_session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Interview session not found")

    report = state.get("final_report")
    if not report:
        raise HTTPException(status_code=425, detail="Interview not yet completed")

    return report


@router.get("/{interview_session_id}/timeline")
async def get_interview_timeline(
    interview_session_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Get the interview timeline for the recruiter portal (P6).

    Returns a list of timestamped events in chronological order.
    """
    store = _get_store()
    timeline = store.get_timeline(interview_session_id)
    if not timeline:
        # Fallback: check if state exists
        state = store.load_state(interview_session_id)
        if not state:
            raise HTTPException(status_code=404, detail="Interview session not found")

    return {
        "interview_session_id": interview_session_id,
        "events": timeline,
        "event_count": len(timeline),
    }


# ── Token Validation Helper ──────────────────────────────────────────────────

def _validate_ws_token(token: str) -> dict | None:
    """Validate a JWT token for WebSocket auth. Returns payload or None."""
    return decode_token(token)


# ── Text Interview WebSocket ──────────────────────────────────────────────────

@router.websocket("/ws")
async def ai_interview_websocket(
    websocket: WebSocket,
    token: str = Query(default=""),
    interview_session_id: str = Query(default=""),
    session_id: str = Query(default=""),  # Original platform session
):
    """
    Real-time text-based AI interview via WebSocket.

    Protocol: See module docstring.
    Supports reconnection and token refresh (P3).
    """
    await websocket.accept()

    store = _get_store()

    # ── Auth ──────────────────────────────────────────────────────────────
    payload = _validate_ws_token(token)
    if not payload:
        await websocket.send_json({"type": "error", "message": "Invalid token"})
        await websocket.close(code=4001)
        return

    # ── Get or Restore Runner ─────────────────────────────────────────────
    runner = None

    # 1. Try Redis checkpoint first (P2 - resume)
    state = store.load_state(interview_session_id)
    if state:
        meta = store.load_meta(interview_session_id) or {}
        if meta.get("status") not in ("completed", "error"):
            runner = InterviewGraphRunner(
                session_id=interview_session_id,
                initial_state=state,
                platform_session_id=meta.get("platform_session_id", session_id),
                state_store=store,
            )
            runner._initialized = state.get("phase", "analyzing") != "analyzing"
            logger.info("Restored runner from Redis", extra={"session": interview_session_id})

    # 2. Fallback: create on-the-fly from session data
    if not runner:
        session_data = load_session(session_id) if session_id else None
        if not session_data:
            await websocket.send_json({"type": "error", "message": "Interview session not found"})
            await websocket.close(code=4002)
            return

        resume_parsed = session_data.get("resume", {})
        resume_raw = resume_parsed.get("rawText", "")
        new_interview_id = interview_session_id or str(uuid.uuid4())

        initial_state = make_initial_state(
            session_id=new_interview_id,
            candidate_email=payload.get("email", ""),
            role=session_data.get("role", "Software Engineer"),
            company=session_data.get("selectedCompany", "the company"),
            resume_raw_text=resume_raw,
            resume_parsed=resume_parsed,
        )
        runner = InterviewGraphRunner(
            session_id=new_interview_id,
            initial_state=initial_state,
            platform_session_id=session_id,
            state_store=store,
        )
        store.save_state(new_interview_id, runner.state)
        store.save_meta(new_interview_id, {
            "platform_session_id": session_id,
            "status": "created",
            "created_at": time.time(),
        })
        interview_session_id = new_interview_id

    try:
        # ── Initialization Phase ──────────────────────────────────────────
        await websocket.send_json({"type": "thinking", "message": "Analyzing your resume..."})

        if not runner._initialized:
            opening_text = await runner.initialize()
            await websocket.send_json({
                "type": "session_ready",
                "opening_text": opening_text,
                "session_id": interview_session_id,
                "timestamp": time.time(),
            })

            # Generate and send first question
            await websocket.send_json({"type": "thinking", "message": "Preparing first question..."})
            first_question = await runner.generate_first_question()
            state = runner.get_state()
            current_q = state.get("current_question", {})
            await websocket.send_json({
                "type": "question",
                "text": first_question,
                "question_id": current_q.get("id", ""),
                "stage": state.get("current_stage", {}).get("name", ""),
                "is_follow_up": False,
                "timestamp": time.time(),
            })
        else:
            # Resuming: send current state summary (P2)
            state = runner.get_state()
            current_q = state.get("current_question", {})
            await websocket.send_json({
                "type": "session_restored",
                "session_id": interview_session_id,
                "phase": state.get("phase"),
                "questions_asked": state.get("questions_asked", 0),
                "max_questions": state.get("max_questions", 12),
                "current_stage": state.get("current_stage", {}).get("name", ""),
                "timestamp": time.time(),
            })
            # Re-send the last question
            if current_q:
                await websocket.send_json({
                    "type": "question",
                    "text": current_q.get("question", ""),
                    "question_id": current_q.get("id", ""),
                    "stage": state.get("current_stage", {}).get("name", ""),
                    "is_follow_up": False,
                    "timestamp": time.time(),
                })
            # Re-send active coding problem if mid-coding-round
            problem = state.get("active_coding_problem")
            if problem and problem.get("description"):
                await websocket.send_json({
                    "type": "coding_problem",
                    "problem": problem,
                    "timestamp": time.time(),
                })

        # ── Main Interview Loop ───────────────────────────────────────────
        audio_buffer = bytearray()
        voice_pipeline = None

        async def _send_coding_problem_if_active() -> None:
            """Feature 9: deliver the live-coding problem alongside a question."""
            problem = runner.state.get("active_coding_problem")
            if problem and problem.get("description"):
                await websocket.send_json({
                    "type": "coding_problem",
                    "problem": problem,
                    "timestamp": time.time(),
                })

        async def _run_answer(answer_text: str, code_snapshot: str | None = None, code_language: str = "") -> bool:
            """Shared handler for typed and voice answers. Returns True if the interview ended."""
            if code_snapshot and code_language:
                runner.state["current_code_snapshot_language"] = code_language

            await websocket.send_json({"type": "thinking", "timestamp": time.time()})

            result = await runner.process_answer(answer_text, code_snapshot=code_snapshot)

            if result.get("should_end"):
                # Save and send final report
                await _save_interview_result(session_id, interview_session_id, runner)
                await websocket.send_json({
                    "type": "interview_complete",
                    "closing_text": result.get("text", ""),
                    "report": result.get("final_report", {}),
                    "scores": result.get("final_report", {}).get("scores", {}),
                    "timestamp": time.time(),
                })
                return True

            # Check if this is a transition message
            if result.get("is_transition"):
                await websocket.send_json({
                    "type": "transition",
                    "text": result.get("text", ""),
                    "timestamp": time.time(),
                })
                # After transition, immediately send next question
                await websocket.send_json({"type": "thinking", "timestamp": time.time()})
                state = runner.get_state()
                current_q = state.get("current_question", {})
                await websocket.send_json({
                    "type": "question",
                    "text": state.get("ai_response_text", ""),
                    "question_id": current_q.get("id", ""),
                    "stage": state.get("current_stage", {}).get("name", ""),
                    "is_follow_up": False,
                    "timestamp": time.time(),
                })
                await _send_coding_problem_if_active()
            else:
                state = runner.get_state()
                current_q = state.get("current_question", {})
                await websocket.send_json({
                    "type": "question",
                    "text": result.get("text", ""),
                    "question_id": current_q.get("id", ""),
                    "stage": state.get("current_stage", {}).get("name", ""),
                    "is_follow_up": result.get("is_follow_up", False),
                    "questions_asked": result.get("questions_asked", 0),
                    "max_questions": result.get("max_questions", 12),
                    "timestamp": time.time(),
                })
                await _send_coding_problem_if_active()
            return False

        while True:
            data = await websocket.receive()

            # Binary audio (voice mode) — buffered until audio_end
            audio_bytes = data.get("bytes")
            if audio_bytes:
                audio_buffer.extend(audio_bytes)
                continue

            raw = data.get("text")
            if raw is None:
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type", "")

            # Ping
            if msg_type == "ping":
                await websocket.send_json({"type": "pong", "timestamp": time.time()})
                continue

            # Token refresh (P3)
            if msg_type == "refresh_token":
                new_token = msg.get("token", "")
                new_payload = _validate_ws_token(new_token)
                if new_payload:
                    payload = new_payload  # Update in-place
                    await websocket.send_json({"type": "token_refreshed", "timestamp": time.time()})
                else:
                    await websocket.send_json({"type": "error", "message": "Invalid refresh token"})
                continue

            # End interview
            if msg_type == "end":
                result = await runner._finalize()
                await _save_interview_result(session_id, interview_session_id, runner)
                await websocket.send_json({
                    "type": "interview_complete",
                    "closing_text": result.get("text", ""),
                    "report": result.get("final_report", {}),
                    "timestamp": time.time(),
                })
                break

            # Feature 7: Toggle system design mode
            if msg_type == "set_system_design_mode":
                enabled = msg.get("enabled", False)
                runner.state["is_system_design_mode"] = bool(enabled)
                runner._checkpoint()
                await websocket.send_json({
                    "type": "system_design_mode_changed",
                    "enabled": bool(enabled),
                    "timestamp": time.time(),
                })
                continue

            # Voice: end of a recorded utterance → STT → answer
            if msg_type == "audio_end":
                if not audio_buffer:
                    continue
                if voice_pipeline is None:
                    voice_pipeline = VoicePipeline.from_settings()
                await websocket.send_json({"type": "processing", "timestamp": time.time()})

                transcript = await voice_pipeline.audio_to_text(bytes(audio_buffer))
                audio_buffer.clear()

                await websocket.send_json({
                    "type": "stt_result",
                    "text": transcript,
                    "is_final": True,
                    "timestamp": time.time(),
                })

                if not transcript:
                    retry_text = "Could you please repeat that?"
                    retry_audio = await voice_pipeline.tts.synthesize(retry_text)
                    await websocket.send_json({
                        "type": "ai_response_text",
                        "text": retry_text,
                        "timestamp": time.time(),
                    })
                    if retry_audio:
                        await websocket.send_bytes(retry_audio)
                    continue

                code_snapshot = msg.get("code") or None
                code_language = msg.get("language") or ""
                if await _run_answer(transcript, code_snapshot, code_language):
                    break
                continue

            # Candidate answer (typed)
            if msg_type == "answer":
                answer_text = msg.get("text", "").strip()
                if not answer_text:
                    continue

                # Extract code snapshot and language from the answer message
                code_snapshot = msg.get("code") or None
                code_language = msg.get("language") or ""

                if await _run_answer(answer_text, code_snapshot, code_language):
                    break
                continue

    except GeminiUnavailableError as e:
        logger.error(
            "Gemini API not configured",
            extra={"error": str(e), "session": interview_session_id}
        )
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
                "error_code": "GEMINI_UNAVAILABLE",
            })
            await websocket.close(code=4003)
        except Exception:
            pass
        return

    except RuntimeError as e:
        logger.error(
            "Gemini call failed",
            extra={"error": str(e), "session": interview_session_id}
        )
        with contextlib.suppress(Exception):
            await websocket.send_json({
                "type": "error",
                "message": f"AI model error: {e}",
                "error_code": "GEMINI_ERROR",
            })

    except WebSocketDisconnect:
        logger.info(
            "AI interview WebSocket disconnected",
            extra={"session": interview_session_id}
        )
        # Save partial results on disconnect — state is already checkpointed
        # Update status to "paused" for resume support
        store.save_meta(interview_session_id, {
            **(store.load_meta(interview_session_id) or {}),
            "status": "paused",
            "paused_at": time.time(),
            "platform_session_id": session_id,
        })
        if session_id:
            try:
                await _save_interview_result(session_id, interview_session_id, runner)
            except Exception as e:
                logger.error("Failed to save on disconnect", extra={"error": str(e)})

    except Exception as e:
        logger.error(
            "AI interview WebSocket error",
            extra={"error": str(e), "session": interview_session_id}
        )
        with contextlib.suppress(Exception):
            await websocket.send_json({
                "type": "error",
                "message": f"Interview error: {e}",
                "error_code": "INTERNAL_ERROR",
            })

    finally:
        if websocket.client_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await websocket.close()


# ── Voice Interview WebSocket ──────────────────────────────────────────────────

@router.websocket("/ws/voice")
async def voice_interview_websocket(
    websocket: WebSocket,
    token: str = Query(default=""),
    interview_session_id: str = Query(default=""),
    session_id: str = Query(default=""),
):
    """
    Real-time voice interview via WebSocket.

    Receives binary audio chunks, returns binary TTS audio + JSON metadata.
    Supports reconnection and state recovery (P2/P3).
    """
    await websocket.accept()

    payload = _validate_ws_token(token)
    if not payload:
        await websocket.send_json({"type": "error", "message": "Invalid token"})
        await websocket.close(code=4001)
        return

    store = _get_store()

    # Try to restore from Redis checkpoint (P2)
    runner = None
    state = store.load_state(interview_session_id)
    if state:
        meta = store.load_meta(interview_session_id) or {}
        if meta.get("status") not in ("completed", "error"):
            runner = InterviewGraphRunner(
                session_id=interview_session_id,
                initial_state=state,
                platform_session_id=meta.get("platform_session_id", session_id),
                state_store=store,
            )
            runner._initialized = state.get("phase", "analyzing") != "analyzing"

    if not runner:
        await websocket.send_json({"type": "error", "message": "Interview session not found"})
        await websocket.close(code=4002)
        return

    # Get or create voice pipeline
    pipeline = VoicePipeline.from_settings()

    try:
        # Initialize if needed
        if not runner._initialized:
            opening_text = await runner.initialize()
            opening_audio = await pipeline.tts.synthesize(opening_text)
            await websocket.send_json({
                "type": "session_ready",
                "opening_text": opening_text,
                "session_id": interview_session_id,
            })
            if opening_audio:
                await websocket.send_bytes(opening_audio)

            # Generate first question
            first_q = await runner.generate_first_question()
            first_q_audio = await pipeline.tts.synthesize(first_q)
            state = runner.get_state()
            current_q = state.get("current_question", {})
            await websocket.send_json({
                "type": "question",
                "text": first_q,
                "question_id": current_q.get("id", ""),
            })
            if first_q_audio:
                await websocket.send_bytes(first_q_audio)
        else:
            # Resuming: re-send last question (P2)
            state = runner.get_state()
            current_q = state.get("current_question", {})
            if current_q:
                resume_audio = await pipeline.tts.synthesize(
                    f"Welcome back. Let's continue. {current_q.get('question', '')}"
                )
                await websocket.send_json({
                    "type": "session_restored",
                    "session_id": interview_session_id,
                    "questions_asked": state.get("questions_asked", 0),
                })
                await websocket.send_json({
                    "type": "question",
                    "text": current_q.get("question", ""),
                    "question_id": current_q.get("id", ""),
                })
                if resume_audio:
                    await websocket.send_bytes(resume_audio)

        # Main voice loop
        audio_buffer = bytearray()

        while True:
            data = await websocket.receive()

            # Binary audio data
            if data.get("bytes"):
                audio_bytes = data["bytes"]
                audio_buffer.extend(audio_bytes)
                continue

            # Text control messages
            if data.get("text"):
                try:
                    msg = json.loads(data["text"])
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")

                # Token refresh (P3)
                if msg_type == "refresh_token":
                    new_token = msg.get("token", "")
                    new_payload = _validate_ws_token(new_token)
                    if new_payload:
                        payload = new_payload
                        await websocket.send_json({"type": "token_refreshed"})
                    continue

                if msg_type == "audio_end":
                    # Process buffered audio
                    if not audio_buffer:
                        continue

                    await websocket.send_json({"type": "processing"})

                    # STT
                    transcript = await pipeline.audio_to_text(bytes(audio_buffer))
                    audio_buffer.clear()

                    if not transcript:
                        retry_text = "Could you please repeat that?"
                        await websocket.send_json({
                            "type": "stt_result",
                            "text": "",
                            "is_final": True,
                        })
                        retry_audio = await pipeline.tts.synthesize(retry_text)
                        await websocket.send_json({"type": "ai_response_text", "text": retry_text})
                        if retry_audio:
                            await websocket.send_bytes(retry_audio)
                        continue

                    await websocket.send_json({
                        "type": "stt_result",
                        "text": transcript,
                        "is_final": True,
                    })

                    # Extract code snapshot and language from the audio_end message
                    code_snapshot = msg.get("code") or None
                    code_language = msg.get("language") or ""
                    if code_snapshot and code_language:
                        runner.state["current_code_snapshot_language"] = code_language

                    # Process through interview agent
                    result = await runner.process_answer(transcript, code_snapshot=code_snapshot)
                    response_text = result.get("text", "")

                    await websocket.send_json({
                        "type": "ai_response_text",
                        "text": response_text,
                        "is_follow_up": result.get("is_follow_up", False),
                    })

                    # TTS
                    response_audio = await pipeline.tts.synthesize(response_text)
                    if response_audio:
                        await websocket.send_bytes(response_audio)

                    if result.get("should_end"):
                        await _save_interview_result(session_id, interview_session_id, runner)
                        await websocket.send_json({
                            "type": "interview_complete",
                            "report": result.get("final_report", {}),
                        })
                        break

                elif msg_type == "end_voice":
                    result = await runner._finalize()
                    await _save_interview_result(session_id, interview_session_id, runner)
                    await websocket.send_json({
                        "type": "interview_complete",
                        "report": result.get("final_report", {}),
                    })
                    break

    except GeminiUnavailableError as e:
        logger.error("Gemini API not configured (voice)", extra={"error": str(e)})
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e),
                "error_code": "GEMINI_UNAVAILABLE",
            })
            await websocket.close(code=4003)
        except Exception:
            pass

    except RuntimeError as e:
        logger.error("Gemini call failed (voice)", extra={"error": str(e)})
        with contextlib.suppress(Exception):
            await websocket.send_json({
                "type": "error",
                "message": f"AI model error: {e}",
                "error_code": "GEMINI_ERROR",
            })

    except WebSocketDisconnect:
        logger.info("Voice interview disconnected", extra={"session": interview_session_id})
        # Mark as paused for resume (P2)
        store.save_meta(interview_session_id, {
            **(store.load_meta(interview_session_id) or {}),
            "status": "paused",
            "paused_at": time.time(),
        })
    except Exception as e:
        logger.error("Voice interview error", extra={"error": str(e)})
        with contextlib.suppress(Exception):
            await websocket.send_json({
                "type": "error",
                "message": f"Interview error: {e}",
                "error_code": "INTERNAL_ERROR",
            })


# ── Helper Functions ──────────────────────────────────────────────────────────

async def _save_interview_result(
    platform_session_id: str,
    interview_session_id: str,
    runner: InterviewGraphRunner,
) -> None:
    """Save interview results back to the platform session."""
    if not platform_session_id:
        return

    try:
        state = runner.get_state()
        report = runner.get_final_report() or state.get("final_report", {})
        session_data = load_session(platform_session_id)

        if not session_data:
            return

        session_data.setdefault("aiInterview", {})
        session_data["aiInterview"][interview_session_id] = {
            "transcript": state.get("conversation_transcript", []),
            "evaluations": state.get("evaluations_history", []),
            "scores": report.get("scores", {}),
            "report": report,
            "completedAt": time.time(),
            "questionsAsked": state.get("questions_asked", 0),
            "phase": state.get("phase", "unknown"),
        }

        # Update top-level scores for compatibility with existing platform
        if report and report.get("scores"):
            scores = report["scores"]
            session_data.setdefault("scores", {})
            session_data["scores"]["technical"] = int(scores.get("technical_score", 70))
            session_data["scores"]["communication"] = int(scores.get("communication_score", 70))

        save_session(platform_session_id, session_data)
        logger.info(
            "Interview results saved",
            extra={"platform_session": platform_session_id, "interview_session": interview_session_id}
        )
    except Exception as e:
        logger.error("Failed to save interview results", extra={"error": str(e)})


def cleanup_session(interview_session_id: str) -> None:
    """Clean up an interview session from Redis."""
    store = _get_store()
    store.delete_state(interview_session_id)
