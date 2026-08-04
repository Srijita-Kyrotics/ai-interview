"""Tests for the objective communication analyzer (no API keys required)."""
from app.ai_interviewer.communication_analyzer import (
    analyze_communication,
    summarize_session,
)


class TestBasicMetrics:
    def test_empty_answer(self):
        m = analyze_communication("")
        assert m.word_count == 0
        assert m.label == "Insufficient speech to analyze"
        assert m.overall_score == 5.0

    def test_very_short_answer(self):
        m = analyze_communication("Yes, I did that.")
        assert m.word_count < 8
        assert m.label == "Insufficient speech to analyze"

    def test_word_count_and_sentences(self):
        text = "First, I built a microservice. Then, I added caching. Finally, I tested it."
        m = analyze_communication(text)
        assert m.word_count == 13
        assert m.sentence_count == 3

    def test_all_scores_within_range(self):
        m = analyze_communication(
            "I designed a system that handled a thousand requests per second. "
            "We used a load balancer and a distributed cache. "
            "The tradeoff was consistency versus availability, so we chose eventual consistency. "
            "In practice, we monitored the error rate closely and added circuit breakers.",
        )
        for attr in ("fluency", "hedged", "clarity", "conciseness", "vocabulary",
                     "structure", "overall_score"):
            assert 0.0 <= getattr(m, attr) <= 10.0


class TestFillerAndHedgeDetection:
    def test_fillers_lower_fluency(self):
        clean = analyze_communication(
            "The system processed requests with a queue and we scaled horizontally "
            "when demand increased during peak hours and the database handled it well."
        )
        filled = analyze_communication(
            "Um, you know, like, we basically used, like, a queue, you know, "
            "and sort of scaled horizontally, um, and I mean it worked fine, like, really."
        )
        assert filled.filler_density > clean.filler_density
        assert filled.fluency < clean.fluency
        assert "Heavy filler-word usage" in " ".join(filled.concerns)

    def test_hedges_lower_hedged_score(self):
        hedgy = analyze_communication(
            "I think we maybe used Kubernetes, I'm not sure. It probably would "
            "scale, I guess. Perhaps we could have done it better, I believe."
        )
        assert hedgy.hedge_density > 3.0
        assert "Excessive hedging" in " ".join(hedgy.concerns)


class TestProsodySignals:
    def test_speaking_rate_scoring(self):
        slow = analyze_communication(
            "We used a relational database with indexes and connection pooling.",
            duration_seconds=20.0,
        )
        fast = analyze_communication(
            "We used a relational database with indexes and connection pooling.",
            duration_seconds=2.0,
        )
        assert slow.speaking_rate_wpm is not None
        assert slow.speaking_rate_wpm < fast.speaking_rate_wpm
        # 9 words in 2 seconds = 270 wpm (too fast), 9 words in 20s = 27 wpm (too slow)
        assert slow.speaking_rate < 5.0
        assert fast.speaking_rate < 5.0

    def test_latency_scoring(self):
        quick = analyze_communication(
            "We used a queue with a worker pool and dead letter handling.",
            question_asked_at=100.0,
            answered_at=101.0,
        )
        slow = analyze_communication(
            "We used a queue with a worker pool and dead letter handling.",
            question_asked_at=100.0,
            answered_at=125.0,
        )
        assert quick.response_latency > slow.response_latency
        assert "Long response latency" in " ".join(slow.concerns)


class TestStructureAndClarity:
    def test_structure_markers_boost(self):
        unstructured = analyze_communication(
            "We made an API. It worked. We shipped it. Users were happy."
        )
        structured = analyze_communication(
            "First, we designed the API contract. Secondly, we implemented it "
            "behind a load balancer. Finally, we monitored latency in production "
            "and added caching to reduce p95 response times."
        )
        assert structured.structure_marker_count > 0
        assert structured.structure > unstructured.structure

    def test_stutter_detection(self):
        m = analyze_communication(
            "The the system was designed to to handle high throughput and the "
            "database was normalized to third normal form before we shipped it."
        )
        assert any("Repeated words" in c for c in m.concerns) or len(m.stutters) > 0


class TestSummarizeSession:
    def test_empty_list(self):
        summary = summarize_session([])
        assert summary["analyzed_answers"] == 0

    def test_aggregation(self):
        texts = [
            "First, I designed the schema. Then I added an index. Finally I tested it.",
            "We used redis for caching and the performance improved significantly. "
            "The tradeoff was memory usage versus latency reduction.",
            "The system was a microservice with a message queue and a worker pool.",
        ]
        metrics = [analyze_communication(t) for t in texts]
        summary = summarize_session(metrics)
        assert summary["analyzed_answers"] == 3
        assert 0.0 <= summary["avg_overall"] <= 10.0
        assert summary["best_dimension"] is not None
        assert summary["worst_dimension"] is not None
        assert len(summary["top_strengths"]) <= 5
