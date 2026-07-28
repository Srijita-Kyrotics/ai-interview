from __future__ import annotations

import json
import logging
import time
from typing import Any

import google.generativeai as genai
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.config import settings
from app.db import load_session, save_session
from app.helpers import decode_token, sanitize_for_ai

logger = logging.getLogger("ai_interview")

router = APIRouter()


def _make_gemini_chat(session_state: dict[str, Any], role_key: str):
    company = sanitize_for_ai(session_state.get("selectedCompany", "a tech company"))
    resume = session_state.get("resume", {})
    skills = sanitize_for_ai(", ".join(resume.get("skills", []))) or "general software engineering"
    name = resume.get("name", "the candidate")

    system_instruction = (
        f"You are Obi, a professional, friendly, and thorough AI interviewer at {company}. "
        f"You are interviewing {name} for a {role_key} role. "
        f"Their skills include: {skills}.\n\n"
        "RULES:\n"
        "1. Ask one question at a time. Wait for the candidate's answer before asking the next.\n"
        "2. Speak naturally and conversationally, like a real interviewer.\n"
        "3. Be encouraging but rigorous. If an answer is vague, ask a follow-up.\n"
        "4. For coding questions: the candidate will write code in an editor you can see. "
        "   When they share code with you, review it carefully for correctness, efficiency, and style.\n"
        "5. After 5-7 questions, say something like 'Thank you, that concludes our interview.'\n"
        "6. Keep responses concise (2-4 sentences max) unless reviewing code.\n"
        f"7. This is a {role_key} interview round.\n"
        "8. Always refer to yourself as Obi.\n\n"
        "ADAPTIVE DIFFICULTY:\n"
        "- Start with medium-difficulty questions.\n"
        "- If the candidate answers well (detailed, accurate, confident), increase difficulty.\n"
        "- If the candidate struggles (vague, incorrect, or short answers), decrease difficulty "
        "and provide a helpful hint or rephrase the question.\n"
        "- Track the candidate's performance internally. After each answer, mentally rate it "
        "as strong/moderate/weak and adjust your next question accordingly.\n"
        "- Mix question types: conceptual, practical, problem-solving, and scenario-based.\n"
        "- For technical rounds: ask about data structures, algorithms, system design, debugging, "
        "and real-world architecture. Adapt depth to the candidate's level."
    )

    model = genai.GenerativeModel(settings.gemini_model, system_instruction=system_instruction)
    return model.start_chat(history=[
        {"role": "user", "parts": ["(Interview started)"]},
        {"role": "model", "parts": [f"Hi there! I'm Obi, your AI interviewer for this {role_key} round. I'm excited to get started. Let me begin with your first question."]}
    ])


def _save_conversation(session_id: str, conversation_log: list[dict[str, str]], round_key: str,
                       latest_code: str, latest_language: str, code_review: str | None,
                       interview_metrics: dict[str, Any] | None = None):
    """Save the full interview conversation, code, and review to the session."""
    state = load_session(session_id)
    if not state:
        return

    state.setdefault("answers", {}).setdefault(round_key, [])
    state.setdefault("codingSubmissions", [])

    for entry in conversation_log:
        state["answers"][round_key].append({
            "questionIndex": len(state["answers"][round_key]),
            "answer": entry["text"] if entry["role"] == "candidate" else f"[Question] {entry['text']}",
        })

    if latest_code:
        state["codingSubmissions"].append({
            "roundKey": round_key,
            "questionIndex": 0,
            "language": latest_language,
            "code": latest_code,
        })

    # Save the full transcript and code review for the report
    state.setdefault("liveInterview", {})
    state["liveInterview"][round_key] = {
        "transcript": conversation_log,
        "code": latest_code,
        "language": latest_language,
        "codeReview": code_review,
        "completedAt": time.time(),
    }

    # Save interview metrics for scoring
    if interview_metrics:
        state.setdefault("interviewMetrics", {})
        state["interviewMetrics"][round_key] = interview_metrics

    save_session(session_id, state)


