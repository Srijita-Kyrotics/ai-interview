"""
AI Interviewer FastAPI Router
==============================
Provides REST endpoints and a WebSocket for the AI interviewer.

Endpoints:
  POST /ai-interview/start         → Start a new AI interview session
  GET  /ai-interview/{session}/state → Get current session state
  GET  /ai-interview/{session}/report → Get final report
  WS   /ws/ai-interview            → Real-time interview WebSocket
  WS   /ws/ai-interview/voice      → Voice interview WebSocket

WebSocket Protocol (text mode):
  Client → Server:
    {"type": "answer", "text": "candidate answer text", "duration_ms": 5000}
    {"type": "end"}
    {"type": "ping"}

  Server → Client:
    {"type": "session_ready", "opening_text": "...", "session_id": "..."}
    {"type": "question", "text": "...", "question_id": "...", "is_follow_up": false}
    {"type": "thinking"}
    {"type": "transition", "text": "..."}
    {"type": "interview_complete", "closing_text": "...", "report": {...}}
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

import json
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from starlette.websockets import WebSocketState

from app.config import settings
from app.db import load_session, save_session
from app.helpers import decode_token
from app.resume_parser import extract_text_from_pdf_content, parse_resume_text

from app.ai_interviewer.state import make_initial_state, InterviewState
from app.ai_interviewer.graph import InterviewGraphRunner
from app.ai_interviewer.voice import VoicePipeline

logger = logging.getLogger("ai_interview.router")

router = APIRouter(prefix="/ai-interview", tags=["AI Interviewer"])

# ── In-Memory Session Store (replace with Redis in production) ────────────────
_active_runners: dict[str, InterviewGraphRunner] = {}
_voice_pipelines: dict[str, VoicePipeline] = {}


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


# ── Dependency: Auth ──────────────────────────────────────────────────────────

def get_current_user(token: str = Query(default="")) -> dict:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


# ── REST Endpoints ───────────────────────────────────────────────────────────

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
    3. Runs the setup phase (resume analysis + planning)
    4. Returns the opening message
    """
    session_data = load_session(request.session_id)
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")

    resume_parsed = session_data.get("resume", {})
    resume_raw = resume_parsed.get("rawText", "") or session_data.get("resume_raw_text", "")

    if not resume_parsed and not resume_raw:
        raise HTTPException(status_code=400, detail="No resume data found in session")

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

    # Create runner and store
    runner = InterviewGraphRunner(
        session_id=interview_session_id,
        initial_state=initial_state,
    )
    _active_runners[interview_session_id] = runner

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


@router.get("/{interview_session_id}/state")
async def get_interview_state(
    interview_session_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Get current state of an active interview session."""
    runner = _active_runners.get(interview_session_id)
    if not runner:
        raise HTTPException(status_code=404, detail="Interview session not found or expired")

    state = runner.get_state()
    return {
        "phase": state.get("phase"),
        "questions_asked": state.get("questions_asked"),
        "max_questions": state.get("max_questions"),
        "current_stage": state.get("current_stage", {}).get("name"),
        "topics_covered": state.get("memory", {}).get("topics_covered", []),
        "should_end": state.get("should_end"),
    }


@router.get("/{interview_session_id}/report")
async def get_interview_report(
    interview_session_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """Get the final interview report (only available after completion)."""
    runner = _active_runners.get(interview_session_id)
    if not runner:
        raise HTTPException(status_code=404, detail="Interview session not found")

    report = runner.get_final_report()
    if not report:
        raise HTTPException(status_code=425, detail="Interview not yet completed")

    return report


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
    """
    await websocket.accept()

    # ── Auth ──────────────────────────────────────────────────────────────
    payload = decode_token(token)
    if not payload:
        await websocket.send_json({"type": "error", "message": "Invalid token"})
        await websocket.close(code=4001)
        return

    # ── Get or Create Runner ──────────────────────────────────────────────
    runner = _active_runners.get(interview_session_id)
    if not runner:
        # Try to create session on the fly (if /start was skipped)
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
        runner = InterviewGraphRunner(session_id=new_interview_id, initial_state=initial_state)
        _active_runners[new_interview_id] = runner
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

        # ── Main Interview Loop ───────────────────────────────────────────
        while True:
            raw = await websocket.receive_text()
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

            # Candidate answer
            if msg_type == "answer":
                answer_text = msg.get("text", "").strip()
                if not answer_text:
                    continue

                # Extract code snapshot from the answer message
                code_snapshot = msg.get("code") or None

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
                    break

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
                continue

    except WebSocketDisconnect:
        logger.info(
            "AI interview WebSocket disconnected",
            extra={"session": interview_session_id}
        )
        # Save partial results on disconnect
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
        try:
            await websocket.send_json({"type": "error", "message": "An error occurred"})
        except Exception:
            pass

    finally:
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass


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
    """
    await websocket.accept()

    payload = decode_token(token)
    if not payload:
        await websocket.send_json({"type": "error", "message": "Invalid token"})
        await websocket.close(code=4001)
        return

    runner = _active_runners.get(interview_session_id)
    if not runner:
        await websocket.send_json({"type": "error", "message": "Interview session not found"})
        await websocket.close(code=4002)
        return

    # Get or create voice pipeline
    pipeline = _voice_pipelines.get(interview_session_id)
    if not pipeline:
        pipeline = VoicePipeline.from_settings()
        _voice_pipelines[interview_session_id] = pipeline

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

                    # Extract code snapshot from the audio_end message
                    code_snapshot = msg.get("code") or None

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

    except WebSocketDisconnect:
        logger.info("Voice interview disconnected", extra={"session": interview_session_id})
    except Exception as e:
        logger.error("Voice interview error", extra={"error": str(e)})
    finally:
        _voice_pipelines.pop(interview_session_id, None)
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass


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
        report = runner.get_final_report()
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
    """Clean up an interview session from memory."""
    _active_runners.pop(interview_session_id, None)
    _voice_pipelines.pop(interview_session_id, None)
