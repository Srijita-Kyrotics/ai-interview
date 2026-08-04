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

LLM calls go through the provider abstraction layer (llm_providers.py).
Nodes do not know which LLM provider is being used.
"""

from __future__ import annotations

import json
import logging
import time
import uuid

from app.ai_interviewer.memory import MemoryManager
from app.ai_interviewer.communication_analyzer import analyze_communication
from app.ai_interviewer.prompts import (
    ANSWER_ANALYZER_PROMPT,
    ANSWER_ANALYZER_SYSTEM,
    CLAIM_EXTRACTOR_PROMPT,
    CLAIM_EXTRACTOR_SYSTEM,
    CLAIM_VERIFIER_PROMPT,
    CLAIM_VERIFIER_SYSTEM,
    CODING_PROBLEM_GENERATOR_PROMPT,
    CODING_PROBLEM_GENERATOR_SYSTEM,
    CONTRADICTION_DETECTOR_PROMPT,
    CONTRADICTION_DETECTOR_SYSTEM,
    DIFFICULTY_GUIDANCE,
    FOLLOW_UP_GENERATOR_PROMPT,
    FOLLOW_UP_GENERATOR_SYSTEM,
    INTERVIEW_CLOSING_PROMPT,
    INTERVIEW_OPENING_PROMPT,
    INTERVIEW_PLANNER_PROMPT,
    INTERVIEW_PLANNER_SYSTEM,
    INTERVIEW_REPLANNER_PROMPT,
    INTERVIEW_REPLANNER_SYSTEM,
    QUESTION_GENERATOR_PROMPT,
    QUESTION_GENERATOR_SYSTEM,
    REPORT_GENERATOR_PROMPT,
    REPORT_GENERATOR_SYSTEM,
    RESUME_ANALYZER_PROMPT,
    RESUME_ANALYZER_SYSTEM,
    STAGE_TRANSITION_PROMPT,
    SYSTEM_DESIGN_EVALUATOR_PROMPT,
    SYSTEM_DESIGN_EVALUATOR_SYSTEM,
)
from app.ai_interviewer.state import (
    AnswerEvaluation,
    CandidateFact,
    CodingProblem,
    CodingSubmission,
    DifficultyLevel,
    FinalReport,
    FinalScores,
    InterviewPlan,
    InterviewStage,
    InterviewState,
    QuestionRecord,
    ResumeAnalysis,
    ResumeClaim,
)

logger = logging.getLogger("ai_interview.nodes")

# ── LLM Provider Abstraction ──────────────────────────────────────────────────
# Nodes call _call_llm_json() which routes through the provider registry.
# The registry handles failover, retry, and circuit breaking.

class GeminiUnavailableError(Exception):
    """Raised when no LLM provider is configured or all providers are unavailable."""
    pass


async def _call_llm_json(system: str, prompt: str) -> dict:
    """
    Call an LLM with a JSON response, return parsed dict.

    Routes through the provider registry which handles:
    - Provider selection (Gemini > OpenAI > Claude)
    - Automatic failover on errors
    - Retry with exponential backoff
    - Circuit breaker protection

    Raises GeminiUnavailableError if no providers are available.
    Raises RuntimeError if all providers fail.
    """
    from app.ai_interviewer.llm_providers import (
        LLMProviderError,
        LLMProviderUnavailableError,
        get_llm_registry,
    )

    registry = get_llm_registry()

    if not registry.available_providers:
        raise GeminiUnavailableError(
            "No LLM providers are configured. "
            "Obi requires at least one LLM API key to function. "
            "Set GEMINI_API_KEY, OPENAI_API_KEY, or CLAUDE_API_KEY."
        )

    try:
        return await registry.generate_json(system, prompt)
    except LLMProviderUnavailableError as e:
        raise GeminiUnavailableError(str(e)) from e
    except LLMProviderError as e:
        raise RuntimeError(f"LLM call failed: {e}") from e


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

    result = await _call_llm_json(RESUME_ANALYZER_SYSTEM, prompt)

    # Normalize — Gemini must return all required fields, no silent fallbacks
    analysis: ResumeAnalysis = {
        "candidate_name": result.get("candidate_name", parsed.get("name", "Candidate")),
        "years_experience": int(result.get("years_experience", 0)),
        "seniority_level": result.get("seniority_level", "mid"),
        "strong_areas": result.get("strong_areas", []),
        "weak_areas": result.get("weak_areas", []),
        "red_flags": result.get("red_flags", []),
        "skills": result.get("skills", []),
        "projects": result.get("projects", []),
        "technologies": result.get("technologies", parsed.get("skills", [])),
        "education": result.get("education", parsed.get("education", [])),
        "certifications": result.get("certifications", parsed.get("certifications", [])),
        "experience_entries": result.get("experience_entries", []),
        "summary": result.get("summary", ""),
        "raw_text": resume_text[:1000],
    }

    # Pre-populate unresolved claims from analysis
    unresolved = []
    if result.get("interview_intelligence"):
        for claim in result["interview_intelligence"].get("verify_these_claims", []):
            unresolved.append(claim)

    updated_memory = dict(state["memory"])
    updated_memory["unresolved_claims"] = unresolved

    # ── Feature 1: Extract structured resume claims ───────────────────────
    claim_prompt = CLAIM_EXTRACTOR_PROMPT.format(
        resume_analysis=json.dumps(result, indent=2)[:4000],
        role=state["role"],
    )
    claim_result = await _call_llm_json(
        CLAIM_EXTRACTOR_SYSTEM,
        claim_prompt,
    )

    resume_claims: list[ResumeClaim] = []
    for raw_claim in claim_result.get("claims", []):
        claim_id = str(uuid.uuid4())[:8]
        resume_claims.append(ResumeClaim(
            claim_id=claim_id,
            claim_text=raw_claim.get("claim_text", ""),
            source=raw_claim.get("source", "resume"),
            skill=raw_claim.get("skill", ""),
            verification_status="UNVERIFIED",
            verification_evidence=[],
            asked_question_ids=[],
        ))

    # ── Feature 4: Seed difficulty from resume seniority ──────────────────
    seniority = result.get("seniority_level", "mid")
    seniority_map = {"junior": 1, "mid": 2, "senior": 3, "staff": 4}
    level_num = seniority_map.get(seniority, 2)
    level_map = {1: "beginner", 2: "intermediate", 3: "advanced", 4: "expert"}
    difficulty = DifficultyLevel(
        level=level_map[level_num],
        level_numeric=level_num,
        overall_mastery=5.0,
        resume_seniority=seniority,
        consecutive_strong=0,
        consecutive_weak=0,
    )

    logger.info(
        "Resume analyzed",
        extra={
            "candidate": analysis["candidate_name"],
            "seniority": analysis["seniority_level"],
            "red_flags": len(analysis["red_flags"]),
            "claims_extracted": len(resume_claims),
        }
    )

    return {
        "resume_analysis": analysis,
        "memory": updated_memory,
        "resume_claims": resume_claims,
        "difficulty_level": difficulty,
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

    result = await _call_llm_json(INTERVIEW_PLANNER_SYSTEM, prompt)

    # Normalize stages — Gemini must return stages, no silent fallback
    raw_stages = result.get("stages", [])
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
        "focus_areas": result.get("focus_areas", []),
        "opening_strategy": result.get("opening_strategy", ""),
        "closing_strategy": result.get("closing_strategy", ""),
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
    - Difficulty level (Feature 4)
    - Topic mastery (Feature 2)
    - Claim verification status (Feature 1)
    """
    logger.info("Executing question_generator_node", extra={"session": state["session_id"]})

    analysis = state.get("resume_analysis", {})
    state.get("interview_plan", {})
    current_stage = state.get("current_stage", {})
    memory = state.get("memory", {})
    evaluations = state.get("evaluations_history", [])
    transcript = state.get("conversation_transcript", [])

    # Get last evaluation if available
    last_eval = evaluations[-1] if evaluations else {}
    last_answer = state.get("answers_history", [{}])
    last_answer_text = last_answer[-1].get("answer_text", "") if last_answer else ""

    # Build compressed conversation history
    mem_mgr = MemoryManager(
        memory,
        current_stage.get("topics", []),
        resume_claims=state.get("resume_claims", []),
        topic_mastery=state.get("topic_mastery", {}),
        candidate_facts=state.get("candidate_facts", []),
        difficulty_level=state.get("difficulty_level", DifficultyLevel(
            level="intermediate", level_numeric=2, overall_mastery=5.0,
            resume_seniority="mid", consecutive_strong=0, consecutive_weak=0,
        )),
        code_history=state.get("code_history", []),
    )
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

    # ── Feature 4: Get difficulty guidance ────────────────────────────────
    difficulty_level = state.get("difficulty_level", {})
    current_diff = difficulty_level.get("level", "intermediate")
    difficulty_hint = DIFFICULTY_GUIDANCE.get(current_diff, DIFFICULTY_GUIDANCE["intermediate"])

    # ── Feature 2: Get mastery context ────────────────────────────────────
    state.get("topic_mastery", {})
    mastery_context = ""
    weak_topics = mem_mgr.get_weak_mastery_topics(threshold=5.0)
    strong_topics = mem_mgr.get_strong_mastery_topics(threshold=8.0)
    if weak_topics:
        mastery_context += f"LOW MASTERY (needs more questions): {', '.join(weak_topics)}. "
    if strong_topics:
        mastery_context += f"HIGH MASTERY (can go deeper or move on): {', '.join(strong_topics)}. "

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

    # Append difficulty and mastery guidance to prompt
    prompt += f"\n\nDIFFICULTY GUIDANCE (current level: {current_diff}):\n{difficulty_hint}"
    if mastery_context:
        prompt += f"\n\nTOPIC MASTERY:\n{mastery_context}"

    # ── Feature 7: System design mode detection ───────────────────────────
    is_system_design = state.get("is_system_design_mode", False)
    if is_system_design:
        prompt += (
            "\n\nSYSTEM DESIGN MODE ACTIVE: This question should be a system design "
            "question. Ask the candidate to design a system related to their experience "
            "or the target role. Focus on architecture, scalability, tradeoffs."
        )

    result = await _call_llm_json(QUESTION_GENERATOR_SYSTEM, prompt)

    question_id = str(uuid.uuid4())
    question_record = QuestionRecord(
        id=question_id,
        question=result.get("question_text", ""),
        stage=current_stage.get("id", "general"),
        topic=result.get("topic", "general"),
        asked_at=time.time(),
        intent=result.get("intent", "technical"),
    )

    # ── Feature 9: In a coding stage, the question is the live-coding problem ──
    problem_updates: dict = {}
    if _is_coding_stage(current_stage):
        active_problem = state.get("active_coding_problem")
        if not (active_problem and active_problem.get("description")):
            problem_updates = await coding_problem_generator_node(state)
            active_problem = problem_updates.get("active_coding_problem")
        if active_problem and active_problem.get("description"):
            problem_title = active_problem.get("title", "Coding Challenge")
            question_record = QuestionRecord(
                id=question_id,
                question=(
                    f"Please solve the following coding problem: {problem_title}\n\n"
                    f"{active_problem.get('description', '')}"
                ),
                stage=current_stage.get("id", "general"),
                topic=f"coding:{active_problem.get('topic', 'algorithms')}",
                asked_at=time.time(),
                intent="coding",
            )
            result["topic"] = question_record["topic"]

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
        "active_coding_problem": problem_updates.get("active_coding_problem"),
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

    # Get expected signals from the question's intent (deterministic, so the
    # evaluator calibrates against the right bar for this question type).
    _INTENT_SIGNALS = {
        "technical": "Accurate technical explanation, concrete examples, complexity awareness",
        "probe": "Specific details, honest admission of limits, no vague buzzwords",
        "verify": "Consistency with resume claims, concrete evidence of real experience",
        "deep_dive": "Tradeoffs, alternatives, design decisions, failure modes",
        "behavioral": "Situation-action-outcome structure, personal contribution, measurable impact",
        "coding": "Correct algorithm, edge cases, efficient complexity, clean code",
    }
    expected_signals = [_INTENT_SIGNALS.get(current_question.get("intent", "technical"), _INTENT_SIGNALS["technical"])]

    # Get code snapshot if available
    code_snapshot = state.get("current_code_snapshot", "") or current_answer.get("code_snapshot", "") or ""

    # ── Objective communication / prosody analysis ──────────────────────
    comm = analyze_communication(
        current_answer.get("answer_text", ""),
        duration_seconds=current_answer.get("duration_seconds"),
        question_asked_at=current_question.get("asked_at"),
        answered_at=current_answer.get("answered_at"),
    )
    communication_evidence = "\n".join(comm.evidence) if comm.evidence else "No objective signals available."

    # Coding context (Feature 9)
    active_problem = state.get("active_coding_problem", {})
    coding_context = (
        json.dumps(active_problem, indent=2)[:2000]
        if active_problem and code_snapshot
        else "No live-coding problem active."
    )

    prompt = ANSWER_ANALYZER_PROMPT.format(
        question_text=current_question.get("question", ""),
        question_intent=current_question.get("intent", "technical"),
        stage_name=current_stage.get("name", "General"),
        expected_signals=", ".join(expected_signals) if expected_signals else "Technical accuracy, depth, and clarity",
        answer_text=current_answer.get("answer_text", ""),
        code_snapshot=code_snapshot if code_snapshot else "No code provided.",
        resume_context=resume_context,
        communication_evidence=communication_evidence,
    )

    # Coding problem context appended so the evaluator can grade against the prompt
    if active_problem and code_snapshot:
        prompt += (
            f"\n\nLIVE CODING PROBLEM (evaluate the submitted code against this):\n{coding_context}"
        )

    result = await _call_llm_json(ANSWER_ANALYZER_SYSTEM, prompt)

    # ── Blend LLM communication score with objective metrics ─────────────
    llm_comm = int(result.get("communication_quality", 5))
    blended_comm = round(0.5 * llm_comm + 0.5 * comm.overall_score)
    blended_comm = max(0, min(10, blended_comm))

    # Fold objective signals into the sign lists (deduplicated, capped)
    positive_signals = list(result.get("positive_signals", []))
    red_flags = list(result.get("red_flags", []))
    for strength in comm.strengths:
        if strength not in positive_signals and len(positive_signals) < 5:
            positive_signals.append(f"(communication) {strength}")
    for concern in comm.concerns:
        if concern not in red_flags and len(red_flags) < 5:
            red_flags.append(f"(communication) {concern}")

    evaluation: AnswerEvaluation = {
        "question_id": current_question.get("id", ""),
        "technical_accuracy": int(result.get("technical_accuracy", 5)),
        "depth": int(result.get("depth", 5)),
        "clarity": int(result.get("clarity", 5)),
        "confidence": int(result.get("confidence", 5)),
        "completeness": int(result.get("completeness", 5)),
        "communication_quality": blended_comm,
        "missing_points": result.get("missing_points", []),
        "positive_signals": positive_signals,
        "red_flags": red_flags,
        "suggested_follow_ups": result.get("suggested_follow_ups", []),
        "overall_quality": result.get("overall_quality", "average"),
        "comm_metrics": comm.to_dict(),
    }

    # ── Feature 9: Coding quality grade ──────────────────────────────────
    coding_quality: int | None = None
    if active_problem and code_snapshot:
        coding_quality = int(round(
            0.5 * evaluation["technical_accuracy"]
            + 0.3 * evaluation["depth"]
            + 0.2 * evaluation["completeness"]
        ))
        evaluation["coding_quality"] = coding_quality

    # Update memory with evaluation insights
    memory = state.get("memory", {})
    mem_mgr = MemoryManager(
        memory, [],
        resume_claims=state.get("resume_claims", []),
        topic_mastery=state.get("topic_mastery", {}),
        candidate_facts=state.get("candidate_facts", []),
        difficulty_level=state.get("difficulty_level", DifficultyLevel(
            level="intermediate", level_numeric=2, overall_mastery=5.0,
            resume_seniority="mid", consecutive_strong=0, consecutive_weak=0,
        )),
        code_history=state.get("code_history", []),
    )
    mem_mgr.process_evaluation(evaluation, current_question.get("topic", "general"))

    updated_evaluations = list(state.get("evaluations_history", [])) + [evaluation]

    # Signal whether a follow-up is needed
    should_follow_up = (
        result.get("should_dig_deeper", False) or
        evaluation["depth"] < 6 or
        len(evaluation["red_flags"]) > 0 or
        len(evaluation["missing_points"]) > 1
    )

    # ── Feature 3: Contradiction detection ────────────────────────────────
    existing_facts = state.get("candidate_facts", [])
    facts_for_check = [
        {"fact_id": f["fact_id"], "statement": f["statement"], "topic": f["topic"]}
        for f in existing_facts
    ]

    contradiction_prompt = CONTRADICTION_DETECTOR_PROMPT.format(
        latest_question=current_question.get("question", ""),
        latest_answer=current_answer.get("answer_text", ""),
        existing_facts=json.dumps(facts_for_check[:20], indent=2) if facts_for_check else "No previous facts recorded.",
    )

    contradiction_result = await _call_llm_json(
        CONTRADICTION_DETECTOR_SYSTEM,
        contradiction_prompt,
    )

    # Process new facts
    updated_facts = list(existing_facts)
    for raw_fact in contradiction_result.get("new_facts", []):
        fact_id = str(uuid.uuid4())[:8]
        new_fact = CandidateFact(
            fact_id=fact_id,
            statement=raw_fact.get("statement", ""),
            topic=raw_fact.get("topic", current_question.get("topic", "general")),
            source_question_id=current_question.get("id", ""),
            timestamp=time.time(),
            contradicted=False,
        )
        updated_facts.append(new_fact)

    # Process contradictions
    contradictions_found = contradiction_result.get("contradictions", [])
    for contra in contradictions_found:
        new_fact_id = contra.get("new_fact_id", "")
        old_fact_id = contra.get("contradicts_fact_id", "")
        # Mark the older fact as contradicted
        for fact in updated_facts:
            if fact["fact_id"] == old_fact_id:
                fact["contradicted"] = True
                fact["contradicted_by"] = new_fact_id
                fact["contradiction_evidence"] = contra.get("explanation", "")
                break
        # Add contradiction to concerning moments
        if contra.get("explanation"):
            memory["concerning_moments"].append(
                f"Contradiction detected: {contra['explanation'][:100]}"
            )

    # ── Feature 9: Record coding submission when a problem is active ─────
    coding_submissions = list(state.get("coding_submissions", []))
    if active_problem and code_snapshot:
        coding_submissions.append(CodingSubmission(
            problem_id=active_problem.get("id", ""),
            question_id=current_question.get("id", ""),
            code=code_snapshot,
            language=state.get("current_code_snapshot_language", ""),
            submitted_at=time.time(),
            quality=coding_quality or 0,
            summary=result.get("answer_summary", ""),
            feedback=", ".join(result.get("red_flags", [])[:2]),
        ))

    logger.info(
        "Answer evaluated",
        extra={
            "technical": evaluation["technical_accuracy"],
            "depth": evaluation["depth"],
            "overall": evaluation["overall_quality"],
            "communication": blended_comm,
            "should_follow_up": should_follow_up,
            "new_facts": len(contradiction_result.get("new_facts", [])),
            "contradictions": len(contradictions_found),
        }
    )

    return {
        "current_evaluation": evaluation,
        "current_comm_metrics": comm.to_dict(),
        "evaluations_history": updated_evaluations,
        "memory": mem_mgr.get_full_memory(),
        "candidate_facts": updated_facts,
        "topic_mastery": mem_mgr.topic_mastery,
        "difficulty_level": mem_mgr.difficulty_level,
        "coding_submissions": coding_submissions,
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

    # Append difficulty guidance
    difficulty_level = state.get("difficulty_level", {})
    current_diff = difficulty_level.get("level", "intermediate")
    difficulty_hint = DIFFICULTY_GUIDANCE.get(current_diff, DIFFICULTY_GUIDANCE["intermediate"])
    prompt += f"\n\nDIFFICULTY GUIDANCE (current level: {current_diff}):\n{difficulty_hint}"

    result = await _call_llm_json(FOLLOW_UP_GENERATOR_SYSTEM, prompt)

    follow_up_text = result.get("follow_up_question", "")

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
    for _i, entry in enumerate(transcript):
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

    # ── Feature 1: Claim verification summary ─────────────────────────────
    resume_claims = state.get("resume_claims", [])
    claim_verification_lines = []
    for c in resume_claims:
        evidence_str = "; ".join(c.get("verification_evidence", [])[:2])
        claim_verification_lines.append(
            f"- [{c['verification_status']}] \"{c['claim_text']}\" "
            f"(skill: {c.get('skill', 'N/A')}, evidence: {evidence_str or 'none'})"
        )
    claim_verification_summary = "\n".join(claim_verification_lines) if claim_verification_lines else "No claims tracked."

    # ── Feature 2: Topic mastery summary ──────────────────────────────────
    topic_mastery = state.get("topic_mastery", {})
    topic_mastery_lines = []
    for topic, mastery in topic_mastery.items():
        topic_mastery_lines.append(
            f"- {topic}: {mastery['mastery_score']}/10 "
            f"(questions: {mastery['questions_asked']}, "
            f"avg_depth: {mastery['avg_depth']:.1f})"
        )
    topic_mastery_summary = "\n".join(topic_mastery_lines) if topic_mastery_lines else "No topic mastery data."

    # ── Feature 5: Code evolution summary ─────────────────────────────────
    code_history = state.get("code_history", [])
    code_evolution_lines = []
    for v in code_history:
        code_evolution_lines.append(
            f"- Version {v['version_id']} (Q: {v.get('question_id', 'N/A')[:8]}, "
            f"lang: {v.get('language', 'N/A')}, "
            f"changes: {v.get('diff_summary', 'N/A')})"
        )
    code_evolution_summary = "\n".join(code_evolution_lines) if code_evolution_lines else "No code evolution data."

    # ── Feature 3: Contradictions count ───────────────────────────────────
    candidate_facts = state.get("candidate_facts", [])
    contradictions_found = len([f for f in candidate_facts if f.get("contradicted", False)])

    # ── Objective communication analysis (from stored per-answer metrics) ─
    comm_metrics_list = [
        dict(ev.get("comm_metrics", {})) for ev in evaluations if ev.get("comm_metrics")
    ]
    if comm_metrics_list:
        from app.ai_interviewer.communication_analyzer import (
            CommunicationMetrics,
            summarize_session,
        )

        comm_summary = summarize_session(
            [CommunicationMetrics(**m) for m in comm_metrics_list]
        )
        comm_lines = [
            f"- Answers analyzed: {comm_summary['analyzed_answers']}",
            f"- Avg communication score: {comm_summary['avg_overall']}/10",
            f"- Strongest dimension: {comm_summary['best_dimension']}",
            f"- Weakest dimension: {comm_summary['worst_dimension']}",
        ]
        if comm_summary["top_strengths"]:
            comm_lines.append(f"- Strengths: {', '.join(comm_summary['top_strengths'])}")
        if comm_summary["top_concerns"]:
            comm_lines.append(f"- Concerns: {', '.join(comm_summary['top_concerns'])}")
        communication_analysis_summary = "\n".join(comm_lines)
        communication_summary = comm_summary
    else:
        communication_analysis_summary = "No per-answer communication metrics captured."
        communication_summary = {"analyzed_answers": 0, "avg_overall": 0.0}

    # ── P5: Evidence graph summary ────────────────────────────────────────
    evidence_graph = state.get("evidence_graph", {})
    evidence_graph_summary: dict[str, list[dict]] = {}
    for claim_id, nodes in evidence_graph.items():
        evidence_graph_summary[claim_id] = [
            {
                "evidence_id": n.get("evidence_id", ""),
                "question_id": n.get("question_id", ""),
                "supports_claim": n.get("supports_claim", False),
                "strength": n.get("strength", ""),
                "reasoning": n.get("reasoning", "")[:200],
            }
            for n in nodes
        ]

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
        claim_verification_summary=claim_verification_summary[:3000],
        topic_mastery_summary=topic_mastery_summary,
        code_evolution_summary=code_evolution_summary,
        contradictions_found=str(contradictions_found),
        communication_analysis_summary=communication_analysis_summary,
        technical_score=scores.get("technical_score", 50),
        communication_score=scores.get("communication_score", 50),
        confidence_score=scores.get("confidence_score", 50),
        problem_solving_score=scores.get("problem_solving_score", 50),
        behavioral_score=scores.get("behavioral_score", 50),
        overall_score=scores.get("overall_score", 50),
    )

    result = await _call_llm_json(REPORT_GENERATOR_SYSTEM, prompt)

    report: FinalReport = {
        "candidate_name": analysis.get("candidate_name", "Candidate"),
        "session_id": state["session_id"],
        "interview_duration_seconds": duration_secs,
        "scores": scores,
        "strengths": result.get("strengths", []),
        "weaknesses": result.get("weaknesses", []),
        "areas_for_improvement": result.get("areas_for_improvement", []),
        "detailed_summary": result.get("detailed_summary", ""),
        "question_records": list(questions),
        "answer_evaluations": list(evaluations),
        "recommendation_rationale": result.get("recommendation_rationale", ""),
        "generated_at": time.time(),
        # Feature 1: Claim verification
        "claim_verification_summary": [
            {
                "claim_id": c["claim_id"],
                "claim_text": c["claim_text"],
                "skill": c.get("skill", ""),
                "status": c["verification_status"],
                "evidence": c.get("verification_evidence", []),
            }
            for c in resume_claims
        ],
        # Feature 2: Topic mastery
        "topic_mastery_summary": [
            {
                "topic": t,
                "mastery_score": m["mastery_score"],
                "questions_asked": m["questions_asked"],
                "avg_technical_accuracy": m["avg_technical_accuracy"],
                "avg_depth": m["avg_depth"],
            }
            for t, m in topic_mastery.items()
        ],
        # Feature 5: Code evolution
        "code_evolution_summary": [
            {
                "version": v["version_id"],
                "language": v.get("language", ""),
                "diff_summary": v.get("diff_summary", ""),
            }
            for v in code_history
        ],
        # Objective communication analysis
        "communication_summary": communication_summary,
        # P5: Evidence graph
        "evidence_graph_summary": evidence_graph_summary,
        # Feature 9: Live coding round
        "coding_summary": {
            "problem": {
                "id": state.get("active_coding_problem", {}).get("id", ""),
                "title": state.get("active_coding_problem", {}).get("title", ""),
                "difficulty": state.get("active_coding_problem", {}).get("difficulty", ""),
                "topic": state.get("active_coding_problem", {}).get("topic", ""),
            } if state.get("active_coding_problem") else None,
            "submissions": [
                {
                    "problem_id": s["problem_id"],
                    "quality": s["quality"],
                    "language": s.get("language", ""),
                    "feedback": s.get("feedback", ""),
                }
                for s in state.get("coding_submissions", [])
            ],
        },
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

# ── Feature 9: Live Coding Problem Generator ────────────────────────────────

def _is_coding_stage(stage: dict) -> bool:
    """Heuristic: a stage is a coding stage if its id/name signals coding."""
    name = f"{stage.get('name', '')} {stage.get('id', '')}".lower()
    return any(token in name for token in ("coding", "cod", "live-code", "algorithm"))


def _as_list(value) -> list:
    """Coerce an LLM field into a list, tolerating None or non-list junk."""
    return list(value) if isinstance(value, (list, tuple, set)) else []


async def coding_problem_generator_node(state: InterviewState) -> dict:
    """
    Generates a structured live-coding problem for the coding stage,
    tailored to the candidate's level and the role being interviewed for.
    """
    existing = state.get("active_coding_problem")
    if existing and existing.get("description"):
        return {"active_coding_problem": existing}

    logger.info("Executing coding_problem_generator_node", extra={"session": state["session_id"]})

    analysis = state.get("resume_analysis", {})
    difficulty = state.get("difficulty_level", {})
    memory = state.get("memory", {})

    prompt = CODING_PROBLEM_GENERATOR_PROMPT.format(
        role=state["role"],
        seniority_level=analysis.get("seniority_level", "mid"),
        skills=", ".join(analysis.get("technologies", [])[:10]),
        difficulty_hint=DIFFICULTY_GUIDANCE.get(
            difficulty.get("level", "intermediate"), DIFFICULTY_GUIDANCE["intermediate"]
        ),
        topics_covered=", ".join(memory.get("topics_covered", [])[-6:]) or "none yet",
        question_index=state.get("questions_asked", 0),
    )

    result = await _call_llm_json(CODING_PROBLEM_GENERATOR_SYSTEM, prompt)

    problem = CodingProblem(
        id=str(uuid.uuid4())[:8],
        title=result.get("title") or "Coding Challenge",
        difficulty=result.get("difficulty") or "medium",
        topic=result.get("topic") or "algorithms",
        description=result.get("description") or "",
        constraints=_as_list(result.get("constraints")),
        examples=_as_list(result.get("examples")),
        languages=_as_list(result.get("languages")) or ["python", "javascript"],
        starter_code=result.get("starter_code") or {},
        time_complexity=result.get("time_complexity") or "",
        space_complexity=result.get("space_complexity") or "",
        evaluation_criteria=_as_list(result.get("evaluation_criteria")),
        generated_at=time.time(),
    )

    logger.info(
        "Coding problem generated",
        extra={"title": problem["title"], "difficulty": problem["difficulty"]},
    )

    return {"active_coding_problem": problem}


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

    updates: dict = {
        "current_stage_index": next_idx,
        "current_stage": next_stage,
    }

    # ── Feature 9: Generate a live-coding problem when entering a coding stage ──
    if _is_coding_stage(next_stage):
        try:
            coding_result = await coding_problem_generator_node(state)
            updates.update(coding_result)
        except Exception as e:  # noqa: BLE001
            logger.warning("Coding problem generation failed", extra={"error": str(e)})

    # Generate transition message
    prompt = STAGE_TRANSITION_PROMPT.format(
        current_stage=current_stage.get("name", ""),
        next_stage=next_stage.get("name", ""),
        candidate_name=analysis.get("candidate_name", ""),
    )
    result = await _call_llm_json(
        "You are a professional interviewer transitioning between topics.",
        prompt,
    )

    transition_text = result.get("transition_text", "")

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
        "active_coding_problem": updates.get("active_coding_problem"),
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

    result = await _call_llm_json(
        "You are a professional technical interviewer opening the interview.",
        prompt,
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

    result = await _call_llm_json(
        "You are a professional technical interviewer closing the interview.",
        prompt,
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


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 1: Claim Verifier Node
# ══════════════════════════════════════════════════════════════════════════════

async def claim_verifier_node(state: InterviewState) -> dict:
    """
    Verifies resume claims against the candidate's latest answer.
    Updates claim verification status with evidence.
    """
    logger.info("Executing claim_verifier_node", extra={"session": state["session_id"]})

    current_question = state.get("current_question", {})
    current_answer = state.get("current_answer", {})
    resume_claims = list(state.get("resume_claims", []))
    state.get("resume_analysis", {})

    if not current_answer or not resume_claims:
        return {"resume_claims": resume_claims}

    # ── P5: Evidence graph ────────────────────────────────────────────────
    from app.ai_interviewer.evidence_graph import EvidenceGraph

    existing_graph = state.get("evidence_graph", {})
    evidence_graph = EvidenceGraph.from_dict(existing_graph, resume_claims)

    # Find unverified claims relevant to this answer's topic
    topic = current_question.get("topic", "general")
    claims_to_verify = [
        c for c in resume_claims
        if c["verification_status"] == "UNVERIFIED"
        and (
            c.get("skill", "").lower() in topic.lower()
            or topic.lower() in c.get("claim_text", "").lower()
            or not c.get("skill")
        )
    ][:3]  # Max 3 claims per answer

    for claim in claims_to_verify:
        previous_evidence = "\n".join(claim.get("verification_evidence", [])) or "No previous evidence."

        prompt = CLAIM_VERIFIER_PROMPT.format(
            claim_text=claim["claim_text"],
            skill=claim.get("skill", "N/A"),
            source=claim.get("source", "resume"),
            question_text=current_question.get("question", ""),
            answer_text=current_answer.get("answer_text", ""),
            previous_evidence=previous_evidence,
        )

        result = await _call_llm_json(CLAIM_VERIFIER_SYSTEM, prompt)

        new_status = result.get("verification_status", "UNVERIFIED")
        evidence = result.get("evidence", "")
        question_id = current_question.get("id", "")

        # Update claim — only upgrade status, never downgrade
        status_priority = {"UNVERIFIED": 0, "PARTIALLY_VERIFIED": 1, "VERIFIED": 2, "FAILED_VERIFICATION": 3}
        current_priority = status_priority.get(claim["verification_status"], 0)
        new_priority = status_priority.get(new_status, 0)

        # Allow upgrading UNVERIFIED → any status
        # Allow upgrading PARTIALLY_VERIFIED → VERIFIED or FAILED
        if claim["verification_status"] == "UNVERIFIED" or new_priority > current_priority:
            claim["verification_status"] = new_status
            if evidence and evidence not in claim["verification_evidence"]:
                claim["verification_evidence"].append(evidence)
            if question_id and question_id not in claim["asked_question_ids"]:
                claim["asked_question_ids"].append(question_id)

        # Record an evidence node for this verification moment (P5)
        if question_id:
            supports_claim = new_status in ("VERIFIED", "PARTIALLY_VERIFIED")
            strength = "strong" if new_status in ("VERIFIED", "FAILED_VERIFICATION") else "moderate"
            evidence_graph.add_evidence(
                claim_id=claim["claim_id"],
                question_id=question_id,
                question_text=current_question.get("question", "")[:300],
                answer_excerpt=(current_answer.get("answer_text", "") or "")[:400],
                supports_claim=supports_claim,
                strength=strength,
                reasoning=evidence[:300] or f"Verification outcome: {new_status}",
            )

    logger.info(
        "Claims verified",
        extra={
            "claims_checked": len(claims_to_verify),
            "total_claims": len(resume_claims),
        }
    )

    return {
        "resume_claims": resume_claims,
        "evidence_graph": evidence_graph.to_dict(),
    }


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 6: Interview Replanner Node
# ══════════════════════════════════════════════════════════════════════════════

async def interview_replanner_node(state: InterviewState) -> dict:
    """
    Replans the remaining interview based on everything learned so far.
    Called every 2-3 questions to adapt the interview strategy.
    """
    logger.info("Executing interview_replanner_node", extra={"session": state["session_id"]})

    analysis = state.get("resume_analysis", {})
    plan = state.get("interview_plan", {})
    memory = state.get("memory", {})
    resume_claims = state.get("resume_claims", [])
    topic_mastery = state.get("topic_mastery", {})
    candidate_facts = state.get("candidate_facts", [])
    difficulty_level = state.get("difficulty_level", {})

    questions_asked = state.get("questions_asked", 0)
    max_questions = state.get("max_questions", 12)
    remaining = max_questions - questions_asked

    if remaining <= 2:
        return {}  # Too few questions left to replan

    # Build context
    mem_mgr = MemoryManager(
        memory,
        plan.get("stages", [{}])[state.get("current_stage_index", 0)].get("topics", []),
        resume_claims=resume_claims,
        topic_mastery=topic_mastery,
        candidate_facts=candidate_facts,
        difficulty_level=difficulty_level,
    )
    mem_summary = mem_mgr.get_summary_for_prompt()

    # Build unverified/failed claims strings
    unverified = [c["claim_text"] for c in resume_claims if c["verification_status"] == "UNVERIFIED"]
    failed = [c["claim_text"] for c in resume_claims if c["verification_status"] == "FAILED_VERIFICATION"]
    contradictions = len([f for f in candidate_facts if f.get("contradicted", False)])

    prompt = INTERVIEW_REPLANNER_PROMPT.format(
        questions_asked=questions_asked,
        max_questions=max_questions,
        remaining_questions=remaining,
        current_stage=state.get("current_stage", {}).get("name", "General"),
        resume_summary=json.dumps(analysis, indent=2)[:2000],
        topic_mastery=json.dumps(
            {t: m["mastery_score"] for t, m in topic_mastery.items()},
            indent=2,
        ) if topic_mastery else "No mastery data yet",
        unverified_claims=", ".join(unverified[:5]) if unverified else "None",
        failed_claims=", ".join(failed[:3]) if failed else "None",
        contradictions_found=str(contradictions),
        weaknesses="; ".join(mem_summary.get("weaknesses", [])),
        strengths="; ".join(mem_summary.get("strengths", [])),
        difficulty_level=difficulty_level.get("level", "intermediate"),
    )

    result = await _call_llm_json(INTERVIEW_REPLANNER_SYSTEM, prompt)

    # Apply replanning — update stage topics if provided
    replanned_stages = result.get("replanned_stages", [])
    topics_to_probe = result.get("topics_to_probe", [])
    topics_to_skip = result.get("topics_to_skip", [])

    # Add new topics to pending if they aren't already covered
    updated_memory = dict(memory)
    for topic in topics_to_probe:
        if topic not in updated_memory.get("topics_covered", []) and topic not in updated_memory.get("topics_pending", []):
            updated_memory["topics_pending"].append(topic)
    # Remove topics to skip
    for topic in topics_to_skip:
        if topic in updated_memory.get("topics_pending", []):
            updated_memory["topics_pending"].remove(topic)

    # Update stages in plan if replanner provided new stages
    updated_plan = dict(plan)
    if replanned_stages:
        state.get("current_stage_index", 0)
        stages = list(plan.get("stages", []))
        for new_stage in replanned_stages:
            # Find matching stage by ID or add as new
            found = False
            for i, existing in enumerate(stages):
                if existing.get("id") == new_stage.get("id"):
                    stages[i] = InterviewStage(
                        id=existing["id"],
                        name=new_stage.get("name", existing["name"]),
                        description=new_stage.get("description", existing["description"]),
                        topics=new_stage.get("topics", existing["topics"]),
                        target_questions=int(new_stage.get("target_questions", existing["target_questions"])),
                        completed=existing["completed"],
                    )
                    found = True
                    break
            if not found:
                stages.append(InterviewStage(
                    id=new_stage.get("id", str(uuid.uuid4())[:8]),
                    name=new_stage.get("name", "Additional Stage"),
                    description=new_stage.get("description", ""),
                    topics=new_stage.get("topics", []),
                    target_questions=int(new_stage.get("target_questions", 2)),
                    completed=False,
                ))
        updated_plan["stages"] = stages

    replan_count = state.get("replan_count", 0) + 1
    replan_topics_added = state.get("replan_topics_added", []) + topics_to_probe

    logger.info(
        "Interview replanned",
        extra={
            "replan_count": replan_count,
            "topics_probed": len(topics_to_probe),
            "topics_skipped": len(topics_to_skip),
            "rationale": result.get("rationale", "")[:100],
        }
    )

    return {
        "interview_plan": updated_plan,
        "memory": updated_memory,
        "replan_count": replan_count,
        "replan_topics_added": replan_topics_added,
    }


# ══════════════════════════════════════════════════════════════════════════════
# FEATURE 7: System Design Evaluator Node
# ══════════════════════════════════════════════════════════════════════════════

async def system_design_evaluator_node(state: InterviewState) -> dict:
    """
    Specialized evaluator for system design questions.
    Evaluates across 7 dimensions: requirements, API, DB, scalability,
    caching, tradeoffs, failure handling.
    """
    logger.info("Executing system_design_evaluator_node", extra={"session": state["session_id"]})

    current_question = state.get("current_question", {})
    current_answer = state.get("current_answer", {})
    state.get("resume_analysis", {})

    if not current_question or not current_answer:
        return {}

    prompt = SYSTEM_DESIGN_EVALUATOR_PROMPT.format(
        question_text=current_question.get("question", ""),
        answer_text=current_answer.get("answer_text", ""),
        role=state.get("role", "Software Engineer"),
        company=state.get("company", "the company"),
    )

    result = await _call_llm_json(SYSTEM_DESIGN_EVALUATOR_SYSTEM, prompt)

    # Store system design scores in state
    system_design_scores = {
        "requirements_clarification": int(result.get("requirements_clarification", 5)),
        "api_design": int(result.get("api_design", 5)),
        "database_design": int(result.get("database_design", 5)),
        "scalability": int(result.get("scalability", 5)),
        "caching_strategy": int(result.get("caching_strategy", 5)),
        "tradeoff_analysis": int(result.get("tradeoff_analysis", 5)),
        "failure_handling": int(result.get("failure_handling", 5)),
        "overall_system_design_score": int(result.get("overall_system_design_score", 5)),
    }

    logger.info(
        "System design evaluated",
        extra={
            "overall_score": system_design_scores["overall_system_design_score"],
            "dimensions": len(system_design_scores),
        }
    )

    return {
        "system_design_scores": system_design_scores,
    }
