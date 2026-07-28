"""
LangGraph Node Implementations
==============================
Each node in the interview pipeline is a pure async function that
receives an InterviewState, does work, and returns a state patch.

Node execution order:
  resume_analyzer_node    → Parses & analyzes the resume
  interview_planner_node  → Generates the interview roadmap
  question_generator_node → Generates the next question
  answer_analyzer_node    → Scores a candidate answer
  follow_up_generator_node→ Decides whether to follow up or advance
  scoring_node            → Computes aggregate scores
  report_generator_node   → Generates the final hiring report
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import google.generativeai as genai

from app.ai_interviewer.state import (
    InterviewState,
    ResumeAnalysis,
    InterviewPlan,
    InterviewStage,
    QuestionRecord,
    AnswerRecord,
    AnswerEvaluation,
    FinalScores,
    FinalReport,
    InterviewMemory,
)
from app.ai_interviewer.memory import MemoryManager
from app.ai_interviewer.prompts import (
    RESUME_ANALYZER_SYSTEM,
    RESUME_ANALYZER_PROMPT,
    INTERVIEW_PLANNER_SYSTEM,
    INTERVIEW_PLANNER_PROMPT,
    QUESTION_GENERATOR_SYSTEM,
    QUESTION_GENERATOR_PROMPT,
    ANSWER_ANALYZER_SYSTEM,
    ANSWER_ANALYZER_PROMPT,
    FOLLOW_UP_GENERATOR_SYSTEM,
    FOLLOW_UP_GENERATOR_PROMPT,
    REPORT_GENERATOR_SYSTEM,
    REPORT_GENERATOR_PROMPT,
    STAGE_TRANSITION_PROMPT,
    INTERVIEW_OPENING_PROMPT,
    INTERVIEW_CLOSING_PROMPT,
)
from app.config import settings

logger = logging.getLogger("ai_interview.nodes")

# ── Gemini Helper ─────────────────────────────────────────────────────────────

def _make_model(system_instruction: str) -> genai.GenerativeModel:
    genai.configure(api_key=settings.gemini_api_key)
    return genai.GenerativeModel(
        settings.gemini_model,
        system_instruction=system_instruction,
        generation_config=genai.GenerationConfig(
            temperature=0.7,
            max_output_tokens=2048,
            response_mime_type="application/json",
        ),
    )


async def _call_gemini_json(
    system: str,
    prompt: str,
    fallback: dict,
) -> dict:
    """Call Gemini with a JSON response, return parsed dict or fallback."""
    try:
        model = _make_model(system)
        response = await model.generate_content_async(prompt)
        text = response.text.strip()
        # Strip markdown fences if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("Gemini JSON parse failed", extra={"error": str(e)})
        return fallback
    except Exception as e:
        logger.error("Gemini call failed", extra={"error": str(e)})
        return fallback


# ══════════════════════════════════════════════════════════════════════════════
# NODE 1: Resume Analyzer
# ══════════════════════════════════════════════════════════════════════════════

async def resume_analyzer_node(state: InterviewState) -> dict:
    """
    Analyzes the candidate's resume and extracts structured intelligence
    for use by all downstream nodes.
    """
    logger.info("Executing resume_analyzer_node", extra={"session": state["session_id"]})

    resume_text = state.get("resume_raw_text", "")
    parsed = state.get("resume_parsed", {})

    # Combine parsed + raw for maximum context
    enriched_text = resume_text
    if parsed:
        enriched_text = (
            f"Name: {parsed.get('name', 'Unknown')}\n"
            f"Skills: {', '.join(parsed.get('skills', []))}\n"
            f"Experience: {json.dumps(parsed.get('experience', []), indent=2)}\n"
            f"Projects: {json.dumps(parsed.get('projects', []), indent=2)}\n"
            f"Education: {json.dumps(parsed.get('education', []), indent=2)}\n"
            f"Certifications: {json.dumps(parsed.get('certifications', []), indent=2)}\n\n"
            f"Raw Resume:\n{resume_text}"
        )

    prompt = RESUME_ANALYZER_PROMPT.format(
        role=state["role"],
        company=state["company"],
        resume_text=enriched_text[:8000],  # Gemini context limit
    )

    fallback_analysis: ResumeAnalysis = {
        "candidate_name": parsed.get("name", "Candidate"),
        "years_experience": 0,
        "seniority_level": "mid",
        "strong_areas": parsed.get("skills", [])[:3],
        "weak_areas": [],
        "red_flags": [],
        "skills": [{"skill": s, "confidence": "medium", "claimed_depth": "intermediate",
                    "needs_verification": True, "follow_up_priority": 5}
                   for s in parsed.get("skills", [])[:5]],
        "projects": [{"name": p.get("name", ""), "technologies": [],
                      "claimed_impact": p.get("description", ""),
                      "unclear_points": [], "deep_dive_questions": []}
                     for p in parsed.get("projects", [])[:3]],
        "technologies": parsed.get("skills", []),
        "education": parsed.get("education", []),
        "certifications": parsed.get("certifications", []),
        "experience_entries": [{"role": e.get("role", ""), "company": e.get("company", ""),
                                "duration": e.get("duration", ""), "key_claims": []}
                               for e in parsed.get("experience", [])],
        "summary": parsed.get("summary", ""),
        "raw_text": resume_text[:1000],
    }

    result = await _call_gemini_json(
        RESUME_ANALYZER_SYSTEM,
        prompt,
        fallback_analysis,
    )

    # Normalize
    analysis: ResumeAnalysis = {
        "candidate_name": result.get("candidate_name", fallback_analysis["candidate_name"]),
        "years_experience": int(result.get("years_experience", 0)),
        "seniority_level": result.get("seniority_level", "mid"),
        "strong_areas": result.get("strong_areas", []),
        "weak_areas": result.get("weak_areas", []),
        "red_flags": result.get("red_flags", []),
        "skills": result.get("skills", fallback_analysis["skills"]),
        "projects": result.get("projects", fallback_analysis["projects"]),
        "technologies": result.get("technologies", fallback_analysis["technologies"]),
        "education": result.get("education", fallback_analysis["education"]),
        "certifications": result.get("certifications", fallback_analysis["certifications"]),
        "experience_entries": result.get("experience_entries", fallback_analysis["experience_entries"]),
        "summary": result.get("summary", fallback_analysis["summary"]),
        "raw_text": resume_text[:1000],
    }

    # Pre-populate unresolved claims from analysis
    unresolved = []
    if result.get("interview_intelligence"):
        for claim in result["interview_intelligence"].get("verify_these_claims", []):
            unresolved.append(claim)

    updated_memory = dict(state["memory"])
    updated_memory["unresolved_claims"] = unresolved

    logger.info(
        "Resume analyzed",
        extra={
            "candidate": analysis["candidate_name"],
            "seniority": analysis["seniority_level"],
            "red_flags": len(analysis["red_flags"]),
        }
    )

    return {
        "resume_analysis": analysis,
        "memory": updated_memory,
        "phase": "planning",
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 2: Interview Planner
# ══════════════════════════════════════════════════════════════════════════════

async def interview_planner_node(state: InterviewState) -> dict:
    """
    Creates the interview roadmap based on the resume analysis.
    Defines stages, focus areas, and the overall interview strategy.
    """
    logger.info("Executing interview_planner_node", extra={"session": state["session_id"]})

    analysis = state.get("resume_analysis", {})
    analysis_json = json.dumps(analysis, indent=2)[:4000]

    prompt = INTERVIEW_PLANNER_PROMPT.format(
        resume_analysis=analysis_json,
        role=state["role"],
        company=state["company"],
        max_questions=state["max_questions"],
    )

    # Fallback plan
    fallback_plan: InterviewPlan = {
        "stages": [
            {
                "id": "warmup",
                "name": "Warm-Up & Background",
                "description": "Establish rapport and confirm background",
                "topics": ["background", "experience"],
                "target_questions": 2,
                "completed": False,
            },
            {
                "id": "technical",
                "name": "Technical Deep Dive",
                "description": "Probe technical skills and project experience",
                "topics": analysis.get("technologies", ["general"])[:4],
                "target_questions": 5,
                "completed": False,
            },
            {
                "id": "problem_solving",
                "name": "Problem Solving",
                "description": "Scenario-based technical challenges",
                "topics": ["system design", "problem solving"],
                "target_questions": 3,
                "completed": False,
            },
            {
                "id": "behavioral",
                "name": "Behavioral & Culture",
                "description": "Teamwork, conflict, growth",
                "topics": ["teamwork", "failure", "growth"],
                "target_questions": 2,
                "completed": False,
            },
        ],
        "total_questions": state["max_questions"],
        "focus_areas": analysis.get("strong_areas", [])[:3],
        "opening_strategy": "Start with a broad background question to warm up",
        "closing_strategy": "End with a behavioral question about learning from failure",
        "estimated_duration_minutes": 45,
    }

    result = await _call_gemini_json(
        INTERVIEW_PLANNER_SYSTEM,
        prompt,
        fallback_plan,
    )

    # Normalize stages
    raw_stages = result.get("stages", fallback_plan["stages"])
    stages: list[InterviewStage] = []
    for s in raw_stages:
        stages.append(InterviewStage(
            id=s.get("id", str(uuid.uuid4())[:8]),
            name=s.get("name", "Stage"),
            description=s.get("description", ""),
            topics=s.get("topics", []),
            target_questions=int(s.get("target_questions", 2)),
            completed=False,
        ))

    plan: InterviewPlan = {
        "stages": stages,
        "total_questions": int(result.get("total_questions", state["max_questions"])),
        "focus_areas": result.get("focus_areas", fallback_plan["focus_areas"]),
        "opening_strategy": result.get("opening_strategy", fallback_plan["opening_strategy"]),
        "closing_strategy": result.get("closing_strategy", fallback_plan["closing_strategy"]),
        "estimated_duration_minutes": int(result.get("estimated_duration_minutes", 45)),
    }

    # Populate memory with all topics from the plan
    all_topics = []
    for stage in stages:
        all_topics.extend(stage["topics"])

    updated_memory = dict(state["memory"])
    updated_memory["topics_pending"] = list(dict.fromkeys(all_topics))  # deduplicated

    logger.info(
        "Interview plan created",
        extra={
            "stages": len(stages),
            "total_questions": plan["total_questions"],
            "focus_areas": plan["focus_areas"],
        }
    )

    return {
        "interview_plan": plan,
        "current_stage": stages[0] if stages else None,
        "current_stage_index": 0,
        "memory": updated_memory,
        "phase": "interviewing",
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 3: Question Generator
# ══════════════════════════════════════════════════════════════════════════════

async def question_generator_node(state: InterviewState) -> dict:
    """
    Generates the next interview question based on:
    - Current stage and topic
    - Previous answer quality
    - Memory (what's been covered, what's pending)
    - Resume analysis
    """
    logger.info("Executing question_generator_node", extra={"session": state["session_id"]})

    analysis = state.get("resume_analysis", {})
    plan = state.get("interview_plan", {})
    current_stage = state.get("current_stage", {})
    memory = state.get("memory", {})
    evaluations = state.get("evaluations_history", [])
    transcript = state.get("conversation_transcript", [])

    # Get last evaluation if available
    last_eval = evaluations[-1] if evaluations else {}
    last_answer = state.get("answers_history", [{}])
    last_answer_text = last_answer[-1].get("answer_text", "") if last_answer else ""

    # Build compressed conversation history
    mem_mgr = MemoryManager(memory, current_stage.get("topics", []))
    conversation_history = mem_mgr.get_compression_context(transcript, max_turns=4)

    # Build resume summary
    resume_summary = (
        f"Name: {analysis.get('candidate_name', 'Candidate')}\n"
        f"Level: {analysis.get('seniority_level', 'mid')}\n"
        f"Strong Areas: {', '.join(analysis.get('strong_areas', [])[:3])}\n"
        f"Red Flags: {', '.join(analysis.get('red_flags', [])[:2])}\n"
        f"Projects: {', '.join([p.get('name', '') for p in analysis.get('projects', [])[:2]])}"
    )

    mem_summary = mem_mgr.get_summary_for_prompt()

    prompt = QUESTION_GENERATOR_PROMPT.format(
        candidate_name=analysis.get("candidate_name", "the candidate"),
        role=state["role"],
        current_stage=current_stage.get("name", "General"),
        stage_topics=", ".join(current_stage.get("topics", [])),
        questions_asked=state["questions_asked"],
        max_questions=state["max_questions"],
        resume_summary=resume_summary,
        conversation_history=conversation_history,
        topics_covered=", ".join(mem_summary["topics_covered"]),
        topics_pending=", ".join(mem_summary["topics_pending"]),
        strengths="; ".join(mem_summary["strengths"]),
        weaknesses="; ".join(mem_summary["weaknesses"]),
        unresolved_claims="; ".join(mem_summary["unresolved_claims"]),
        last_answer=last_answer_text[:500] if last_answer_text else "N/A",
        last_technical_score=last_eval.get("technical_accuracy", "N/A"),
        last_depth_score=last_eval.get("depth", "N/A"),
        last_missing_points=", ".join(last_eval.get("missing_points", [])),
    )

    fallback_question = {
        "question_text": f"Can you walk me through one of your most challenging projects?",
        "intent": "deep_dive",
        "topic": "projects",
        "rationale": "Fallback: general project deep-dive",
        "difficulty": "medium",
        "expected_answer_signals": ["specific project details", "technical challenges", "outcomes"],
    }

    result = await _call_gemini_json(
        QUESTION_GENERATOR_SYSTEM,
        prompt,
        fallback_question,
    )

    question_id = str(uuid.uuid4())
    question_record = QuestionRecord(
        id=question_id,
        question=result.get("question_text", fallback_question["question_text"]),
        stage=current_stage.get("id", "general"),
        topic=result.get("topic", "general"),
        asked_at=time.time(),
        intent=result.get("intent", "technical"),
    )

    # Update memory
    mem_mgr.mark_question_asked(question_id, result.get("topic", "general"))

    # Add to transcript
    transcript_entry = {
        "role": "interviewer",
        "text": question_record["question"],
        "ts": time.time(),
        "question_id": question_id,
    }
    updated_transcript = list(state.get("conversation_transcript", [])) + [transcript_entry]

    updated_questions = list(state.get("questions_history", [])) + [question_record]

    logger.info(
        "Question generated",
        extra={
            "intent": question_record["intent"],
            "topic": question_record["topic"],
            "difficulty": result.get("difficulty", "medium"),
        }
    )

    return {
        "current_question": question_record,
        "questions_history": updated_questions,
        "conversation_transcript": updated_transcript,
        "memory": mem_mgr.get_full_memory(),
        "question_started_at": time.time(),
        "ai_response_text": question_record["question"],
        "questions_asked": state["questions_asked"] + 1,
        "last_activity_at": time.time(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 4: Answer Analyzer
# ══════════════════════════════════════════════════════════════════════════════

async def answer_analyzer_node(state: InterviewState) -> dict:
    """
    Evaluates the candidate's answer across multiple dimensions:
    technical accuracy, depth, clarity, confidence, completeness, communication.
    Returns structured scoring and follow-up signals.
    """
    logger.info("Executing answer_analyzer_node", extra={"session": state["session_id"]})

    current_question = state.get("current_question", {})
    current_answer = state.get("current_answer", {})
    analysis = state.get("resume_analysis", {})
    current_stage = state.get("current_stage", {})

    if not current_question or not current_answer:
        logger.warning("Missing question or answer in answer_analyzer_node")
        return {}

    # Build resume context for verification
    resume_context = (
        f"Claimed Skills: {', '.join(analysis.get('technologies', [])[:10])}\n"
        f"Projects: {json.dumps([p.get('name') for p in analysis.get('projects', [])[:3]])}\n"
        f"Red Flags: {', '.join(analysis.get('red_flags', []))}"
    )

    # Get expected signals from question record
    questions_history = state.get("questions_history", [])
    expected_signals = []
    for q in questions_history:
        if q["id"] == current_question.get("id"):
            break

    # Get code snapshot if available
    code_snapshot = state.get("current_code_snapshot", "") or current_answer.get("code_snapshot", "") or ""

    prompt = ANSWER_ANALYZER_PROMPT.format(
        question_text=current_question.get("question", ""),
        question_intent=current_question.get("intent", "technical"),
        stage_name=current_stage.get("name", "General"),
        expected_signals=", ".join(expected_signals) if expected_signals else "Technical accuracy, depth, and clarity",
        answer_text=current_answer.get("answer_text", ""),
        code_snapshot=code_snapshot if code_snapshot else "No code provided.",
        resume_context=resume_context,
    )

    fallback_eval: AnswerEvaluation = {
        "question_id": current_question.get("id", ""),
        "technical_accuracy": 5,
        "depth": 5,
        "clarity": 5,
        "confidence": 5,
        "completeness": 5,
        "communication_quality": 5,
        "missing_points": [],
        "positive_signals": [],
        "red_flags": [],
        "suggested_follow_ups": [],
        "overall_quality": "average",
    }

    result = await _call_gemini_json(
        ANSWER_ANALYZER_SYSTEM,
        prompt,
        fallback_eval,
    )

    evaluation: AnswerEvaluation = {
        "question_id": current_question.get("id", ""),
        "technical_accuracy": int(result.get("technical_accuracy", 5)),
        "depth": int(result.get("depth", 5)),
        "clarity": int(result.get("clarity", 5)),
        "confidence": int(result.get("confidence", 5)),
        "completeness": int(result.get("completeness", 5)),
        "communication_quality": int(result.get("communication_quality", 5)),
        "missing_points": result.get("missing_points", []),
        "positive_signals": result.get("positive_signals", []),
        "red_flags": result.get("red_flags", []),
        "suggested_follow_ups": result.get("suggested_follow_ups", []),
        "overall_quality": result.get("overall_quality", "average"),
    }

    # Update memory with evaluation insights
    memory = state.get("memory", {})
    mem_mgr = MemoryManager(memory, [])
    mem_mgr.process_evaluation(evaluation, current_question.get("topic", "general"))

    updated_evaluations = list(state.get("evaluations_history", [])) + [evaluation]

    # Signal whether a follow-up is needed
    should_follow_up = (
        result.get("should_dig_deeper", False) or
        evaluation["depth"] < 6 or
        len(evaluation["red_flags"]) > 0 or
        len(evaluation["missing_points"]) > 1
    )

    logger.info(
        "Answer evaluated",
        extra={
            "technical": evaluation["technical_accuracy"],
            "depth": evaluation["depth"],
            "overall": evaluation["overall_quality"],
            "should_follow_up": should_follow_up,
        }
    )

    return {
        "current_evaluation": evaluation,
        "evaluations_history": updated_evaluations,
        "memory": mem_mgr.get_full_memory(),
        "_should_follow_up": should_follow_up,  # routing signal
        "_dig_deeper_angle": result.get("dig_deeper_angle", ""),
        "last_activity_at": time.time(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 5: Follow-Up Generator
# ══════════════════════════════════════════════════════════════════════════════

async def follow_up_generator_node(state: InterviewState) -> dict:
    """
    Generates a targeted follow-up question when the previous answer
    was shallow, vague, or contained red flags.
    
    This is the most important node for interview quality — it's what 
    separates a real interviewer from a scripted one.
    """
    logger.info("Executing follow_up_generator_node", extra={"session": state["session_id"]})

    current_question = state.get("current_question", {})
    current_answer = state.get("current_answer", {})
    current_eval = state.get("current_evaluation", {})
    analysis = state.get("resume_analysis", {})
    memory = state.get("memory", {})

    # Get code snapshot if available
    code_snapshot = state.get("current_code_snapshot", "") or current_answer.get("code_snapshot", "") or ""

    prompt = FOLLOW_UP_GENERATOR_PROMPT.format(
        original_question=current_question.get("question", ""),
        candidate_answer=current_answer.get("answer_text", ""),
        code_snapshot=code_snapshot if code_snapshot else "No code provided.",
        technical_accuracy=current_eval.get("technical_accuracy", 5),
        depth=current_eval.get("depth", 5),
        missing_points=", ".join(current_eval.get("missing_points", [])),
        red_flags=", ".join(current_eval.get("red_flags", [])),
        dig_deeper_angle=state.get("_dig_deeper_angle", ""),
        claimed_skills=", ".join(analysis.get("technologies", [])[:8]),
        topics_covered=", ".join(memory.get("topics_covered", [])[-5:]),
    )

    fallback_follow_up = {
        "follow_up_question": "Could you elaborate on that? Specifically, what were the technical challenges you faced?",
        "why_this_question": "Answer was vague, need more specifics",
        "escalation_level": 1,
        "is_challenging": False,
    }

    result = await _call_gemini_json(
        FOLLOW_UP_GENERATOR_SYSTEM,
        prompt,
        fallback_follow_up,
    )

    follow_up_text = result.get("follow_up_question", fallback_follow_up["follow_up_question"])

    # Create a new question record for the follow-up
    question_id = str(uuid.uuid4())
    follow_up_record = QuestionRecord(
        id=question_id,
        question=follow_up_text,
        stage=current_question.get("stage", "general"),
        topic=current_question.get("topic", "general") + "_followup",
        asked_at=time.time(),
        intent="probe",
    )

    # Update memory
    mem_mgr = MemoryManager(memory, [])
    mem_mgr.mark_question_asked(question_id, follow_up_record["topic"])

    # Add to transcript
    transcript_entry = {
        "role": "interviewer",
        "text": follow_up_text,
        "ts": time.time(),
        "question_id": question_id,
        "is_follow_up": True,
    }
    updated_transcript = list(state.get("conversation_transcript", [])) + [transcript_entry]
    updated_questions = list(state.get("questions_history", [])) + [follow_up_record]

    logger.info(
        "Follow-up generated",
        extra={
            "escalation_level": result.get("escalation_level", 1),
            "is_challenging": result.get("is_challenging", False),
        }
    )

    return {
        "current_question": follow_up_record,
        "questions_history": updated_questions,
        "conversation_transcript": updated_transcript,
        "memory": mem_mgr.get_full_memory(),
        "ai_response_text": follow_up_text,
        "questions_asked": state["questions_asked"] + 1,
        "last_activity_at": time.time(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# NODE 6: Scoring Node
# ══════════════════════════════════════════════════════════════════════════════

async def scoring_node(state: InterviewState) -> dict:
    """
    Computes aggregate scores across all dimensions by aggregating 
    all answer evaluations from the session.
    """
    logger.info("Executing scoring_node", extra={"session": state["session_id"]})

    evaluations = state.get("evaluations_history", [])

    if not evaluations:
        default_scores = FinalScores(
            technical_score=50.0,
            communication_score=50.0,
            confidence_score=50.0,
            problem_solving_score=50.0,
            behavioral_score=50.0,
            depth_score=50.0,
            overall_score=50.0,
            recommendation="Lean Reject",
        )
        return {"_computed_scores": default_scores}

    # Aggregate raw scores
    n = len(evaluations)
    tech_avg = sum(e.get("technical_accuracy", 5) for e in evaluations) / n * 10
    comm_avg = sum(e.get("communication_quality", 5) for e in evaluations) / n * 10
    conf_avg = sum(e.get("confidence", 5) for e in evaluations) / n * 10
    depth_avg = sum(e.get("depth", 5) for e in evaluations) / n * 10
    clarity_avg = sum(e.get("clarity", 5) for e in evaluations) / n * 10
    completeness_avg = sum(e.get("completeness", 5) for e in evaluations) / n * 10

    # Problem solving = blend of technical + depth + completeness
    problem_solving = (tech_avg * 0.4 + depth_avg * 0.35 + completeness_avg * 0.25)

    # Behavioral = blend of confidence + communication + clarity
    behavioral = (conf_avg * 0.4 + comm_avg * 0.35 + clarity_avg * 0.25)

    # Overall weighted average
    overall = (
        tech_avg * 0.30 +
        depth_avg * 0.20 +
        problem_solving * 0.20 +
        comm_avg * 0.15 +
        conf_avg * 0.10 +
        behavioral * 0.05
    )

    # Determine recommendation
    if overall >= 82:
        recommendation = "Strong Hire"
    elif overall >= 70:
        recommendation = "Hire"
    elif overall >= 58:
        recommendation = "Lean Hire"
    elif overall >= 45:
        recommendation = "Lean Reject"
    else:
        recommendation = "Reject"

    scores = FinalScores(
        technical_score=round(tech_avg, 1),
        communication_score=round(comm_avg, 1),
        confidence_score=round(conf_avg, 1),
        problem_solving_score=round(problem_solving, 1),
        behavioral_score=round(behavioral, 1),
        depth_score=round(depth_avg, 1),
        overall_score=round(overall, 1),
        recommendation=recommendation,
    )

    logger.info(
        "Scores computed",
        extra={
            "overall": scores["overall_score"],
            "recommendation": scores["recommendation"],
        }
    )

    return {"_computed_scores": scores}


# ══════════════════════════════════════════════════════════════════════════════
# NODE 7: Report Generator
# ══════════════════════════════════════════════════════════════════════════════

async def report_generator_node(state: InterviewState) -> dict:
    """
    Generates the final comprehensive hiring report.
    This is the deliverable for recruiters and hiring managers.
    """
    logger.info("Executing report_generator_node", extra={"session": state["session_id"]})

    analysis = state.get("resume_analysis", {})
    scores = state.get("_computed_scores", {})
    evaluations = state.get("evaluations_history", [])
    transcript = state.get("conversation_transcript", [])
    questions = state.get("questions_history", [])

    # Build transcript summary
    transcript_pairs = []
    for i, entry in enumerate(transcript):
        text = entry.get("text", "")[:300]
        role = entry.get("role", "")
        transcript_pairs.append(f"{role.upper()}: {text}")
    transcript_summary = "\n".join(transcript_pairs[-20:])  # last 20 turns

    # Build evaluations summary
    eval_summaries = []
    for i, ev in enumerate(evaluations[:8]):
        q = questions[i] if i < len(questions) else {}
        eval_summaries.append(
            f"Q{i+1} [{q.get('topic', 'general')}]: "
            f"Technical={ev.get('technical_accuracy', 0)}/10, "
            f"Depth={ev.get('depth', 0)}/10, "
            f"Quality={ev.get('overall_quality', 'average')}, "
            f"Missing: {', '.join(ev.get('missing_points', [])[:2])}"
        )
    evaluations_summary = "\n".join(eval_summaries)

    # Build code snapshots summary from answer history
    answers = state.get("answers_history", [])
    code_snapshots = []
    for i, ans in enumerate(answers):
        snap = ans.get("code_snapshot", "")
        if snap:
            q_text = ans.get("question_text", f"Q{i+1}")
            code_snapshots.append(f"--- Code for: {q_text[:80]} ---\n{snap[:2000]}")
    code_snapshots_summary = "\n\n".join(code_snapshots) if code_snapshots else "No code was submitted during the interview."

    # Duration
    start = state.get("interview_started_at", time.time())
    duration_secs = time.time() - start
    duration_minutes = int(duration_secs / 60)

    prompt = REPORT_GENERATOR_PROMPT.format(
        candidate_name=analysis.get("candidate_name", "Candidate"),
        role=state["role"],
        company=state["company"],
        duration_minutes=duration_minutes,
        total_questions=state["questions_asked"],
        resume_analysis=json.dumps(analysis, indent=2)[:2000],
        transcript_summary=transcript_summary,
        evaluations_summary=evaluations_summary,
        code_snapshots_summary=code_snapshots_summary[:4000],
        technical_score=scores.get("technical_score", 50),
        communication_score=scores.get("communication_score", 50),
        confidence_score=scores.get("confidence_score", 50),
        problem_solving_score=scores.get("problem_solving_score", 50),
        behavioral_score=scores.get("behavioral_score", 50),
        overall_score=scores.get("overall_score", 50),
    )

    fallback_report_data = {
        "strengths": analysis.get("strong_areas", ["Unable to determine"]),
        "weaknesses": analysis.get("weak_areas", ["Unable to determine"]),
        "areas_for_improvement": ["Further technical depth in core areas"],
        "detailed_summary": "Interview data was insufficient for a detailed assessment.",
        "recommendation": scores.get("recommendation", "Lean Reject"),
        "recommendation_rationale": "Based on aggregate interview scores.",
        "standout_moments": [],
        "risk_factors": [],
        "suggested_onboarding_focus": [],
    }

    result = await _call_gemini_json(
        REPORT_GENERATOR_SYSTEM,
        prompt,
        fallback_report_data,
    )

    report: FinalReport = {
        "candidate_name": analysis.get("candidate_name", "Candidate"),
        "session_id": state["session_id"],
        "interview_duration_seconds": duration_secs,
        "scores": scores,
        "strengths": result.get("strengths", fallback_report_data["strengths"]),
        "weaknesses": result.get("weaknesses", fallback_report_data["weaknesses"]),
        "areas_for_improvement": result.get("areas_for_improvement", []),
        "detailed_summary": result.get("detailed_summary", ""),
        "question_records": list(questions),
        "answer_evaluations": list(evaluations),
        "recommendation_rationale": result.get("recommendation_rationale", ""),
        "generated_at": time.time(),
    }

    logger.info(
        "Final report generated",
        extra={
            "candidate": report["candidate_name"],
            "recommendation": scores.get("recommendation"),
            "overall_score": scores.get("overall_score"),
        }
    )

    return {
        "final_report": report,
        "phase": "completed",
        "should_end": True,
    }


# ══════════════════════════════════════════════════════════════════════════════
# HELPER NODES
# ══════════════════════════════════════════════════════════════════════════════

async def stage_advance_node(state: InterviewState) -> dict:
    """
    Checks if we should advance to the next interview stage.
    Returns updated stage info and a natural transition message.
    """
    plan = state.get("interview_plan", {})
    stages = plan.get("stages", [])
    current_idx = state.get("current_stage_index", 0)
    current_stage = state.get("current_stage", {})
    analysis = state.get("resume_analysis", {})

    # Check if we've exhausted questions for the current stage
    stage_q_count = sum(
        1 for q in state.get("questions_history", [])
        if q.get("stage") == current_stage.get("id")
    )
    target = current_stage.get("target_questions", 2)

    if stage_q_count < target:
        return {}  # Stay in current stage

    # Mark current stage complete
    next_idx = current_idx + 1
    if next_idx >= len(stages):
        return {"should_end": True}  # All stages done

    next_stage = stages[next_idx]

    # Generate transition message
    prompt = STAGE_TRANSITION_PROMPT.format(
        current_stage=current_stage.get("name", ""),
        next_stage=next_stage.get("name", ""),
        candidate_name=analysis.get("candidate_name", ""),
    )
    result = await _call_gemini_json(
        "You are a professional interviewer transitioning between topics.",
        prompt,
        {"transition_text": f"Great, let's move on to {next_stage['name']}."},
    )

    transition_text = result.get("transition_text", f"Great, let's shift to {next_stage['name']}.")

    transcript_entry = {
        "role": "interviewer",
        "text": transition_text,
        "ts": time.time(),
        "is_transition": True,
    }
    updated_transcript = list(state.get("conversation_transcript", [])) + [transcript_entry]

    return {
        "current_stage_index": next_idx,
        "current_stage": next_stage,
        "conversation_transcript": updated_transcript,
        "ai_response_text": transition_text,
    }


async def opening_node(state: InterviewState) -> dict:
    """Generates the opening message for the interview."""
    logger.info("Executing opening_node", extra={"session": state["session_id"]})

    analysis = state.get("resume_analysis", {})
    plan = state.get("interview_plan", {})
    stages = plan.get("stages", [])
    first_stage = stages[0] if stages else {}

    seniority_map = {
        "junior": "Mid-Level",
        "mid": "Senior",
        "senior": "Staff",
        "staff": "Principal",
    }
    seniority = seniority_map.get(analysis.get("seniority_level", "mid"), "Senior")

    prompt = INTERVIEW_OPENING_PROMPT.format(
        seniority=seniority,
        company=state["company"],
        candidate_name=analysis.get("candidate_name", ""),
        role=state["role"],
        opening_strategy=plan.get("opening_strategy", "Start with background"),
        first_topic=first_stage.get("topics", ["your background"])[0],
    )

    result = await _call_gemini_json(
        "You are a professional technical interviewer opening the interview.",
        prompt,
        {"opening_text": f"Hi! I'm Alex, a Senior Engineer here. I'll be conducting your {state['role']} interview today. Let's start — can you tell me a bit about yourself and what you've been working on recently?"},
    )

    opening_text = result.get("opening_text", "")

    transcript_entry = {
        "role": "interviewer",
        "text": opening_text,
        "ts": time.time(),
        "is_opening": True,
    }

    return {
        "ai_response_text": opening_text,
        "conversation_transcript": [transcript_entry],
        "last_activity_at": time.time(),
    }


async def closing_node(state: InterviewState) -> dict:
    """Generates the closing message for the interview."""
    logger.info("Executing closing_node", extra={"session": state["session_id"]})

    analysis = state.get("resume_analysis", {})
    memory = state.get("memory", {})

    overall_quality = "good"
    if memory.get("positive_moments") and len(memory["positive_moments"]) > len(memory.get("concerning_moments", [])):
        overall_quality = "strong"
    elif len(memory.get("concerning_moments", [])) > len(memory.get("positive_moments", [])):
        overall_quality = "average"

    prompt = INTERVIEW_CLOSING_PROMPT.format(
        candidate_name=analysis.get("candidate_name", ""),
        overall_quality=overall_quality,
        positives=", ".join(memory.get("positive_moments", [])[:2]),
    )

    result = await _call_gemini_json(
        "You are a professional technical interviewer closing the interview.",
        prompt,
        {"closing_text": "Thank you so much for your time today. It was great chatting with you. Our team will be in touch about next steps soon. Good luck!"},
    )

    closing_text = result.get("closing_text", "")

    transcript_entry = {
        "role": "interviewer",
        "text": closing_text,
        "ts": time.time(),
        "is_closing": True,
    }
    updated_transcript = list(state.get("conversation_transcript", [])) + [transcript_entry]

    return {
        "ai_response_text": closing_text,
        "conversation_transcript": updated_transcript,
        "should_end": True,
        "last_activity_at": time.time(),
    }
