"""
LangGraph Interview Graph
=========================
Assembles all nodes into a compiled StateGraph.

Graph Architecture:
──────────────────

  [START]
    │
    ▼
  resume_analyzer ──────────────────────────────────┐
    │                                                │
    ▼                                                │ (on error)
  interview_planner                                  ▼
    │                                           [error_node]
    ▼
  opening ──────────────────────────────────────────┐
    │                                               │ (emit opening message)
    ▼
  ┌─────────────────────────────────────────────────┐
  │             MAIN INTERVIEW LOOP                 │
  │                                                 │
  │  question_generator ◄─────────────────────┐    │
  │       │                                   │    │
  │       ▼                                   │    │
  │  [WAIT FOR ANSWER] ←─ WebSocket           │    │
  │       │                                   │    │
  │       ▼                                   │    │
  │  answer_analyzer                          │    │
  │       │                                   │    │
  │       ▼                                   │    │
  │  route_after_analysis ──► follow_up_gen ──┘    │
  │       │                                        │
  │       ▼ (no follow-up)                         │
  │  stage_advance ──────────────────────────────► │
  │       │ (continue)                             │
  │       └───────────────────────────────────────►│
  │                   (loop)                       │
  └─────────────────────────────────────────────────┘
    │ (should_end == True)
    ▼
  closing
    │
    ▼
  scoring
    │
    ▼
  report_generator
    │
    ▼
  [END]

The graph is designed for EVENT-DRIVEN execution.
During the interview loop, the graph pauses after question_generator
and waits for the candidate's answer via WebSocket.
The answer is injected as a state update, and the graph resumes
from answer_analyzer.

This is implemented using LangGraph's `interrupt` mechanism or
manual step-by-step invocation via the WebSocket handler.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.ai_interviewer.coding_judge import judge_submission
from app.ai_interviewer.nodes import (
    answer_analyzer_node,
    claim_extractor_node,
    claim_verifier_node,
    closing_node,
    follow_up_generator_node,
    interview_planner_node,
    interview_replanner_node,
    opening_node,
    question_generator_node,
    report_generator_node,
    resume_analyzer_node,
    scoring_node,
    stage_advance_node,
    system_design_evaluator_node,
)
from app.ai_interviewer.state import InterviewState

logger = logging.getLogger("ai_interview.graph")


# ── Conditional Edge Functions ────────────────────────────────────────────────

def route_after_answer_analysis(state: InterviewState) -> Literal[
    "follow_up_generator", "stage_advance", "closing"
]:
    """
    Route after answer analysis:
    - If answer was shallow/incomplete → generate follow-up
    - If we've hit max questions → close interview
    - Otherwise → check if we should advance stage, then ask next question
    """
    should_follow_up = state.get("_should_follow_up", False)
    should_end = state.get("should_end", False)
    questions_asked = state.get("questions_asked", 0)
    max_questions = state.get("max_questions", 12)
    max_turns = state.get("max_turns", max_questions * 2)

    if should_end or questions_asked >= max_turns:
        logger.info("Routing to closing — interview complete")
        return "closing"

    if should_follow_up:
        logger.info("Routing to follow_up_generator — answer needs deeper probe")
        return "follow_up_generator"

    logger.info("Routing to stage_advance — moving forward")
    return "stage_advance"


def route_after_stage_advance(state: InterviewState) -> Literal[
    "question_generator", "closing"
]:
    """After advancing a stage, either continue with next question or close."""
    if state.get("should_end", False):
        return "closing"
    if state.get("questions_asked", 0) >= state.get("max_turns", state.get("max_questions", 12) * 2):
        return "closing"
    return "question_generator"


def route_after_follow_up(state: InterviewState) -> Literal[
    "question_generator", "closing"
]:
    """After generating a follow-up, route appropriately."""
    if state.get("questions_asked", 0) >= state.get("max_turns", state.get("max_questions", 12) * 2):
        return "closing"
    return "question_generator"


def route_initial_analysis(state: InterviewState) -> Literal[
    "interview_planner", "error_node"
]:
    """After resume analysis, check for errors."""
    if state.get("error"):
        return "error_node"
    return "interview_planner"


def error_node(state: InterviewState) -> dict:
    """Handle errors gracefully."""
    logger.error("Interview error encountered", extra={"error": state.get("error")})
    return {
        "phase": "error",
        "should_end": True,
        "ai_response_text": "I'm experiencing a technical issue. Please contact support.",
    }


# ── Graph Builder ─────────────────────────────────────────────────────────────

def build_interview_graph(checkpointer=None):
    """
    Build and compile the LangGraph interview graph.

    The graph supports:
    1. Full automated runs (for testing)
    2. Step-by-step event-driven runs (for WebSocket interviews)

    Args:
        checkpointer: Optional LangGraph checkpointer for persistence.
                      Use MemorySaver() for in-memory, or PostgresSaver for prod.

    Returns:
        Compiled LangGraph StateGraph
    """
    graph = StateGraph(InterviewState)

    # ── Add Nodes ─────────────────────────────────────────────────────────
    graph.add_node("resume_analyzer", resume_analyzer_node)
    graph.add_node("interview_planner", interview_planner_node)
    graph.add_node("opening", opening_node)
    graph.add_node("question_generator", question_generator_node)
    graph.add_node("answer_analyzer", answer_analyzer_node)
    graph.add_node("follow_up_generator", follow_up_generator_node)
    graph.add_node("stage_advance", stage_advance_node)
    graph.add_node("closing", closing_node)
    graph.add_node("scoring", scoring_node)
    graph.add_node("report_generator", report_generator_node)
    graph.add_node("error_node", error_node)
    # Feature 1: Claim verification (called inline in process_answer, not a graph node)
    # Feature 6: Replanner (called inline in process_answer every N questions)
    # Feature 7: System design evaluator (called inline for system design questions)

    # ── Add Edges ─────────────────────────────────────────────────────────

    # Entry
    graph.add_edge(START, "resume_analyzer")

    # Resume → Planner (with error routing)
    graph.add_conditional_edges(
        "resume_analyzer",
        route_initial_analysis,
        {
            "interview_planner": "interview_planner",
            "error_node": "error_node",
        }
    )

    # Planner → Opening
    graph.add_edge("interview_planner", "opening")

    # Opening → First Question
    graph.add_edge("opening", "question_generator")

    # Question Generator → [PAUSE for answer via WebSocket, resume at answer_analyzer]
    # In event-driven mode: the WebSocket injects the answer and calls answer_analyzer_node directly
    # In automated test mode: question_generator → answer_analyzer
    graph.add_edge("question_generator", "answer_analyzer")

    # Answer Analyzer → Follow-up / Stage Advance / Closing
    graph.add_conditional_edges(
        "answer_analyzer",
        route_after_answer_analysis,
        {
            "follow_up_generator": "follow_up_generator",
            "stage_advance": "stage_advance",
            "closing": "closing",
        }
    )

    # Follow-up → Question Generator (loop)
    graph.add_conditional_edges(
        "follow_up_generator",
        route_after_follow_up,
        {
            "question_generator": "question_generator",
            "closing": "closing",
        }
    )

    # Stage Advance → Question Generator or Closing
    graph.add_conditional_edges(
        "stage_advance",
        route_after_stage_advance,
        {
            "question_generator": "question_generator",
            "closing": "closing",
        }
    )

    # Closing → Scoring → Report → END
    graph.add_edge("closing", "scoring")
    graph.add_edge("scoring", "report_generator")
    graph.add_edge("report_generator", END)
    graph.add_edge("error_node", END)

    # ── Compile ────────────────────────────────────────────────────────────
    checkpointer = checkpointer or MemorySaver()
    compiled = graph.compile(checkpointer=checkpointer)

    logger.info("Interview graph compiled successfully")
    return compiled


# ── Singleton Graph (for WebSocket sessions) ──────────────────────────────────

_graph_instance = None

def get_interview_graph():
    """Get or create the compiled interview graph singleton."""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = build_interview_graph()
    return _graph_instance


# ── Step-by-Step Runner (for WebSocket event-driven mode) ─────────────────────

class InterviewGraphRunner:
    """
    Manages step-by-step execution of the interview graph.

    This runner is used by the WebSocket handler to run the graph
    one "turn" at a time:
    1. Call initialize() for setup phase
    2. Inject the candidate's answer via process_answer()
    3. Get the AI's response

    State is checkpointed to Redis after every mutation (P1).
    Timeline events are recorded for the recruiter portal (P6).
    Sessions can be recovered after restart (P2).
    """

    def __init__(
        self,
        session_id: str,
        initial_state: InterviewState,
        platform_session_id: str = "",
        state_store=None,
    ):
        self.session_id = session_id
        self.platform_session_id = platform_session_id
        self.state = initial_state
        self.graph = get_interview_graph()
        self.config = {"configurable": {"thread_id": session_id}}
        self._initialized = False
        self._last_question_id: str | None = None
        self._store = state_store

    def _checkpoint(self) -> None:
        """Persist state to Redis. Called after every state mutation."""
        if self._store:
            self._store.save_state(self.session_id, self.state)

    def _emit_timeline(self, event_type: str, summary: str, **extra) -> None:
        """Record a timeline event for the recruiter portal."""
        if self._store:
            event = {
                "type": event_type,
                "summary": summary,
                "timestamp": time.time(),
                "question_index": self.state.get("questions_asked", 0),
                **extra,
            }
            self._store.append_timeline_event(self.session_id, event)

    @classmethod
    def restore(cls, session_id: str, state_store=None) -> InterviewGraphRunner | None:
        """
        Restore a runner from Redis checkpoint.
        Returns None if no checkpoint exists.
        """
        store = state_store or __import__("app.ai_interviewer.state_store", fromlist=["get_state_store"]).get_state_store()
        state = store.load_state(session_id)
        if not state:
            return None

        meta = store.load_meta(session_id) or {}
        runner = cls(
            session_id=session_id,
            initial_state=state,
            platform_session_id=meta.get("platform_session_id", ""),
            state_store=store,
        )
        # Determine if the runner was already initialized
        runner._initialized = state.get("phase", "analyzing") != "analyzing"
        logger.info("Restored interview runner from checkpoint", extra={"session": session_id})
        return runner

    async def initialize(self, progress_cb=None) -> str:
        """
        Run the setup phase: resume_analyzer → (claim_extractor ∥ interview_planner) → opening.
        Returns the opening message text.

        The claim extractor and interview planner both depend only on the
        resume analysis, so they run concurrently — this cuts one full LLM
        round-trip (~2-6s) out of the time before Obi starts speaking.
        """
        logger.info("Initializing interview graph", extra={"session": self.session_id})

        async def _emit(status: str) -> None:
            if progress_cb:
                await progress_cb(status)

        # Run resume analyzer
        await _emit("Analyzing your resume…")
        result = await resume_analyzer_node(self.state)
        self.state.update(result)
        self._checkpoint()

        # Claim extraction and interview planning run concurrently
        await _emit("Planning the interview…")
        claim_result, plan_result = await asyncio.gather(
            claim_extractor_node(self.state),
            interview_planner_node(self.state),
        )
        self.state.update(claim_result)
        self.state.update(plan_result)
        self._checkpoint()

        # Generate opening message
        await _emit("Preparing your opening…")
        result = await opening_node(self.state)
        self.state.update(result)
        self._checkpoint()

        self._initialized = True
        self._emit_timeline("interview_started", "Interview session initialized")

        return self.state.get("ai_response_text", "Hello! I'm Obi, let's begin the interview.")

    async def generate_first_question(self) -> str:
        """Generate and return the first interview question."""
        result = await question_generator_node(self.state)
        self.state.update(result)
        self._last_question_id = self.state.get("current_question", {}).get("id")
        self._checkpoint()
        return self.state.get("ai_response_text", "")

    async def process_answer(self, answer_text: str, code_snapshot: str = None) -> dict:
        """
        Process a candidate's answer and return the next AI action.

        Returns a dict with:
        - "text": The AI's response (follow-up or next question)
        - "phase": Current interview phase
        - "should_end": Whether the interview is complete
        - "evaluation": The answer evaluation (for internal tracking)
        """
        logger.info(
            "Processing candidate answer",
            extra={"session": self.session_id, "answer_length": len(answer_text)}
        )

        # Record the answer
        current_question = self.state.get("current_question", {})
        answer_record = {
            "question_id": current_question.get("id", ""),
            "question_text": current_question.get("question", ""),
            "answer_text": answer_text,
            "answered_at": time.time(),
            "duration_seconds": time.time() - self.state.get("question_started_at", time.time()),
        }
        if code_snapshot:
            answer_record["code_snapshot"] = code_snapshot
            self.state["current_code_snapshot"] = code_snapshot

        self.state["current_answer"] = answer_record
        self.state["answers_history"] = list(self.state.get("answers_history", [])) + [answer_record]

        # Add to transcript
        transcript_entry = {
            "role": "candidate",
            "text": answer_text,
            "ts": time.time(),
        }
        self.state["conversation_transcript"] = list(
            self.state.get("conversation_transcript", [])
        ) + [transcript_entry]

        # ── Feature 9: Judge submission against hidden test cases ────────
        # Runs before analysis so the objective pass/fail results can be
        # folded into the LLM evaluation prompt.
        active_problem = self.state.get("active_coding_problem")
        if active_problem and active_problem.get("description") and code_snapshot:
            hidden_cases = active_problem.get("hidden_test_cases", [])
            language = self.state.get("current_code_snapshot_language", "")
            if hidden_cases and language:
                try:
                    test_results = await judge_submission(language, code_snapshot, hidden_cases)
                except Exception as exc:
                    logger.warning(
                        "Hidden test judging failed",
                        extra={"session": self.session_id, "error": str(exc)},
                    )
                    test_results = None
                if test_results and test_results.get("ok"):
                    self.state["code_test_results"] = test_results
                    self._emit_timeline(
                        "code_tested",
                        f"Hidden tests: {test_results['passed']}/{test_results['total']} passed",
                    )

        # ── Run answer analyzer + claim verifier in parallel ─────────────
        # These LLM calls only read the answer/question and write disjoint
        # state keys, so running them concurrently cuts per-turn latency from
        # ~3 sequential round-trips to ~1 (the slowest of the batch).
        analysis_coros = [
            answer_analyzer_node(self.state),
            claim_verifier_node(self.state),
        ]
        if self.state.get("is_system_design_mode", False):
            analysis_coros.append(system_design_evaluator_node(self.state))

        results = await asyncio.gather(*analysis_coros)
        eval_result = results[0]
        for res in results:
            self.state.update(res)

        # ── Feature 5: Track code evolution ───────────────────────────────
        if code_snapshot:
            code_history = list(self.state.get("code_history", []))
            question_id = current_question.get("id", "")
            language = self.state.get("current_code_snapshot_language", "")
            from app.ai_interviewer.state import CodeVersion
            version_num = len(code_history) + 1
            diff_summary = ""
            if code_history:
                prev_code = code_history[-1].get("code", "")
                old_lines = set(prev_code.strip().splitlines())
                new_lines = set(code_snapshot.strip().splitlines())
                added = new_lines - old_lines
                removed = old_lines - new_lines
                parts = []
                if added:
                    parts.append(f"+{len(added)} lines")
                if removed:
                    parts.append(f"-{len(removed)} lines")
                diff_summary = ", ".join(parts) if parts else "No changes"

            code_history.append(CodeVersion(
                version_id=version_num,
                timestamp=time.time(),
                question_id=question_id,
                code=code_snapshot,
                language=language,
                diff_summary=diff_summary,
            ))
            self.state["code_history"] = code_history

        # ── Emit timeline events (P6) ─────────────────────────────────────
        evaluation = eval_result.get("current_evaluation", {})
        quality = evaluation.get("overall_quality", "average")
        scores = [evaluation.get(d, 5) for d in [
            "technical_accuracy", "depth", "clarity",
            "confidence", "completeness", "communication_quality"
        ]]
        avg_score = sum(scores) / len(scores) if scores else 5

        if code_snapshot:
            self._emit_timeline(
                "code_submitted",
                f"Submitted code ({language}) with {diff_summary}" if diff_summary else f"Submitted code ({language})",
                language=language,
            )

        # Claim verification events
        updated_claims = self.state.get("resume_claims", [])
        for claim in updated_claims:
            if claim.get("verification_status") == "VERIFIED":
                self._emit_timeline("claim_verified", f"Claim verified: {claim.get('claim_text', '')[:100]}")
            elif claim.get("verification_status") == "FAILED_VERIFICATION":
                self._emit_timeline("claim_failed", f"Claim failed: {claim.get('claim_text', '')[:100]}")

        # Contradiction events
        facts = self.state.get("candidate_facts", [])
        contradictions = [f for f in facts if f.get("contradicted")]
        if contradictions:
            latest = contradictions[-1]
            self._emit_timeline(
                "contradiction_detected",
                f"Contradiction detected: {latest.get('statement', '')[:100]}",
            )

        # Answer quality event
        if avg_score >= 7:
            self._emit_timeline(
                "strong_answer",
                f"Strong explanation (quality: {quality}, avg: {avg_score:.1f}/10)",
            )
        elif avg_score <= 4:
            self._emit_timeline(
                "weak_answer",
                f"Weak response (quality: {quality}, avg: {avg_score:.1f}/10)",
            )

        # Checkpoint after processing
        self._checkpoint()

        # Check if interview should end
        should_end = self.state.get("should_end", False)
        questions_asked = self.state.get("questions_asked", 0)
        main_questions_asked = self.state.get("main_questions_asked", 0)
        max_questions = self.state.get("max_questions", 12)
        max_turns = self.state.get("max_turns", max_questions * 2)

        if should_end or questions_asked >= max_turns:
            return await self._finalize()

        # Decide: follow-up or next question
        should_follow_up = self.state.get("_should_follow_up", False)

        if should_follow_up:
            result = await follow_up_generator_node(self.state)
            self.state.update(result)
            self._checkpoint()
            self._emit_timeline(
                "follow_up",
                f"Follow-up question asked on: {current_question.get('topic', 'unknown')}",
            )
            return {
                "text": self.state.get("ai_response_text", ""),
                "phase": "interviewing",
                "should_end": False,
                "is_follow_up": True,
                "evaluation": eval_result.get("current_evaluation", {}),
                "questions_asked": self.state.get("questions_asked", 0),
                "main_questions_asked": self.state.get("main_questions_asked", 0),
                "max_questions": max_questions,
            }

        # Advance stage if needed
        advance_result = await stage_advance_node(self.state)
        if advance_result:
            self.state.update(advance_result)
            self._checkpoint()
            # If stage advance emitted a transition, send it
            if advance_result.get("ai_response_text"):
                new_stage = self.state.get("current_stage", {}).get("name", "")
                self._emit_timeline(
                    "stage_transition",
                    f"Stage transition: now in {new_stage}",
                    stage=new_stage,
                )
                return {
                    "text": advance_result["ai_response_text"],
                    "phase": "interviewing",
                    "should_end": False,
                    "is_transition": True,
                    "evaluation": eval_result.get("current_evaluation", {}),
                    "questions_asked": self.state.get("questions_asked", 0),
                    "main_questions_asked": self.state.get("main_questions_asked", 0),
                    "max_questions": max_questions,
                }

        # ── Feature 6: Dynamic replanning every 3 questions ───────────────
        replan_count = self.state.get("replan_count", 0)
        questions_since_replan = main_questions_asked - (replan_count * 3)
        if questions_since_replan >= 3:
            replan_result = await interview_replanner_node(self.state)
            if replan_result:
                self.state.update(replan_result)
                self._checkpoint()
                self._emit_timeline(
                    "replan",
                    f"Interview replanned (plan #{replan_count + 1})",
                )

        # Check should_end after stage advance
        if self.state.get("should_end", False) or self.state.get("questions_asked", 0) >= max_turns:
            return await self._finalize()

        # Generate next question
        q_result = await question_generator_node(self.state)
        self.state.update(q_result)
        self._last_question_id = self.state.get("current_question", {}).get("id")
        self._checkpoint()

        return {
            "text": self.state.get("ai_response_text", ""),
            "phase": "interviewing",
            "should_end": False,
            "is_follow_up": False,
            "evaluation": eval_result.get("current_evaluation", {}),
            "questions_asked": self.state.get("questions_asked", 0),
            "main_questions_asked": self.state.get("main_questions_asked", 0),
            "max_questions": max_questions,
        }

    async def _finalize(self) -> dict:
        """Run closing, scoring, and report generation."""
        logger.info("Finalizing interview", extra={"session": self.session_id})

        # Closing
        closing_result = await closing_node(self.state)
        self.state.update(closing_result)
        closing_text = self.state.get("ai_response_text", "Thank you for your time.")
        self._emit_timeline("interview_completed", "Interview finished, generating report")

        # Scoring
        score_result = await scoring_node(self.state)
        self.state.update(score_result)

        # Report
        report_result = await report_generator_node(self.state)
        self.state.update(report_result)

        # Final checkpoint
        self._checkpoint()

        return {
            "text": closing_text,
            "phase": "completed",
            "should_end": True,
            "final_report": self.state.get("final_report", {}),
            "questions_asked": self.state.get("questions_asked", 0),
            "main_questions_asked": self.state.get("main_questions_asked", 0),
            "max_questions": self.state.get("max_questions", 12),
        }

    def get_state(self) -> InterviewState:
        """Return the current full state."""
        return self.state

    def get_final_report(self) -> dict:
        """Return the final report if available."""
        return self.state.get("final_report", {})