@router.websocket("/ws/interview")
async def interview_websocket(
    websocket: WebSocket,
    token: str = Query(default=""),
    session_id: str = Query(default=""),
    round_key: str = Query(default=""),
):
    await websocket.accept()

    # ── Auth ──────────────────────────────────────────────────────────────
    payload = decode_token(token)
    if not payload:
        await websocket.send_json({"type": "error", "message": "Invalid or expired token"})
        await websocket.close(code=4001)
        return

    email = payload["email"]
    state = load_session(session_id)
    if not state:
        await websocket.send_json({"type": "error", "message": "Session not found"})
        await websocket.close(code=4002)
        return
    if state.get("user_id") and state["user_id"] != email and payload.get("role") not in ("recruiter", "admin"):
        await websocket.send_json({"type": "error", "message": "Access denied"})
        await websocket.close(code=4003)
        return

    gemini_key = settings.gemini_api_key
    if not gemini_key:
        await websocket.send_json({"type": "error", "message": "Gemini API key not configured"})
        await websocket.close(code=4004)
        return

    # ── Setup Gemini ──────────────────────────────────────────────────────
    genai.configure(api_key=gemini_key)
    chat = _make_gemini_chat(state, round_key)

    # ── State ─────────────────────────────────────────────────────────────
    conversation_log: list[dict[str, str]] = []
    latest_code = ""
    latest_language = "javascript"
    code_review_text: str | None = None
    question_count = 0
    max_questions = 7
    interview_metrics: dict[str, Any] = {}

    # ── Send welcome + first question ──────────────────────────────────────
    await websocket.send_json({
        "type": "thinking",
        "timestamp": time.time(),
    })

    try:
        response = await chat.send_message_async(
            "Introduce yourself briefly as Obi and ask your first interview question."
        )
        first_q = response.text.strip()
        await websocket.send_json({
            "type": "ai_message",
            "text": first_q,
            "timestamp": time.time(),
        })
        conversation_log.append({"role": "interviewer", "text": first_q})
        question_count += 1
    except Exception as e:
        logger.error("Gemini first question failed", extra={"error": str(e)})
        error_msg = f"Gemini API failed: {e}. Please check your GEMINI_API_KEY configuration."
        await websocket.send_json({
            "type": "error",
            "message": error_msg,
            "error_code": "GEMINI_ERROR",
        })
        await websocket.close(code=4003)
        return

    # ── Main loop ─────────────────────────────────────────────────────────
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid message format"})
                continue

            msg_type = msg.get("type", "")

            # ── Code update (live streaming) ──────────────────────────────
            if msg_type == "code_update":
                latest_code = msg.get("code", "")
                latest_language = msg.get("language", "javascript")
                continue

            # ── Interview metrics from frontend ──────────────────────────
            if msg_type == "metrics":
                interview_metrics = msg.get("metrics", {})
                continue

            # ── Student answer (text or voice transcript) ─────────────────
            if msg_type == "message":
                text = msg.get("text", "").strip()
                if not text:
                    continue

                conversation_log.append({"role": "candidate", "text": text})

                # Build context for Gemini
                context_parts = []
                if latest_code:
                    context_parts.append(
                        f"[The candidate's current code in {latest_language}]:\n```\n{latest_code[:4000]}\n```"
                    )
                context_parts.append(f"Candidate's answer: {text}")

                if question_count >= max_questions:
                    context_parts.append(
                        "The candidate has answered enough questions. "
                        "Thank them and say the interview is complete. "
                        "Give a brief positive closing remark."
                    )

                prompt = "\n\n".join(context_parts)

                # Signal thinking state to frontend
                await websocket.send_json({"type": "thinking", "timestamp": time.time()})

                try:
                    response = await chat.send_message_async(prompt)
                    ai_text = response.text.strip()
                    conversation_log.append({"role": "interviewer", "text": ai_text})
                    question_count += 1

                    await websocket.send_json({
                        "type": "ai_message",
                        "text": ai_text,
                        "timestamp": time.time(),
                        "question_count": question_count,
                    })

                    if question_count >= max_questions:
                        await websocket.send_json({
                            "type": "interview_complete",
                            "timestamp": time.time(),
                        })
                        break

                except Exception as e:
                    logger.error("Gemini response failed", extra={"error": str(e)})
                    await websocket.send_json({
                        "type": "ai_message",
                        "text": "Could you repeat that? I had a small technical issue.",
                        "timestamp": time.time(),
                    })
                continue

            # ── Request code review ───────────────────────────────────────
            if msg_type == "review_code":
                code = msg.get("code", latest_code)
                language = msg.get("language", latest_language)
                if not code:
                    await websocket.send_json({"type": "error", "message": "No code to review"})
                    continue

                review_prompt = (
                    f"The candidate is finishing their coding task. "
                    f"Here is their code in {language}:\n\n```\n{code[:6000]}\n```\n\n"
                    "Please review the code. Provide:\n"
                    "1. Overall assessment (correctness, time/space complexity)\n"
                    "2. Strengths\n"
                    "3. Areas for improvement\n"
                    "4. A score out of 10\n\n"
                    "Be thorough but encouraging."
                )

                # Signal thinking state to frontend
                await websocket.send_json({"type": "thinking", "timestamp": time.time()})

                try:
                    response = await chat.send_message_async(review_prompt)
                    review_text = response.text.strip()
                    code_review_text = review_text
                    conversation_log.append({"role": "interviewer", "text": f"[Code Review] {review_text}"})

                    await websocket.send_json({
                        "type": "code_review",
                        "text": review_text,
                        "timestamp": time.time(),
                    })
                except Exception as e:
                    logger.error("Gemini code review failed", extra={"error": str(e)})
                    await websocket.send_json({"type": "error", "message": "Code review failed"})
                continue

            # ── End interview ─────────────────────────────────────────────
            if msg_type == "end_interview":
                _save_conversation(session_id, conversation_log, round_key,
                                   latest_code, latest_language, code_review_text,
                                   interview_metrics)
                await websocket.send_json({"type": "interview_ended", "timestamp": time.time()})
                break

    except WebSocketDisconnect:
        logger.info("Interview WebSocket disconnected", extra={"session_id": session_id})
    except Exception as e:
        logger.error("Interview WebSocket error", extra={"error": str(e), "session_id": session_id})
    finally:
        # Always save on disconnect (even if not ended cleanly)
        if conversation_log:
            try:
                _save_conversation(session_id, conversation_log, round_key,
                                   latest_code, latest_language, code_review_text,
                                   interview_metrics)
            except Exception as e:
                logger.error("Failed to save conversation on disconnect", extra={"error": str(e)})

        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close()
            except Exception:
                pass
