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

import logging
from typing import Literal

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.ai_interviewer.state import InterviewState
from app.ai_interviewer.nodes import (
    resume_analyzer_node,
    interview_planner_node,
    question_generator_node,
    answer_analyzer_node,
    follow_up_generator_node,
    scoring_node,
    report_generator_node,
    stage_advance_node,
    opening_node,
    closing_node,
)

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

    if should_end or questions_asked >= max_questions:
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
    if state.get("questions_asked", 0) >= state.get("max_questions", 12):
        return "closing"
    return "question_generator"


def route_after_follow_up(state: InterviewState) -> Literal[
    "question_generator", "closing"
]:
    """After generating a follow-up, route appropriately."""
    if state.get("questions_asked", 0) >= state.get("max_questions", 12):
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

def build_interview_graph(checkpointer=None) -> "CompiledGraph":
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
    1. Call next() to get the next AI action (question/message)
    2. Inject the candidate's answer
    3. Call next() again to get the AI's response
    
    Each session has its own runner instance.
    """

    def __init__(self, session_id: str, initial_state: InterviewState):
        self.session_id = session_id
        self.state = initial_state
        self.graph = get_interview_graph()
        self.config = {"configurable": {"thread_id": session_id}}
        self._initialized = False

    async def initialize(self) -> str:
        """
        Run the setup phase: resume_analyzer → interview_planner → opening.
        Returns the opening message text.
        """
        logger.info("Initializing interview graph", extra={"session": self.session_id})

        # Run resume analyzer
        result = await resume_analyzer_node(self.state)
        self.state.update(result)

        # Run interview planner
        result = await interview_planner_node(self.state)
        self.state.update(result)

        # Generate opening message
        result = await opening_node(self.state)
        self.state.update(result)

        self._initialized = True
        return self.state.get("ai_response_text", "Hello! I'm Alex, let's begin the interview.")

    async def generate_first_question(self) -> str:
        """Generate and return the first interview question."""
        result = await question_generator_node(self.state)
        self.state.update(result)
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
        import time

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

        # Run answer analyzer
        eval_result = await answer_analyzer_node(self.state)
        self.state.update(eval_result)

        # Check if interview should end
        should_end = self.state.get("should_end", False)
        questions_asked = self.state.get("questions_asked", 0)
        max_questions = self.state.get("max_questions", 12)

        if should_end or questions_asked >= max_questions:
            return await self._finalize()

        # Decide: follow-up or next question
        should_follow_up = self.state.get("_should_follow_up", False)

        if should_follow_up:
            result = await follow_up_generator_node(self.state)
            self.state.update(result)
            return {
                "text": self.state.get("ai_response_text", ""),
                "phase": "interviewing",
                "should_end": False,
                "is_follow_up": True,
                "evaluation": eval_result.get("current_evaluation", {}),
                "questions_asked": self.state.get("questions_asked", 0),
                "max_questions": max_questions,
            }

        # Advance stage if needed
        advance_result = await stage_advance_node(self.state)
        if advance_result:
            self.state.update(advance_result)
            # If stage advance emitted a transition, send it
            if advance_result.get("ai_response_text"):
                return {
                    "text": advance_result["ai_response_text"],
                    "phase": "interviewing",
                    "should_end": False,
                    "is_transition": True,
                    "evaluation": eval_result.get("current_evaluation", {}),
                    "questions_asked": self.state.get("questions_asked", 0),
                    "max_questions": max_questions,
                }

        # Check should_end after stage advance
        if self.state.get("should_end", False) or self.state.get("questions_asked", 0) >= max_questions:
            return await self._finalize()

        # Generate next question
        q_result = await question_generator_node(self.state)
        self.state.update(q_result)

        return {
            "text": self.state.get("ai_response_text", ""),
            "phase": "interviewing",
            "should_end": False,
            "is_follow_up": False,
            "evaluation": eval_result.get("current_evaluation", {}),
            "questions_asked": self.state.get("questions_asked", 0),
            "max_questions": max_questions,
        }

    async def _finalize(self) -> dict:
        """Run closing, scoring, and report generation."""
        logger.info("Finalizing interview", extra={"session": self.session_id})

        # Closing
        closing_result = await closing_node(self.state)
        self.state.update(closing_result)
        closing_text = self.state.get("ai_response_text", "Thank you for your time.")

        # Scoring
        score_result = await scoring_node(self.state)
        self.state.update(score_result)

        # Report
        report_result = await report_generator_node(self.state)
        self.state.update(report_result)

        return {
            "text": closing_text,
            "phase": "completed",
            "should_end": True,
            "final_report": self.state.get("final_report", {}),
            "questions_asked": self.state.get("questions_asked", 0),
            "max_questions": self.state.get("max_questions", 12),
        }

    def get_state(self) -> InterviewState:
        """Return the current full state."""
        return self.state

    def get_final_report(self) -> dict:
        """Return the final report if available."""
        return self.state.get("final_report", {})
