"""
Objective Communication & Prosody Analysis
===========================================

Computes deterministic, explainable communication metrics from a candidate's
answer text and timing so the final report is not entirely dependent on LLM
judgement. Every score is normalized to 0-10 and paired with human-readable
evidence strings.

The analyzer is intentionally dependency-free (pure stdlib) so it can be unit
tested offline without API keys.

Scores returned (0-10, higher is better):
  fluency          - filler-word density (um, uh, like, you know, ...)
  hedged           - hedging density ("i think", "maybe", "not sure", ...)
  speaking_rate    - words-per-minute, penalizing both too slow and too fast
  response_latency - time between the question and the start of the answer
  structure        - presence of signposting / structure markers
  vocabulary       - lexical diversity (type-token ratio) + sentence complexity
  conciseness      - answer length relative to the question complexity
  clarity          - blended readability proxy from sentence structure
  overall_score    - weighted aggregate

A voice-mode hint can be passed in (paralinguistic_flags) when prosody
metadata is available (e.g. from a future streaming STT layer).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

# ── Word lists ────────────────────────────────────────────────────────────────

FILLER_WORDS = (
    "um", "uh", "er", "ah", "hmm", "like", "you know", "i mean", "kinda",
    "sort of", "sorta", "basically", "literally", "actually", "right",
    "well", "so yeah", "you know what i mean",
)

# Hedge verbs/adverbs signal uncertainty, often overclaim-adjacent.
HEDGE_WORDS = (
    "i think", "i guess", "i suppose", "i believe", "i feel like", "maybe",
    "perhaps", "probably", "possibly", "i'm not sure", "not really sure",
    "i don't know", "i dunno", "kinda", "sort of", "sorta", "somewhat",
    "might be", "could be", "i assume", "i'd say", "as far as i know",
    "i recall", "i don't remember exactly", "not 100% sure",
)

# Self-interruption / stutter patterns that break fluency.
_STUTTER_RE = re.compile(r"\b(\w+)\s+\1\b", re.IGNORECASE)  # "the the", "I I"
_RESTART_RE = re.compile(r"\b(\w{3,})\s+\1\s+\1\b", re.IGNORECASE)

STRUCTURE_MARKERS = (
    "first", "firstly", "second", "secondly", "third", "finally", "lastly",
    "additionally", "furthermore", "moreover", "however", "therefore",
    "in conclusion", "to summarize", "for example", "in other words",
    "as a result", "on the other hand", "in practice", "in terms of",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_words(text: str) -> list[str]:
    """Lowercase, split on non-word chars, drop empties."""
    return [w for w in re.sub(r"[^a-zA-Z']+", " ", text.lower()).split() if w]


def _count_phrases(text: str, phrases: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(lowered.count(p) for p in phrases)


def _clamp(value: float, lo: float = 0.0, hi: float = 10.0) -> float:
    return max(lo, min(hi, value))


def _score_inverse(density: float, max_penalty_at: float) -> float:
    """Map density 0→10 down to density>=max_penalty_at→0 linearly."""
    if density <= 0:
        return 10.0
    return _clamp(10.0 * (1.0 - density / max_penalty_at))


def _bell(score: float, ideal_lo: float, ideal_hi: float, span: float) -> float:
    """Penalize values outside the ideal window on a smooth bell curve."""
    if score < ideal_lo:
        return _clamp(10.0 - ((ideal_lo - score) / span) * 10.0)
    if score > ideal_hi:
        return _clamp(10.0 - ((score - ideal_hi) / span) * 10.0)
    return 10.0


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class CommunicationMetrics:
    """Objective communication metrics for one answer."""

    # Raw signals
    word_count: int = 0
    sentence_count: int = 0
    avg_sentence_length: float = 0.0
    speaking_rate_wpm: float | None = None
    response_latency_seconds: float | None = None
    filler_density: float = 0.0            # filler occurrences per 100 words
    hedge_density: float = 0.0             # hedges per 100 words
    stutters: list[str] = field(default_factory=list)
    vocabulary_diversity: float = 0.0      # type/token ratio
    avg_word_length: float = 0.0
    structure_marker_count: int = 0

    # Normalized scores (0-10, higher = better)
    fluency: float = 5.0
    hedged: float = 5.0
    speaking_rate: float = 5.0
    response_latency: float = 5.0
    structure: float = 5.0
    vocabulary: float = 5.0
    conciseness: float = 5.0
    clarity: float = 5.0
    overall_score: float = 5.0

    label: str = "Average communicator"
    strengths: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    paralinguistic_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _empty_metrics() -> CommunicationMetrics:
    return CommunicationMetrics(
        label="Insufficient speech to analyze",
        strengths=[],
        concerns=["Answer too short for communication analysis"],
        evidence=["Answer was too brief to compute objective communication metrics."],
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def analyze_communication(
    answer_text: str,
    duration_seconds: float | None = None,
    question_asked_at: float | None = None,
    answered_at: float | None = None,
    paralinguistic_flags: list[str] | None = None,
) -> CommunicationMetrics:
    """
    Analyze a single answer and return objective CommunicationMetrics.

    `duration_seconds` is the recorded speaking duration (voice mode). When
    unavailable, speaking-rate scoring is skipped rather than guessed.
    """
    text = (answer_text or "").strip()
    if not text:
        return _empty_metrics()

    words = _clean_words(text)
    word_count = len(words)
    if word_count < 8:
        return _empty_metrics()

    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    sentence_count = max(1, len(sentences))
    avg_sentence_length = word_count / sentence_count

    # Filler & hedge densities
    filler_count = _count_phrases(text, FILLER_WORDS)
    hedge_count = _count_phrases(text, HEDGE_WORDS)
    filler_density = filler_count * 100.0 / word_count
    hedge_density = hedge_count * 100.0 / word_count

    fluency = _score_inverse(filler_density, max_penalty_at=6.0)
    hedged = _score_inverse(hedge_density, max_penalty_at=8.0)

    # Stutters / self-restarts
    stutters = list(dict.fromkeys(_STUTTER_RE.findall(text)))
    stutters += [m[0] for m in _RESTART_RE.findall(text)]
    stutters = list(dict.fromkeys(stutters))
    if stutters:
        fluency = _clamp(fluency - 1.5)

    # Speaking rate (words per minute)
    speaking_rate_wpm = None
    speaking_rate_score = 5.0
    if duration_seconds and duration_seconds > 1.0:
        speaking_rate_wpm = word_count / (duration_seconds / 60.0)
        # Ideal conversational interview pace ~130-170 wpm.
        speaking_rate_score = _bell(speaking_rate_wpm, 120.0, 175.0, span=80.0)

    # Response latency
    latency_score = 5.0
    latency_seconds = None
    if question_asked_at and answered_at:
        latency_seconds = max(0.0, answered_at - question_asked_at)
        if latency_seconds <= 2.0:
            latency_score = 9.0
        elif latency_seconds <= 5.0:
            latency_score = 7.5
        elif latency_seconds <= 10.0:
            latency_score = 5.5
        else:
            latency_score = _clamp(10.0 - ((latency_seconds - 10.0) / 5.0) * 2.0)

    # Vocabulary diversity (type/token ratio) + word length
    unique = len(set(words))
    vocabulary_diversity = unique / word_count if word_count else 0.0
    avg_word_length = sum(len(w) for w in words) / word_count
    vocab_base = _score_inverse((1.0 - vocabulary_diversity) * 100.0, max_penalty_at=55.0)
    vocabulary = _clamp(vocab_base + (avg_word_length - 4.0) * 1.2)

    # Structure / signposting
    structure_marker_count = _count_phrases(text, STRUCTURE_MARKERS)
    if word_count >= 25:
        structure = _clamp(4.0 + structure_marker_count * 1.5)
    else:
        structure = _clamp(5.0 + structure_marker_count * 1.0)

    # Conciseness — balance brevity against depth. Penalize both very short
    # (thin) and very long (rambling) answers relative to a 25-90 word sweet spot.
    if word_count < 15:
        conciseness = _clamp(10.0 - (15 - word_count) * 0.5)
    elif word_count <= 90:
        conciseness = 10.0
    else:
        conciseness = _clamp(10.0 - ((word_count - 90) / 80.0) * 4.0)

    # Clarity — readable sentence length (moderate = good) combined with structure.
    clarity = _clamp(
        0.55 * _bell(avg_sentence_length, 10.0, 22.0, span=14.0)
        + 0.45 * structure
    )

    # Aggregate (weights reflect what drives recruiter perception)
    overall = (
        fluency * 0.20
        + hedged * 0.15
        + clarity * 0.20
        + conciseness * 0.15
        + vocabulary * 0.10
        + structure * 0.10
        + speaking_rate_score * 0.05
        + latency_score * 0.05
    )
    overall = _clamp(overall)

    metrics = CommunicationMetrics(
        word_count=word_count,
        sentence_count=sentence_count,
        avg_sentence_length=round(avg_sentence_length, 1),
        speaking_rate_wpm=round(speaking_rate_wpm, 1) if speaking_rate_wpm else None,
        response_latency_seconds=round(latency_seconds, 1) if latency_seconds is not None else None,
        filler_density=round(filler_density, 1),
        hedge_density=round(hedge_density, 1),
        stutters=stutters,
        vocabulary_diversity=round(vocabulary_diversity, 3),
        avg_word_length=round(avg_word_length, 2),
        structure_marker_count=structure_marker_count,
        fluency=round(fluency, 1),
        hedged=round(hedged, 1),
        speaking_rate=round(speaking_rate_score, 1),
        response_latency=round(latency_score, 1),
        structure=round(structure, 1),
        vocabulary=round(vocabulary, 1),
        conciseness=round(conciseness, 1),
        clarity=round(clarity, 1),
        overall_score=round(overall, 1),
        label=_label(overall, filler_density, hedge_density),
        paralinguistic_flags=list(paralinguistic_flags or []),
    )

    metrics.strengths = _build_strengths(metrics)
    metrics.concerns = _build_concerns(metrics)
    metrics.evidence = _build_evidence(metrics)

    return metrics


# ── Label + evidence builders ─────────────────────────────────────────────────

def _label(overall: float, filler_density: float, hedge_density: float) -> str:
    if overall >= 8.0:
        base = "Clear, structured communicator"
    elif overall >= 6.5:
        base = "Effective communicator"
    elif overall >= 4.5:
        base = "Adequate communicator"
    else:
        base = "Ineffective communicator"
    if filler_density >= 4.0:
        base += " (heavy filler words)"
    elif hedge_density >= 5.0:
        base += " (frequent hedging)"
    return base


def _build_strengths(m: CommunicationMetrics) -> list[str]:
    strengths: list[str] = []
    if m.fluency >= 8.0:
        strengths.append("Very few filler words or verbal hesitations")
    if m.structure >= 7.0 and m.structure_marker_count >= 1:
        strengths.append("Answers are well-structured with clear signposting")
    if m.vocabulary >= 7.5:
        strengths.append("Strong vocabulary range and lexical precision")
    if m.conciseness >= 8.5:
        strengths.append("Concise and on-point answers")
    if m.response_latency >= 7.5 and m.response_latency_seconds is not None:
        strengths.append("Quick, natural response pace")
    return strengths[:4]


def _build_concerns(m: CommunicationMetrics) -> list[str]:
    concerns: list[str] = []
    if m.filler_density >= 4.0:
        concerns.append(f"Heavy filler-word usage ({m.filler_density:.1f} per 100 words)")
    if m.hedge_density >= 5.0:
        concerns.append(f"Excessive hedging/uncertainty markers ({m.hedge_density:.1f} per 100 words)")
    if m.stutters:
        concerns.append(f"Repeated words / self-interruptions: {', '.join(m.stutters[:3])}")
    if m.speaking_rate is not None and m.speaking_rate_wpm is not None:
        if m.speaking_rate_wpm < 110:
            concerns.append(f"Very slow speaking pace ({m.speaking_rate_wpm:.0f} wpm)")
        elif m.speaking_rate_wpm > 190:
            concerns.append(f"Very fast speaking pace ({m.speaking_rate_wpm:.0f} wpm)")
    if m.response_latency_seconds is not None and m.response_latency_seconds > 8.0:
        concerns.append(f"Long response latency ({m.response_latency_seconds:.0f}s before answering)")
    if m.conciseness < 5.0 and m.word_count > 140:
        concerns.append("Rambling answer — hard to extract the key point")
    return concerns[:4]


def _build_evidence(m: CommunicationMetrics) -> list[str]:
    evidence: list[str] = []
    if m.word_count:
        evidence.append(
            f"{m.word_count} words across {m.sentence_count} sentences "
            f"(avg {m.avg_sentence_length} words/sentence)"
        )
    if m.speaking_rate_wpm is not None:
        evidence.append(f"Speaking rate {m.speaking_rate_wpm:.0f} wpm")
    if m.response_latency_seconds is not None:
        evidence.append(f"Response latency {m.response_latency_seconds:.1f}s")
    if m.filler_density:
        evidence.append(f"Filler density {m.filler_density:.1f}/100 words")
    if m.hedge_density:
        evidence.append(f"Hedging density {m.hedge_density:.1f}/100 words")
    evidence.append(f"Vocabulary diversity {m.vocabulary_diversity:.2f} (type/token ratio)")
    if m.structure_marker_count:
        evidence.append(f"{m.structure_marker_count} structural signposts detected")
    return evidence


def summarize_session(metrics_list: list[CommunicationMetrics]) -> dict:
    """
    Aggregate per-answer metrics into a session-level communication summary.
    Used by the report generator for the Communication Analysis section.
    """
    if not metrics_list:
        return {"analyzed_answers": 0, "avg_overall": 0.0, "best_dimension": None, "worst_dimension": None}

    dims = [
        "fluency", "hedged", "clarity", "conciseness",
        "vocabulary", "structure", "speaking_rate", "response_latency",
    ]
    sums: dict[str, float] = {d: 0.0 for d in dims}
    weights: dict[str, int] = {d: 0 for d in dims}
    all_strengths: list[str] = []
    all_concerns: list[str] = []

    for m in metrics_list:
        for d in dims:
            value = getattr(m, d, None)
            if value is not None:
                sums[d] += value
                weights[d] += 1
        all_strengths.extend(m.strengths)
        all_concerns.extend(m.concerns)

    avgs = {d: (sums[d] / weights[d] if weights[d] else 0.0) for d in dims}

    # Only consider dimensions that were actually measured.
    measured = {d: avgs[d] for d in dims if weights[d]}
    best = max(measured, key=measured.get) if measured else None
    worst = min(measured, key=measured.get) if measured else None

    return {
        "analyzed_answers": len(metrics_list),
        "avg_overall": round(
            sum(m.overall_score for m in metrics_list) / len(metrics_list), 1
        ),
        "dimension_averages": {d: round(v, 1) for d, v in avgs.items()},
        "best_dimension": best,
        "worst_dimension": worst,
        "top_strengths": list(dict.fromkeys(all_strengths))[:5],
        "top_concerns": list(dict.fromkeys(all_concerns))[:5],
    }
