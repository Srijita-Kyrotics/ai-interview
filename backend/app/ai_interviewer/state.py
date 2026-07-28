"""
Interview State Schema
======================
Defines the complete TypedDict that flows through every node of the
LangGraph interview pipeline.  Every field is documented.
"""

from __future__ import annotations

from typing import Any, Optional
from typing_extensions import TypedDict, NotRequired


# ── Sub-schemas ──────────────────────────────────────────────────────────────

class SkillAnalysis(TypedDict):
    skill: str
    confidence: str          # "high" | "medium" | "low"
    claimed_depth: str       # "expert" | "intermediate" | "beginner"
    needs_verification: bool
    follow_up_priority: int  # 1-10, higher = more important


class ProjectAnalysis(TypedDict):
    name: str
    technologies: list[str]
    claimed_impact: str
    unclear_points: list[str]
    deep_dive_questions: list[str]


class ResumeAnalysis(TypedDict):
    candidate_name: str
    years_experience: int
    seniority_level: str      # "junior" | "mid" | "senior" | "staff"
    strong_areas: list[str]
    weak_areas: list[str]
    red_flags: list[str]      # Overclaiming, inconsistencies
    skills: list[SkillAnalysis]
    projects: list[ProjectAnalysis]
    technologies: list[str]
    education: list[dict]
    certifications: list[dict]
    experience_entries: list[dict]
    summary: str
    raw_text: str


class InterviewStage(TypedDict):
    id: str
    name: str
    description: str
    topics: list[str]
    target_questions: int
    completed: bool


class InterviewPlan(TypedDict):
    stages: list[InterviewStage]
    total_questions: int
    focus_areas: list[str]
    opening_strategy: str
    closing_strategy: str
    estimated_duration_minutes: int


class QuestionRecord(TypedDict):
    id: str
    question: str
    stage: str
    topic: str
    asked_at: float
    intent: str              # "probe" | "verify" | "deep_dive" | "behavioral" | "technical"


class AnswerRecord(TypedDict):
    question_id: str
    question_text: str
    answer_text: str
    answered_at: float
    duration_seconds: float
    code_snapshot: NotRequired[str]


class AnswerEvaluation(TypedDict):
    question_id: str
    technical_accuracy: int   # 0-10
    depth: int                # 0-10
    clarity: int              # 0-10
    confidence: int           # 0-10
    completeness: int         # 0-10
    communication_quality: int # 0-10
    missing_points: list[str]
    positive_signals: list[str]
    red_flags: list[str]
    suggested_follow_ups: list[str]
    overall_quality: str      # "excellent" | "good" | "average" | "poor"


class InterviewMemory(TypedDict):
    questions_asked: list[str]         # question IDs
    topics_covered: list[str]
    topics_pending: list[str]
    candidate_strengths: list[str]
    candidate_weaknesses: list[str]
    unresolved_claims: list[str]       # Claims that need verification
    positive_moments: list[str]
    concerning_moments: list[str]
    depth_map: dict[str, int]          # topic -> depth level reached


class FinalScores(TypedDict):
    technical_score: float             # 0-100
    communication_score: float         # 0-100
    confidence_score: float            # 0-100
    problem_solving_score: float       # 0-100
    behavioral_score: float            # 0-100
    depth_score: float                 # 0-100
    overall_score: float               # 0-100
    recommendation: str                # "Strong Hire" | "Hire" | "Lean Hire" | "Lean Reject" | "Reject"


class FinalReport(TypedDict):
    candidate_name: str
    session_id: str
    interview_duration_seconds: float
    scores: FinalScores
    strengths: list[str]
    weaknesses: list[str]
    areas_for_improvement: list[str]
    detailed_summary: str
    question_records: list[QuestionRecord]
    answer_evaluations: list[AnswerEvaluation]
    recommendation_rationale: str
    generated_at: float


# ── Master State ─────────────────────────────────────────────────────────────

class InterviewState(TypedDict):
    # ── Identity ──────────────────────────────────────────────────────────
    session_id: str
    candidate_email: str
    role: str                          # Target role for the interview
    company: str

    # ── Resume Data ──────────────────────────────────────────────────────
    resume_raw_text: str
    resume_parsed: dict                # Output of resume_parser.parse_resume_text
    resume_analysis: NotRequired[ResumeAnalysis]

    # ── Interview Plan ───────────────────────────────────────────────────
    interview_plan: NotRequired[InterviewPlan]
    current_stage_index: int
    current_stage: NotRequired[InterviewStage]

    # ── Conversation ─────────────────────────────────────────────────────
    questions_history: list[QuestionRecord]
    answers_history: list[AnswerRecord]
    evaluations_history: list[AnswerEvaluation]
    conversation_transcript: list[dict]  # {"role": "interviewer"|"candidate", "text": str, "ts": float}

    # ── Current Turn ─────────────────────────────────────────────────────
    current_question: NotRequired[QuestionRecord]
    current_answer: NotRequired[AnswerRecord]
    current_evaluation: NotRequired[AnswerEvaluation]
    next_question_text: NotRequired[str]
    ai_response_text: NotRequired[str]
    current_code_snapshot: NotRequired[str]

    # ── Memory ────────────────────────────────────────────────────────────
    memory: InterviewMemory

    # ── Timing ───────────────────────────────────────────────────────────
    interview_started_at: float
    last_activity_at: float
    question_started_at: NotRequired[float]

    # ── Control Flow ─────────────────────────────────────────────────────
    phase: str                         # "analyzing" | "planning" | "interviewing" | "completed" | "error"
    questions_asked: int
    max_questions: int
    should_end: bool
    error: NotRequired[str]

    # ── Final Output ─────────────────────────────────────────────────────
    final_report: NotRequired[FinalReport]

    # ── Voice Pipeline ────────────────────────────────────────────────────
    voice_enabled: bool
    audio_chunk_buffer: NotRequired[bytes]  # For streaming STT
    tts_audio_response: NotRequired[bytes]  # For streaming TTS


# ── State Factory ─────────────────────────────────────────────────────────────

def make_initial_state(
    session_id: str,
    candidate_email: str,
    role: str,
    company: str,
    resume_raw_text: str,
    resume_parsed: dict,
    max_questions: int = 12,
    voice_enabled: bool = False,
) -> InterviewState:
    """Create a fresh InterviewState with sensible defaults."""
    import time

    now = time.time()
    return InterviewState(
        session_id=session_id,
        candidate_email=candidate_email,
        role=role,
        company=company,
        resume_raw_text=resume_raw_text,
        resume_parsed=resume_parsed,
        current_stage_index=0,
        questions_history=[],
        answers_history=[],
        evaluations_history=[],
        conversation_transcript=[],
        memory=InterviewMemory(
            questions_asked=[],
            topics_covered=[],
            topics_pending=[],
            candidate_strengths=[],
            candidate_weaknesses=[],
            unresolved_claims=[],
            positive_moments=[],
            concerning_moments=[],
            depth_map={},
        ),
        interview_started_at=now,
        last_activity_at=now,
        phase="analyzing",
        questions_asked=0,
        max_questions=max_questions,
        should_end=False,
        voice_enabled=voice_enabled,
    )
