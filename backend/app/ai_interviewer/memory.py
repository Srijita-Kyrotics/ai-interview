"""
Interview Memory Manager
========================
Manages stateful memory throughout the interview session.
Handles topic tracking, strength/weakness accumulation,
context compression for long interviews, claim verification,
fact memory, topic mastery, and difficulty management.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.ai_interviewer.state import (
    InterviewMemory,
    AnswerEvaluation,
    QuestionRecord,
    ResumeClaim,
    TopicMastery,
    CandidateFact,
    DifficultyLevel,
    CodeVersion,
)


class MemoryManager:
    """
    Manages the interview memory state.

    The memory system tracks:
    - Questions already asked (to avoid repeats)
    - Topics covered vs still pending
    - Running tally of strengths and weaknesses
    - Unresolved claims that need follow-up
    - Depth map: how deep we've gone on each topic

    Feature extensions:
    - Claim verification: tracks resume claims and their verification status
    - Fact memory: extracts factual statements for contradiction detection
    - Topic mastery: per-topic mastery scores (0-10)
    - Difficulty escalation: adaptive difficulty based on performance
    - Code evolution: tracks code changes across questions
    """

    def __init__(
        self,
        memory: InterviewMemory,
        plan_topics: list[str],
        resume_claims: list[ResumeClaim] | None = None,
        topic_mastery: dict[str, TopicMastery] | None = None,
        candidate_facts: list[CandidateFact] | None = None,
        difficulty_level: DifficultyLevel | None = None,
        code_history: list[CodeVersion] | None = None,
    ):
        self.memory = memory
        self.resume_claims = resume_claims or []
        self.topic_mastery = topic_mastery or {}
        self.candidate_facts = candidate_facts or []
        self.difficulty_level = difficulty_level or DifficultyLevel(
            level="intermediate",
            level_numeric=2,
            overall_mastery=5.0,
            resume_seniority="mid",
            consecutive_strong=0,
            consecutive_weak=0,
        )
        self.code_history = code_history or []

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

        # ── Update topic mastery ──────────────────────────────────────────
        self._update_topic_mastery(topic, eval_result)

        # ── Update difficulty level ───────────────────────────────────────
        self._update_difficulty(eval_result)

    # ── Claim Tracking (Feature 1) ────────────────────────────────────────

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

    def update_claim_status(
        self,
        claim_id: str,
        status: str,
        evidence: str,
        question_id: str,
    ) -> None:
        """Update a resume claim's verification status with evidence."""
        for claim in self.resume_claims:
            if claim["claim_id"] == claim_id:
                claim["verification_status"] = status
                if evidence and evidence not in claim["verification_evidence"]:
                    claim["verification_evidence"].append(evidence)
                if question_id and question_id not in claim["asked_question_ids"]:
                    claim["asked_question_ids"].append(question_id)
                break

    def add_resume_claim(self, claim_text: str, source: str, skill: str = "") -> str:
        """Add a new resume claim to track. Returns the claim_id."""
        claim_id = str(uuid.uuid4())[:8]
        claim: ResumeClaim = {
            "claim_id": claim_id,
            "claim_text": claim_text,
            "source": source,
            "skill": skill,
            "verification_status": "UNVERIFIED",
            "verification_evidence": [],
            "asked_question_ids": [],
        }
        self.resume_claims.append(claim)
        return claim_id

    def get_unverified_claims(self) -> list[ResumeClaim]:
        """Return claims that haven't been verified yet."""
        return [c for c in self.resume_claims if c["verification_status"] == "UNVERIFIED"]

    def get_verified_claims(self) -> list[ResumeClaim]:
        """Return verified claims."""
        return [c for c in self.resume_claims if c["verification_status"] == "VERIFIED"]

    def get_failed_claims(self) -> list[ResumeClaim]:
        """Return claims that failed verification."""
        return [c for c in self.resume_claims if c["verification_status"] == "FAILED_VERIFICATION"]

    # ── Fact Memory (Feature 3) ───────────────────────────────────────────

    def add_candidate_fact(
        self,
        statement: str,
        topic: str,
        question_id: str,
    ) -> str:
        """Add a factual statement extracted from a candidate answer."""
        fact_id = str(uuid.uuid4())[:8]
        fact: CandidateFact = {
            "fact_id": fact_id,
            "statement": statement,
            "topic": topic,
            "source_question_id": question_id,
            "timestamp": time.time(),
            "contradicted": False,
        }
        self.candidate_facts.append(fact)
        return fact_id

    def mark_contradiction(
        self,
        fact_id: str,
        contradicting_fact_id: str,
        evidence: str,
    ) -> None:
        """Mark a fact as contradicted by another fact."""
        for fact in self.candidate_facts:
            if fact["fact_id"] == fact_id:
                fact["contradicted"] = True
                fact["contradicted_by"] = contradicting_fact_id
                fact["contradiction_evidence"] = evidence
                break

    def get_facts_by_topic(self, topic: str) -> list[CandidateFact]:
        """Get all candidate facts for a specific topic."""
        return [f for f in self.candidate_facts if f["topic"] == topic]

    def get_contradictions(self) -> list[CandidateFact]:
        """Get all contradicted facts."""
        return [f for f in self.candidate_facts if f["contradicted"]]

    # ── Topic Mastery (Feature 2) ─────────────────────────────────────────

    def _update_topic_mastery(self, topic: str, eval_result: AnswerEvaluation) -> None:
        """Update mastery score for a topic based on latest evaluation."""
        tech = eval_result.get("technical_accuracy", 5)
        depth = eval_result.get("depth", 5)
        completeness = eval_result.get("completeness", 5)
        new_score = (tech * 0.4 + depth * 0.35 + completeness * 0.25)

        if topic in self.topic_mastery:
            existing = self.topic_mastery[topic]
            # Exponential moving average (alpha=0.4)
            alpha = 0.4
            updated_score = alpha * new_score + (1 - alpha) * existing["mastery_score"]
            existing["mastery_score"] = round(updated_score, 2)
            existing["questions_asked"] += 1
            existing["avg_technical_accuracy"] = (
                (existing["avg_technical_accuracy"] * (existing["questions_asked"] - 1) + tech)
                / existing["questions_asked"]
            )
            existing["avg_depth"] = (
                (existing["avg_depth"] * (existing["questions_asked"] - 1) + depth)
                / existing["questions_asked"]
            )
            existing["last_assessed_at"] = time.time()
        else:
            self.topic_mastery[topic] = TopicMastery(
                topic=topic,
                mastery_score=round(new_score, 2),
                questions_asked=1,
                avg_technical_accuracy=float(tech),
                avg_depth=float(depth),
                last_assessed_at=time.time(),
            )

    def get_overall_mastery(self) -> float:
        """Compute average mastery across all topics."""
        if not self.topic_mastery:
            return 5.0
        scores = [m["mastery_score"] for m in self.topic_mastery.values()]
        return round(sum(scores) / len(scores), 2)

    def get_weak_mastery_topics(self, threshold: float = 5.0) -> list[str]:
        """Return topics where mastery is below threshold."""
        return [
            t for t, m in self.topic_mastery.items()
            if m["mastery_score"] < threshold
        ]

    def get_strong_mastery_topics(self, threshold: float = 8.0) -> list[str]:
        """Return topics where mastery is above threshold."""
        return [
            t for t, m in self.topic_mastery.items()
            if m["mastery_score"] >= threshold
        ]

    # ── Difficulty Escalation (Feature 4) ─────────────────────────────────

    def _update_difficulty(self, eval_result: AnswerEvaluation) -> None:
        """Update difficulty level based on answer quality."""
        tech = eval_result.get("technical_accuracy", 5)
        depth = eval_result.get("depth", 5)
        completeness = eval_result.get("completeness", 5)
        avg = (tech + depth + completeness) / 3

        if avg >= 7:
            self.difficulty_level["consecutive_strong"] += 1
            self.difficulty_level["consecutive_weak"] = 0
        elif avg <= 4:
            self.difficulty_level["consecutive_weak"] += 1
            self.difficulty_level["consecutive_strong"] = 0
        else:
            self.difficulty_level["consecutive_strong"] = 0
            self.difficulty_level["consecutive_weak"] = 0

        # Escalate: 3+ consecutive strong answers → level up
        if self.difficulty_level["consecutive_strong"] >= 3:
            current = self.difficulty_level["level_numeric"]
            if current < 4:
                self.difficulty_level["level_numeric"] = current + 1
                self.difficulty_level["consecutive_strong"] = 0

        # De-escalate: 3+ consecutive weak answers → level down
        if self.difficulty_level["consecutive_weak"] >= 3:
            current = self.difficulty_level["level_numeric"]
            if current > 1:
                self.difficulty_level["level_numeric"] = current - 1
                self.difficulty_level["consecutive_weak"] = 0

        # Map numeric to string
        level_map = {1: "beginner", 2: "intermediate", 3: "advanced", 4: "expert"}
        self.difficulty_level["level"] = level_map[self.difficulty_level["level_numeric"]]

        # Update overall mastery
        self.difficulty_level["overall_mastery"] = self.get_overall_mastery()

    def set_initial_difficulty_from_resume(self, seniority: str) -> None:
        """Seed difficulty level from resume seniority analysis."""
        seniority_map = {"junior": 1, "mid": 2, "senior": 3, "staff": 4}
        level_num = seniority_map.get(seniority, 2)
        self.difficulty_level["level_numeric"] = level_num
        self.difficulty_level["resume_seniority"] = seniority
        level_map = {1: "beginner", 2: "intermediate", 3: "advanced", 4: "expert"}
        self.difficulty_level["level"] = level_map[level_num]

    # ── Code Evolution (Feature 5) ────────────────────────────────────────

    def add_code_version(
        self,
        code: str,
        question_id: str,
        language: str = "",
    ) -> int:
        """Add a new code snapshot and return its version number."""
        version_num = len(self.code_history) + 1
        diff_summary = ""

        if self.code_history:
            prev = self.code_history[-1]["code"]
            diff_summary = self._summarize_code_diff(prev, code)

        version: CodeVersion = {
            "version_id": version_num,
            "timestamp": time.time(),
            "question_id": question_id,
            "code": code,
            "language": language,
            "diff_summary": diff_summary,
        }
        self.code_history.append(version)
        return version_num

    def _summarize_code_diff(self, old_code: str, new_code: str) -> str:
        """Generate a simple diff summary between two code versions."""
        old_lines = set(old_code.strip().splitlines())
        new_lines = set(new_code.strip().splitlines())
        added = new_lines - old_lines
        removed = old_lines - new_lines
        parts = []
        if added:
            parts.append(f"+{len(added)} lines")
        if removed:
            parts.append(f"-{len(removed)} lines")
        if not parts:
            return "No changes"
        return ", ".join(parts)

    def get_code_evolution_summary(self) -> list[dict]:
        """Return a summary of code evolution for reporting."""
        return [
            {
                "version": v["version_id"],
                "timestamp": v["timestamp"],
                "language": v.get("language", ""),
                "diff_summary": v.get("diff_summary", ""),
                "code_preview": v["code"][:200],
            }
            for v in self.code_history
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
            # Feature 1: claim verification summary
            "claims_verified": len(self.get_verified_claims()),
            "claims_failed": len(self.get_failed_claims()),
            "claims_unverified": len(self.get_unverified_claims()),
            # Feature 2: topic mastery
            "topic_mastery": {
                t: m["mastery_score"] for t, m in self.topic_mastery.items()
            },
            # Feature 3: contradictions
            "contradictions_found": len(self.get_contradictions()),
            # Feature 4: difficulty level
            "difficulty_level": self.difficulty_level["level"],
            # Feature 5: code versions
            "code_versions_submitted": len(self.code_history),
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
        if self.difficulty_level["level"] != "intermediate":
            memory_text.append(f"DIFFICULTY: {self.difficulty_level['level']}")
        weak_topics = self.get_weak_mastery_topics()
        if weak_topics:
            memory_text.append(f"WEAK_MASTERY: {', '.join(weak_topics[:3])}")

        memory_str = " | ".join(memory_text) if memory_text else ""

        return f"{turn_text}\n\n[Memory: {memory_str}]" if memory_str else turn_text

    def get_full_memory(self) -> InterviewMemory:
        """Return the current memory state."""
        return self.memory
