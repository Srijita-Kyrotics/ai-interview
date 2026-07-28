"""
Evidence Graph
==============
Structured evidence chain for claim verification, scoring, and reporting.

Architecture:
  Claim
    ├── Evidence 1 (supports)
    ├── Evidence 2 (refutes)
    └── Evidence 3 (supports)

The evidence graph provides:
1. Structured evidence chains per claim (not just flat strings)
2. Evidence strength scoring
3. Support/refute classification
4. Aggregated verification confidence
5. Rich report generation

Used by:
- claim_verifier_node: Populates evidence after each answer
- scoring_node: Uses evidence quality in scoring
- report_generator_node: Renders evidence chains in reports
"""

from __future__ import annotations

import logging
import uuid

from app.ai_interviewer.state import EvidenceNode, ResumeClaim

logger = logging.getLogger("ai_interview.evidence_graph")


class EvidenceGraph:
    """
    Manages the evidence graph for an interview session.

    Stores claim→evidence relationships and provides methods for:
    - Adding evidence to claims
    - Computing verification confidence
    - Generating summaries for reports
    - Detecting conflicting evidence
    """

    def __init__(self, claims: list[ResumeClaim] | None = None):
        # claim_id → list of EvidenceNode
        self._graph: dict[str, list[EvidenceNode]] = {}
        self._claims = {c["claim_id"]: c for c in (claims or [])}

    def add_evidence(
        self,
        claim_id: str,
        question_id: str,
        question_text: str,
        answer_excerpt: str,
        supports_claim: bool,
        strength: str = "moderate",
        reasoning: str = "",
    ) -> EvidenceNode:
        """Add a piece of evidence to a claim's chain."""
        evidence = EvidenceNode(
            evidence_id=str(uuid.uuid4())[:8],
            question_id=question_id,
            question_text=question_text,
            answer_excerpt=answer_excerpt,
            supports_claim=supports_claim,
            strength=strength,
            reasoning=reasoning,
        )

        if claim_id not in self._graph:
            self._graph[claim_id] = []
        self._graph[claim_id].append(evidence)

        logger.debug(
            "Added evidence to claim %s: supports=%s, strength=%s",
            claim_id, supports_claim, strength,
        )
        return evidence

    def get_evidence_chain(self, claim_id: str) -> list[EvidenceNode]:
        """Get all evidence for a specific claim."""
        return self._graph.get(claim_id, [])

    def get_supporting_evidence(self, claim_id: str) -> list[EvidenceNode]:
        """Get evidence that supports a claim."""
        return [e for e in self._graph.get(claim_id, []) if e["supports_claim"]]

    def get_refuting_evidence(self, claim_id: str) -> list[EvidenceNode]:
        """Get evidence that refutes a claim."""
        return [e for e in self._graph.get(claim_id, []) if not e["supports_claim"]]

    def compute_verification_confidence(self, claim_id: str) -> dict:
        """
        Compute verification confidence for a claim based on its evidence chain.

        Returns:
            {
                "confidence": "high" | "medium" | "low",
                "support_score": float (0-1),
                "evidence_count": int,
                "has_strong_support": bool,
                "has_strong_refutation": bool,
                "net_strength": float (-1 to 1),
            }
        """
        evidence = self._graph.get(claim_id, [])
        if not evidence:
            return {
                "confidence": "low",
                "support_score": 0.5,
                "evidence_count": 0,
                "has_strong_support": False,
                "has_strong_refutation": False,
                "net_strength": 0.0,
            }

        strength_map = {"strong": 1.0, "moderate": 0.6, "weak": 0.3}

        support_score = 0.0
        total_weight = 0.0
        has_strong_support = False
        has_strong_refutation = False

        for e in evidence:
            weight = strength_map.get(e.get("strength", "moderate"), 0.6)
            total_weight += weight
            if e["supports_claim"]:
                support_score += weight
                if e["strength"] == "strong":
                    has_strong_support = True
            else:
                support_score -= weight
                if e["strength"] == "strong":
                    has_strong_refutation = True

        # Normalize to 0-1
        normalized = (support_score + total_weight) / (2 * total_weight) if total_weight > 0 else 0.5

        net_strength = support_score / total_weight if total_weight > 0 else 0.0

        # Determine confidence
        if len(evidence) >= 3 and (has_strong_support or has_strong_refutation):
            confidence = "high"
        elif len(evidence) >= 2 or has_strong_support:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "confidence": confidence,
            "support_score": round(normalized, 3),
            "evidence_count": len(evidence),
            "has_strong_support": has_strong_support,
            "has_strong_refutation": has_strong_refutation,
            "net_strength": round(net_strength, 3),
        }

    def get_claim_status(self, claim_id: str) -> str:
        """Determine claim verification status from evidence."""
        confidence = self.compute_verification_confidence(claim_id)
        evidence = self._graph.get(claim_id, [])

        if not evidence:
            return "UNVERIFIED"

        if confidence["support_score"] >= 0.75 and confidence["confidence"] in ("high", "medium"):
            return "VERIFIED"
        elif confidence["support_score"] <= 0.25 and confidence["confidence"] in ("high", "medium"):
            return "FAILED_VERIFICATION"
        elif evidence:
            return "PARTIALLY_VERIFIED"
        return "UNVERIFIED"

    def has_conflicts(self, claim_id: str) -> bool:
        """Check if a claim has conflicting evidence."""
        supporting = self.get_supporting_evidence(claim_id)
        refuting = self.get_refuting_evidence(claim_id)
        return len(supporting) > 0 and len(refuting) > 0

    def get_all_claims_summary(self) -> list[dict]:
        """Get a summary of all claims with their evidence chains."""
        summaries = []
        for claim_id, evidence in self._graph.items():
            claim = self._claims.get(claim_id, {})
            confidence = self.compute_verification_confidence(claim_id)
            summaries.append({
                "claim_id": claim_id,
                "claim_text": claim.get("claim_text", ""),
                "verification_status": self.get_claim_status(claim_id),
                "confidence": confidence,
                "evidence_count": len(evidence),
                "has_conflicts": self.has_conflicts(claim_id),
                "evidence_chain": [
                    {
                        "evidence_id": e["evidence_id"],
                        "supports": e["supports_claim"],
                        "strength": e["strength"],
                        "excerpt": e["answer_excerpt"][:200],
                        "reasoning": e["reasoning"],
                    }
                    for e in evidence
                ],
            })
        return summaries

    def to_dict(self) -> dict[str, list[dict]]:
        """Serialize the evidence graph for storage."""
        return {
            claim_id: [
                {
                    "evidence_id": e["evidence_id"],
                    "question_id": e["question_id"],
                    "question_text": e["question_text"],
                    "answer_excerpt": e["answer_excerpt"],
                    "supports_claim": e["supports_claim"],
                    "strength": e["strength"],
                    "reasoning": e["reasoning"],
                }
                for e in evidence_list
            ]
            for claim_id, evidence_list in self._graph.items()
        }

    @classmethod
    def from_dict(cls, data: dict[str, list[dict]], claims: list[ResumeClaim] | None = None) -> EvidenceGraph:
        """Deserialize an evidence graph from storage."""
        graph = cls(claims=claims)
        for claim_id, evidence_list in data.items():
            graph._graph[claim_id] = [
                EvidenceNode(**e) for e in evidence_list
            ]
        return graph

    @classmethod
    def from_claims(cls, claims: list[ResumeClaim]) -> EvidenceGraph:
        """Create an evidence graph from existing claims (for backward compat)."""
        graph = cls(claims=claims)
        for claim in claims:
            claim_id = claim.get("claim_id", "")
            for evidence_text in claim.get("verification_evidence", []):
                graph.add_evidence(
                    claim_id=claim_id,
                    question_id="",
                    question_text="",
                    answer_excerpt=evidence_text,
                    supports_claim=True,
                    strength="moderate",
                    reasoning="",
                )
        return graph
