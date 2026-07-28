"""
Interview Memory Manager
========================
Manages stateful memory throughout the interview session.
Handles topic tracking, strength/weakness accumulation, and
context compression for long interviews.
"""

from __future__ import annotations

import time
from typing import Any

from app.ai_interviewer.state import InterviewMemory, AnswerEvaluation, QuestionRecord


class MemoryManager:
    """
    Manages the interview memory state.
    
    The memory system tracks:
    - Questions already asked (to avoid repeats)
    - Topics covered vs still pending  
    - Running tally of strengths and weaknesses
    - Unresolved claims that need follow-up
    - Depth map: how deep we've gone on each topic
    """

    def __init__(self, memory: InterviewMemory, plan_topics: list[str]):
        self.memory = memory
        # Populate pending topics from plan
        if not memory["topics_pending"] and plan_topics:
            memory["topics_pending"] = plan_topics.copy()

    # ── Question Tracking ─────────────────────────────────────────────────

    def mark_question_asked(self, question_id: str, topic: str) -> None:
        """Record that a question was asked."""
        if question_id not in self.memory["questions_asked"]:
            self.memory["questions_asked"].append(question_id)
        # Move topic from pending to covered if needed
        if topic in self.memory["topics_pending"]:
            self.memory["topics_pending"].remove(topic)
        if topic not in self.memory["topics_covered"]:
            self.memory["topics_covered"].append(topic)
        # Increment depth for this topic
        self.memory["depth_map"][topic] = self.memory["depth_map"].get(topic, 0) + 1

    def has_asked_about(self, topic: str) -> bool:
        """Check if a topic has been covered."""
        return topic in self.memory["topics_covered"]

    def get_topic_depth(self, topic: str) -> int:
        """Get how many questions we've asked about a specific topic."""
        return self.memory["depth_map"].get(topic, 0)

    def get_next_priority_topic(self) -> str | None:
        """Return the highest-priority pending topic."""
        if self.memory["topics_pending"]:
            return self.memory["topics_pending"][0]
        return None

    # ── Answer Evaluation Processing ──────────────────────────────────────

    def process_evaluation(self, eval_result: AnswerEvaluation, topic: str) -> None:
        """Update memory based on an answer evaluation."""
        overall = eval_result.get("overall_quality", "average")
        
        # Record strengths
        for signal in eval_result.get("positive_signals", []):
            entry = f"[{topic}] {signal}"
            if entry not in self.memory["candidate_strengths"]:
                self.memory["candidate_strengths"].append(entry)

        # Record weaknesses
        for point in eval_result.get("missing_points", []):
            entry = f"[{topic}] Missing: {point}"
            if entry not in self.memory["candidate_weaknesses"]:
                self.memory["candidate_weaknesses"].append(entry)

        # Record red flags as unresolved claims
        for flag in eval_result.get("red_flags", []):
            entry = f"[{topic}] {flag}"
            if entry not in self.memory["unresolved_claims"]:
                self.memory["unresolved_claims"].append(entry)

        # Track positive/concerning moments
        if overall == "excellent":
            self.memory["positive_moments"].append(
                f"Excellent answer on {topic}"
            )
        elif overall == "poor":
            self.memory["concerning_moments"].append(
                f"Poor answer on {topic}"
            )

    # ── Claim Tracking ────────────────────────────────────────────────────

    def add_unresolved_claim(self, claim: str) -> None:
        """Add a claim that needs verification."""
        if claim not in self.memory["unresolved_claims"]:
            self.memory["unresolved_claims"].append(claim)

    def resolve_claim(self, claim_fragment: str) -> None:
        """Mark a claim as resolved (partial match)."""
        self.memory["unresolved_claims"] = [
            c for c in self.memory["unresolved_claims"]
            if claim_fragment.lower() not in c.lower()
        ]

    # ── Context Generation ────────────────────────────────────────────────

    def get_summary_for_prompt(self) -> dict[str, Any]:
        """Return a concise memory snapshot for use in prompts."""
        return {
            "topics_covered": self.memory["topics_covered"][-10:],  # last 10
            "topics_pending": self.memory["topics_pending"][:5],    # top 5 pending
            "strengths": self.memory["candidate_strengths"][-5:],   # last 5 strengths
            "weaknesses": self.memory["candidate_weaknesses"][-5:], # last 5 weaknesses
            "unresolved_claims": self.memory["unresolved_claims"][:3],  # top 3 unresolved
        }

    def get_compression_context(self, transcript: list[dict], max_turns: int = 6) -> str:
        """
        Generate a compressed context string for long interviews.
        Keeps the last max_turns of conversation + key memory signals.
        """
        # Last N conversation turns
        recent_turns = transcript[-max_turns * 2:] if transcript else []
        turn_text = "\n".join(
            f"{t['role'].upper()}: {t['text'][:300]}"
            for t in recent_turns
        )

        # Key memory signals
        memory_text = []
        if self.memory["unresolved_claims"]:
            memory_text.append(f"UNRESOLVED: {', '.join(self.memory['unresolved_claims'][:2])}")
        if self.memory["candidate_weaknesses"]:
            memory_text.append(f"WEAK AREAS: {', '.join([w.split(']')[-1].strip() for w in self.memory['candidate_weaknesses'][-2:]])}")

        memory_str = " | ".join(memory_text) if memory_text else ""

        return f"{turn_text}\n\n[Memory: {memory_str}]" if memory_str else turn_text

    def get_full_memory(self) -> InterviewMemory:
        """Return the current memory state."""
        return self.memory
