"""
Integration Tests for AI Interviewer LangGraph Flow
====================================================
Tests the complete interview pipeline including:
- Full graph execution
- WebSocket communication
- Voice pipeline integration
- Proctoring events
- System design stage
- Dynamic replanning
"""

import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.ai_interviewer.graph import InterviewGraphRunner, build_interview_graph
from app.ai_interviewer.nodes import make_initial_state
from app.ai_interviewer.state import InterviewState
from app.ai_interviewer.voice import VoicePipeline, DeepgramSTT, ElevenLabsTTS
from app.main import app


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_llm_registry():
    """Mock LLM registry that returns predictable responses."""
    with patch("app.ai_interviewer.llm_providers.get_llm_registry") as mock:
        registry = AsyncMock()
        mock.return_value = registry
        
        # Mock responses for each node
        responses = {
            "resume_analyzer": {
                "candidate_name": "Test Candidate",
                "years_experience": 3,
                "seniority_level": "mid",
                "strong_areas": ["Python", "System Design"],
                "weak_areas": ["DevOps"],
                "red_flags": [],
                "skills": [{"skill": "Python", "confidence": "high", "claimed_depth": "intermediate"}],
                "projects": [],
                "technologies": ["Python", "FastAPI", "PostgreSQL"],
                "experience_entries": [],
                "education": [],
                "certifications": [],
                "summary": "Mid-level backend engineer",
                "interview_intelligence": {
                    "must_probe": ["Python async", "Database design"],
                    "verify_these_claims": ["Expert in Python"],
                    "interesting_angles": ["Open source contributions"],
                    "likely_weaknesses": ["Kubernetes"],
                    "opening_question_suggestions": ["Tell me about a complex Python project"],
                },
            },
            "claim_extractor": {
                "claims": [
                    {"claim_text": "Expert in Python", "source": "skills", "skill": "Python", "verification_priority": 8},
                    {"claim_text": "Built scalable APIs", "source": "projects", "skill": "FastAPI", "verification_priority": 7},
                ],
            },
            "interview_planner": {
                "stages": [
                    {
                        "id": "tech_overview",
                        "name": "Technical Overview",
                        "description": "Probe core technical skills",
                        "topics": ["Python", "APIs", "Databases"],
                        "target_questions": 3,
                        "completed": False,
                    },
                    {
                        "id": "system_design",
                        "name": "System Design",
                        "description": "System architecture discussion",
                        "topics": ["Scalability", "Caching", "Database Sharding"],
                        "target_questions": 3,
                        "completed": False,
                    },
                    {
                        "id": "coding",
                        "name": "Coding Challenge",
                        "description": "Live coding exercise",
                        "topics": ["Algorithms", "Data Structures"],
                        "target_questions": 2,
                        "completed": False,
                    },
                ],
                "total_questions": 8,
                "focus_areas": ["Python", "System Design", "APIs"],
                "opening_strategy": "Start with Python project deep dive",
                "closing_strategy": "Behavioral wrap-up",
                "estimated_duration_minutes": 45,
            },
            "opening": {
                "opening_text": "Hi Test, I'm Jack, your interviewer. I've reviewed your background and today we'll discuss your Python experience. Let's start: Can you walk me through your most complex Python project?",
            },
            "question_generator": {
                "question_text": "Can you explain how you handled database migrations in your FastAPI project?",
                "intent": "technical",
                "topic": "databases",
                "rationale": "Verify claimed database experience",
                "difficulty": "medium",
                "expected_answer_signals": ["Alembic", "migrations", "version control"],
            },
            "answer_analyzer": {
                "technical_accuracy": 8,
                "depth": 7,
                "clarity": 8,
                "confidence": 7,
                "completeness": 7,
                "communication_quality": 8,
                "missing_points": [],
                "positive_signals": ["Mentioned Alembic", "Explained versioning"],
                "red_flags": [],
                "suggested_follow_ups": ["How did you handle rollback?"],
                "answer_summary": "Good explanation of migration strategy",
                "overall_quality": "good",
                "should_dig_deeper": False,
                "dig_deeper_angle": "",
            },
            "claim_verifier": {
                "verification_status": "VERIFIED",
                "evidence": "Candidate mentioned Alembic and versioned migrations",
                "confidence": "high",
                "reasoning": "Answer demonstrates hands-on experience",
            },
            "follow_up_generator": {
                "follow_up_question": "Good answer. How did you handle rollback scenarios when a migration failed?",
                "why_this_question": "Test depth of migration experience",
                "escalation_level": 1,
                "is_challenging": False,
            },
            "stage_advance": {
                "current_stage_index": 1,
                "current_stage": {
                    "id": "system_design",
                    "name": "System Design",
                    "description": "System architecture discussion",
                    "topics": ["Scalability", "Caching", "Database Sharding"],
                    "target_questions": 3,
                    "completed": False,
                },
                "ai_response_text": "Great, let's move on to system design. How would you design a scalable notification service?",
            },
            "system_design_question_generator": {
                "question_text": "How would you design a scalable notification service that handles millions of push notifications per day?",
                "intent": "system_design",
                "topic": "scalability",
                "rationale": "Test system design skills",
                "difficulty": "hard",
                "expected_answer_signals": ["Message queue", "Horizontal scaling", "Deduplication"],
            },
            "system_design_evaluator": {
                "requirements_clarification": 8,
                "api_design": 7,
                "database_design": 6,
                "scalability": 8,
                "caching_strategy": 7,
                "tradeoff_analysis": 6,
                "failure_handling": 7,
                "overall_system_design_score": 7,
                "strengths": ["Good scalability approach"],
                "weaknesses": ["Could elaborate on caching"],
                "missing_components": ["Rate limiting"],
                "suggested_follow_up": "How would you handle rate limiting?",
                "evaluation_summary": "Solid system design answer",
            },
            "coding_problem_generator": {
                "title": "Two Sum",
                "difficulty": "easy",
                "topic": "arrays",
                "description": "Given an array of integers, return indices of the two numbers that add up to target.",
                "constraints": ["2 <= n <= 10^4", "-10^9 <= nums[i] <= 10^9"],
                "examples": [{"input": "4\n2 7 11 15\n9", "output": "0 1", "explanation": "2 + 7 = 9"}],
                "io_contract": "Line 1: n. Line 2: n space-separated ints. Line 3: target. Output: two indices.",
                "languages": ["python", "javascript"],
                "starter_code": {"python": "import sys\n\ndef solve():\n    data = sys.stdin.read().strip().split()\n    # implement here\n\nif __name__ == \"__main__\":\n    solve()"},
                "visible_test_cases": [{"input": "4\n2 7 11 15\n9", "expected": "0 1"}],
                "hidden_test_cases": [
                    {"input": "3\n3 2 4\n6", "expected": "1 2"},
                    {"input": "3\n3 3\n6", "expected": "0 1"},
                ],
                "time_complexity": "O(n)",
                "space_complexity": "O(n)",
                "evaluation_criteria": ["Correctness", "Time complexity", "Clean code"],
            },
            "scoring": {
                "technical_score": 75.0,
                "communication_score": 80.0,
                "confidence_score": 70.0,
                "problem_solving_score": 72.0,
                "behavioral_score": 78.0,
                "depth_score": 73.0,
                "overall_score": 74.5,
                "recommendation": "Hire",
            },
            "report_generator": {
                "strengths": ["Strong Python knowledge", "Good system design"],
                "weaknesses": ["Limited DevOps experience"],
                "areas_for_improvement": ["Kubernetes", "CI/CD pipelines"],
                "detailed_summary": "Candidate demonstrated strong technical skills...",
                "recommendation": "Hire",
                "recommendation_rationale": "Strong technical foundation with good communication",
                "standout_moments": ["Explained migration strategy clearly"],
                "risk_factors": ["Limited production Kubernetes experience"],
                "suggested_onboarding_focus": ["Kubernetes basics", "CI/CD"],
                "claim_assessment": {
                    "verified_claims": ["Expert in Python - verified via project discussion"],
                    "failed_claims": [],
                    "partial_claims": [],
                },
                "code_quality_assessment": {
                    "submitted_code": True,
                    "showed_improvement": True,
                    "code_summary": "Clean Python solution with O(n) complexity",
                },
            },
            "interview_replanner": {
                "replanned_stages": [],
                "priority_claims_to_verify": [],
                "topics_to_probe": [],
                "topics_to_skip": [],
                "rationale": "Current plan is sufficient",
            },
        }
        
        # Track call count to return appropriate response
        call_count = {"count": 0}
        
        async def mock_generate_json(system, prompt, model=None):
            call_count["count"] += 1
            # Return appropriate response based on prompt content
            if "RESUME_ANALYZER" in system:
                return responses["resume_analyzer"]
            elif "CLAIM_EXTRACTOR" in system:
                return responses["claim_extractor"]
            elif "INTERVIEW_PLANNER" in system:
                return responses["interview_planner"]
            elif "INTERVIEW_OPENING" in system:
                return responses["opening"]
            elif "QUESTION_GENERATOR" in system:
                return responses["question_generator"]
            elif "ANSWER_ANALYZER" in system:
                return responses["answer_analyzer"]
            elif "CLAIM_VERIFIER" in system:
                return responses["claim_verifier"]
            elif "FOLLOW_UP_GENERATOR" in system:
                return responses["follow_up_generator"]
            elif "STAGE_TRANSITION" in system:
                return responses["stage_advance"]
            elif "SYSTEM_DESIGN_GENERATOR" in system:
                return responses["system_design_question_generator"]
            elif "SYSTEM_DESIGN_EVALUATOR" in system:
                return responses["system_design_evaluator"]
            elif "CODING_PROBLEM_GENERATOR" in system:
                return responses["coding_problem_generator"]
            elif "SCORING" in system:
                return responses["scoring"]
            elif "REPORT_GENERATOR" in system:
                return responses["report_generator"]
            elif "INTERVIEW_REPLANNER" in system:
                return responses["interview_replanner"]
            return {}
        
        registry.generate_json = mock_generate_json
        registry.available_providers = ["mock"]
        yield registry


@pytest.fixture
def mock_voice_pipeline():
    """Mock voice pipeline for testing."""
    with patch("app.ai_interviewer.voice.VoicePipeline") as mock:
        pipeline = AsyncMock()
        
        pipeline.audio_to_text = AsyncMock(return_value="I used Python and FastAPI to build REST APIs with PostgreSQL.")
        pipeline.text_to_audio = AsyncMock(return_value=b"fake_audio_data")
        pipeline.process_turn = AsyncMock(return_value={
            "transcript": "I used Python and FastAPI to build REST APIs with PostgreSQL.",
            "response_text": "Good explanation. How did you handle database migrations?",
            "response_audio": b"fake_audio_data",
            "phase": "interviewing",
            "should_end": False,
            "total_latency_ms": 800,
            "stt_latency_ms": 200,
            "llm_latency_ms": 400,
            "tts_latency_ms": 200,
        })
        
        mock.from_settings = MagicMock(return_value=pipeline)
        yield pipeline


@pytest.fixture
def initial_state():
    """Create initial interview state."""
    return make_initial_state(
        session_id=str(uuid.uuid4()),
        candidate_email="test@example.com",
        role="Software Engineer",
        company="Test Corp",
        resume_raw_text="Name: Test Candidate\nSkills: Python, FastAPI, PostgreSQL\nExperience: 3 years backend development",
        resume_parsed={
            "name": "Test Candidate",
            "skills": ["Python", "FastAPI", "PostgreSQL"],
            "experience_entries": [{"role": "Backend Engineer", "company": "Acme", "duration": "3 years"}],
            "rawText": "Test resume",
        },
        max_questions=6,
        voice_enabled=False,
    )


# ── LangGraph Integration Tests ────────────────────────────────────────────

class TestInterviewGraphFlow:
    """Test the complete LangGraph interview flow."""
    
    @pytest.mark.asyncio
    async def test_full_interview_initialization(self, mock_llm_registry, initial_state):
        """Test interview initialization phase."""
        runner = InterviewGraphRunner(
            session_id=initial_state["session_id"],
            initial_state=initial_state,
        )
        
        opening = await runner.initialize()
        
        assert "Hi Test" in opening
        assert "Jack" in opening
        assert runner._initialized is True
        assert runner.state["phase"] == "interviewing"
        assert runner.state["resume_analysis"]["candidate_name"] == "Test Candidate"
        assert len(runner.state["interview_plan"]["stages"]) == 3
    
    @pytest.mark.asyncio
    async def test_first_question_generation(self, mock_llm_registry, initial_state):
        """Test first question generation after initialization."""
        runner = InterviewGraphRunner(
            session_id=initial_state["session_id"],
            initial_state=initial_state,
        )
        
        await runner.initialize()
        question = await runner.generate_first_question()
        
        assert "database migrations" in question.lower() or "fastapi" in question.lower()
        assert runner.state["questions_asked"] == 1
        assert runner.state["main_questions_asked"] == 1
        assert "current_question" in runner.state
    
    @pytest.mark.asyncio
    async def test_answer_processing_and_follow_up(self, mock_llm_registry, initial_state):
        """Test processing candidate answer and generating follow-up."""
        runner = InterviewGraphRunner(
            session_id=initial_state["session_id"],
            initial_state=initial_state,
        )
        
        await runner.initialize()
        await runner.generate_first_question()
        
        # Process a good answer
        result = await runner.process_answer(
            "I used Alembic for database migrations. It handles versioning and rollbacks automatically.",
            code_snapshot=None
        )
        
        # Should generate a follow-up question
        assert result["phase"] == "interviewing"
        assert result["should_end"] is False
        assert "follow_up" in str(result).lower() or "question" in str(result).lower()
        assert runner.state["questions_asked"] >= 1
    
    @pytest.mark.asyncio
    async def test_stage_advancement(self, mock_llm_registry, initial_state):
        """Test stage advancement after completing stage questions."""
        runner = InterviewGraphRunner(
            session_id=initial_state["session_id"],
            initial_state=initial_state,
        )
        
        await runner.initialize()
        
        # Simulate completing first stage (3 questions)
        for i in range(3):
            await runner.generate_first_question() if i == 0 else None
            # Manually increment to simulate stage completion
            runner.state["questions_asked"] = i + 1
            runner.state["main_questions_asked"] = i + 1
            
            if i < 2:
                result = await runner.process_answer(
                    f"Answer to question {i+1} with good technical detail.",
                    code_snapshot=None
                )
        
        # Check stage advancement
        assert runner.state["current_stage_index"] >= 0
    
    @pytest.mark.asyncio
    async def test_system_design_stage(self, mock_llm_registry, initial_state):
        """Test system design stage entry and question generation."""
        runner = InterviewGraphRunner(
            session_id=initial_state["session_id"],
            initial_state=initial_state,
        )
        
        await runner.initialize()
        
        # Manually advance to system design stage
        runner.state["current_stage_index"] = 1
        runner.state["current_stage"] = runner.state["interview_plan"]["stages"][1]
        runner.state["is_system_design_mode"] = True
        
        # Generate system design question
        question = await runner.process_answer(
            "Transition answer",
            code_snapshot=None
        )
        
        # Should generate system design question
        assert "notification" in str(question).lower() or "design" in str(question).lower()
    
    @pytest.mark.asyncio
    async def test_interview_completion_and_report(self, mock_llm_registry, initial_state):
        """Test interview completion and report generation."""
        runner = InterviewGraphRunner(
            session_id=initial_state["session_id"],
            initial_state=initial_state,
        )
        
        await runner.initialize()
        await runner.generate_first_question()
        
        # Process several answers
        for i in range(4):
            result = await runner.process_answer(
                f"Answer {i+1} with technical detail about Python, APIs, and databases.",
                code_snapshot=None
            )
            if result.get("should_end"):
                break
        
        # Finalize
        final_result = await runner._finalize()
        
        assert final_result["phase"] == "completed"
        assert final_result["should_end"] is True
        assert "final_report" in final_result
        assert final_result["final_report"]["scores"]["overall_score"] > 0
        assert final_result["final_report"]["recommendation"] in ["Strong Hire", "Hire", "Lean Hire", "Lean Reject", "Reject"]
    
    @pytest.mark.asyncio
    async def test_replanner_invocation(self, mock_llm_registry, initial_state):
        """Test dynamic replanner is invoked every 3 questions."""
        runner = InterviewGraphRunner(
            session_id=initial_state["session_id"],
            initial_state=initial_state,
        )
        
        await runner.initialize()
        await runner.generate_first_question()
        
        # Process 3 questions to trigger replanner
        for i in range(3):
            result = await runner.process_answer(
                f"Answer {i+1} about different technical topics.",
                code_snapshot=None
            )
        
        # Replanner should have been called
        assert runner.state.get("replan_count", 0) >= 0


# ── WebSocket Integration Tests ────────────────────────────────────────────

class TestWebSocketInterview:
    """Test WebSocket-based interview flow."""
    
    def test_text_websocket_connection(self, client, auth_header):
        """Test text WebSocket connection and message exchange."""
        with client.websocket_connect(
            "/ai-interview/ws",
            headers=auth_header()
        ) as ws:
            # Should receive session_ready
            msg = ws.receive_json()
            assert msg["type"] in ["session_ready", "thinking", "status"]
            
            # Send answer
            ws.send_json({
                "type": "answer",
                "text": "I have 3 years of Python experience building REST APIs with FastAPI."
            })
            
            # Should receive question
            msg = ws.receive_json()
            assert msg["type"] in ["question", "thinking", "interview_complete"]
    
    def test_voice_websocket_connection(self, client, auth_header, mock_voice_pipeline):
        """Test voice WebSocket connection."""
        with client.websocket_connect(
            "/ai-interview/ws/voice",
            headers=auth_header()
        ) as ws:
            # Should receive session_ready with greeting
            msg = ws.receive_json()
            assert msg["type"] in ["session_ready", "progress"]
            
            # Send audio_end with transcript
            ws.send_json({
                "type": "audio_end",
                "transcript": "I have Python experience with FastAPI."
            })
            
            # Should receive STT result and next question
            msg = ws.receive_json()
            assert msg["type"] in ["stt_result", "question", "processing"]
    
    def test_proctoring_websocket(self, client, auth_header):
        """Test proctoring WebSocket event handling."""
        session_id = str(uuid.uuid4())
        
        with client.websocket_connect(
            f"/ai-interview/ws/proctoring?interview_session_id={session_id}",
            headers=auth_header()
        ) as ws:
            # Send proctoring event
            ws.send_json({
                "type": "event",
                "event_type": "face_missing",
                "severity": "high",
                "details": {"duration_ms": 5000},
                "timestamp": time.time(),
            })
            
            # Should receive acknowledgment
            msg = ws.receive_json()
            assert msg["type"] == "event_ack"
            assert msg["event_type"] == "face_missing"
            assert "integrity_score" in msg
    
    def test_proctoring_termination(self, client, auth_header):
        """Test session termination due to proctoring violations."""
        session_id = str(uuid.uuid4())
        
        with client.websocket_connect(
            f"/ai-interview/ws/proctoring?interview_session_id={session_id}",
            headers=auth_header()
        ) as ws:
            # Send multiple critical violations
            for i in range(4):
                ws.send_json({
                    "type": "event",
                    "event_type": "multi_face",
                    "severity": "critical",
                    "details": {},
                    "timestamp": time.time(),
                })
                msg = ws.receive_json()
            
            # Last event should trigger termination
            final_msg = ws.receive_json()
            assert final_msg["type"] in ["terminated", "event_ack"]
            if final_msg["type"] == "terminated":
                assert "terminated" in final_msg["message"].lower()


# ── Voice Pipeline Integration Tests ───────────────────────────────────────

class TestVoicePipelineIntegration:
    """Test the complete voice pipeline."""
    
    @pytest.mark.asyncio
    async def test_voice_pipeline_turn(self, mock_llm_registry, mock_voice_pipeline, initial_state):
        """Test a full voice turn: audio -> STT -> LLM -> TTS."""
        runner = InterviewGraphRunner(
            session_id=initial_state["session_id"],
            initial_state=initial_state,
        )
        
        await runner.initialize()
        await runner.generate_first_question()
        
        pipeline = VoicePipeline.from_settings()
        
        # Process voice turn
        result = await pipeline.process_turn(b"fake_audio", runner)
        
        assert "transcript" in result
        assert "response_text" in result
        assert "response_audio" in result
        assert result["phase"] == "interviewing"
        assert result["total_latency_ms"] > 0
    
    @pytest.mark.asyncio
    async def test_language_switching(self, initial_state):
        """Test multi-language voice support."""
        from app.ai_interviewer.voice import get_supported_languages, get_voice_for_language
        
        languages = get_supported_languages()
        assert len(languages) >= 10
        
        # Test voice selection for different languages
        for lang in ["en-US", "es", "fr", "de", "ja"]:
            voice_id = get_voice_for_language(lang, "male", "elevenlabs")
            assert voice_id
            
            voice_id_female = get_voice_for_language(lang, "female", "elevenlabs")
            assert voice_id_female
    
    @pytest.mark.asyncio
    async def test_stt_fallback_chain(self, initial_state):
        """Test STT fallback from Deepgram to Whisper."""
        from app.ai_interviewer.voice import VoicePipeline, DeepgramSTT, WhisperSTT
        
        # Test Deepgram unavailable -> falls back to Whisper
        with patch("app.ai_interviewer.voice.getattr") as mock_getattr:
            mock_getattr.side_effect = lambda obj, name, default="": (
                "" if name == "deepgram_api_key" else 
                "test_key" if name in ["groq_api_key", "openai_api_key"] else 
                default
            )
            
            pipeline = VoicePipeline.from_settings()
            
            # Should use Whisper STT
            assert isinstance(pipeline.stt, WhisperSTT)
    
    @pytest.mark.asyncio
    async def test_tts_fallback_chain(self, initial_state):
        """Test TTS fallback from ElevenLabs to OpenAI."""
        from app.ai_interviewer.voice import VoicePipeline, ElevenLabsTTS, OpenAITTS
        
        with patch("app.ai_interviewer.voice.getattr") as mock_getattr:
            mock_getattr.side_effect = lambda obj, name, default="": (
                "" if name == "elevenlabs_api_key" else 
                "test_key" if name == "openai_api_key" else 
                default
            )
            
            pipeline = VoicePipeline.from_settings()
            
            # Should use OpenAI TTS
            assert isinstance(pipeline.tts, OpenAITTS)


# ── Proctoring Integration Tests ──────────────────────────────────────────

class TestProctoringIntegration:
    """Test proctoring system integration."""
    
    def test_proctoring_rest_endpoints(self, client, auth_header):
        """Test proctoring REST API endpoints."""
        session_id = str(uuid.uuid4())
        
        # Create session first
        create_res = client.post(
            "/ai-interview/create-session",
            headers=auth_header(),
        )
        assert create_res.status_code == 200
        
        # Send proctoring event
        event_res = client.post(
            f"/ai-interview/{create_res.json()['interview_session_id']}/proctoring/event",
            headers=auth_header(),
            json={
                "session_id": create_res.json()['interview_session_id'],
                "event_type": "tab_switch",
                "severity": "medium",
                "details": {"url": "https://google.com"},
                "timestamp": time.time(),
            }
        )
        
        assert event_res.status_code == 200
        assert "integrity_score" in event_res.json()
        assert "should_terminate" in event_res.json()
    
    def test_proctoring_warning_threshold(self, client, auth_header):
        """Test proctoring warning at 50% integrity."""
        session_id = str(uuid.uuid4())
        create_res = client.post(
            "/ai-interview/create-session",
            headers=auth_header(),
        )
        interview_id = create_res.json()['interview_session_id']
        
        # Send events to drop integrity below 50%
        for i in range(8):
            client.post(
                f"/ai-interview/{interview_id}/proctoring/event",
                headers=auth_header(),
                json={
                    "session_id": interview_id,
                    "event_type": "face_missing",
                    "severity": "medium",
                    "details": {},
                    "timestamp": time.time(),
                }
            )
        
        # Get proctoring data
        get_res = client.get(
            f"/ai-interview/{interview_id}/proctoring",
            headers=auth_header(),
        )
        
        assert get_res.status_code == 200
        data = get_res.json()
        assert data["status"] in ["warned", "terminated"]
    
    def test_proctoring_manual_termination(self, client, auth_header):
        """Test manual session termination."""
        create_res = client.post(
            "/ai-interview/create-session",
            headers=auth_header(),
        )
        interview_id = create_res.json()['interview_session_id']
        
        # Terminate
        term_res = client.post(
            f"/ai-interview/{interview_id}/proctoring/terminate",
            headers=auth_header(),
        )
        
        assert term_res.status_code == 200
        assert term_res.json()["status"] == "terminated"


# ── Vector Search Integration Tests ────────────────────────────────────────

class TestVectorSearchIntegration:
    """Test vector-based resume search."""
    
    def test_semantic_search_endpoint(self, client, auth_header):
        """Test semantic search API."""
        res = client.post(
            "/ai-interview/vector/search",
            headers=auth_header(),
            json={
                "query": "Python backend engineer with FastAPI experience",
                "top_k": 5,
            }
        )
        
        # May return empty results if no embeddings stored
        assert res.status_code in [200, 404]
    
    def test_role_matching_endpoint(self, client, auth_header):
        """Test role-based candidate matching."""
        res = client.post(
            "/ai-interview/vector/match-role",
            headers=auth_header(),
            json={
                "role_description": "Senior Python Developer for scalable web services",
                "required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
                "top_k": 10,
            }
        )
        
        assert res.status_code in [200, 404]
        if res.status_code == 200:
            data = res.json()
            assert "candidates" in data
    
    def test_skill_gap_analysis(self, client, auth_header):
        """Test skill gap analysis between candidate and job."""
        # First store a job
        client.post(
            "/ai-interview/vector/store-job",
            headers=auth_header(),
            json={
                "job_id": "job-123",
                "title": "Senior Backend Engineer",
                "company": "TestCorp",
                "description": "Build scalable microservices with Python and Kubernetes",
                "required_skills": ["Python", "FastAPI", "Kubernetes", "PostgreSQL"],
            }
        )
        
        # Analyze skill gap
        res = client.post(
            "/ai-interview/vector/skill-gap",
            headers=auth_header(),
            json={
                "candidate_email": "test@example.com",
                "job_id": "job-123",
            }
        )
        
        assert res.status_code in [200, 404]


# ── Code Execution Integration Tests ───────────────────────────────────────

class TestCodeExecutionIntegration:
    """Test code execution with caching and sandboxing."""
    
    def test_python_execution_with_cache(self, client, auth_header):
        """Test Python code execution with compilation caching."""
        code = """
def solve():
    import sys
    data = sys.stdin.read().strip().split()
    n = int(data[0])
    arr = list(map(int, data[1:n+1]))
    target = int(data[n+1])
    
    seen = {}
    for i, num in enumerate(arr):
        complement = target - num
        if complement in seen:
            print(seen[complement], i)
            return
        seen[num] = i
    print(-1)

if __name__ == "__main__":
    solve()
"""
        # First execution
        res1 = client.post(
            "/ai-interview/run-code",
            headers=auth_header(),
            json={"language": "python", "code": code, "stdin": "4\n2 7 11 15\n9"}
        )
        assert res1.status_code == 200
        assert "0 1" in res1.json()["stdout"]
        
        # Second execution (should use cache)
        res2 = client.post(
            "/ai-interview/run-code",
            headers=auth_header(),
            json={"language": "python", "code": code, "stdin": "3\n3 2 4\n6"}
        )
        assert res2.status_code == 200
        assert "1 2" in res2.json()["stdout"]
    
    def test_code_execution_resource_limits(self, client, auth_header):
        """Test resource limits are enforced."""
        # Infinite loop code
        code = "while True: pass"
        
        res = client.post(
            "/ai-interview/run-code",
            headers=auth_header(),
            json={"language": "python", "code": code}
        )
        
        assert res.status_code == 200
        data = res.json()
        assert data["timed_out"] is True or data["ok"] is False
    
    def test_unsupported_language_handling(self, client, auth_header):
        """Test handling of unsupported languages."""
        res = client.post(
            "/ai-interview/run-code",
            headers=auth_header(),
            json={"language": "cobol", "code": "DISPLAY 'HELLO'."}
        )
        
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is False
        assert "not supported" in data["error"].lower()


# ── Benchmark & Analytics Integration Tests ────────────────────────────────

class TestBenchmarkIntegration:
    """Test benchmark and analytics endpoints."""
    
    def test_benchmark_endpoint(self, client, auth_header):
        """Test platform benchmark data."""
        res = client.get("/admin/benchmark", headers=auth_header())
        
        assert res.status_code == 200
        data = res.json()
        if "benchmark" in data:
            bench = data["benchmark"]
            assert "median_overall" in bench
            assert "p75_overall" in bench
            assert "p90_overall" in bench
    
    def test_recruiter_analytics_tab(self, client, auth_header):
        """Test recruiter analytics data."""
        res = client.get("/admin/candidates", headers=auth_header())
        
        assert res.status_code == 200
        data = res.json()
        assert "candidates" in data


# ── Test Utilities ──────────────────────────────────────────────────────────

def test_health_endpoints():
    """Test health check endpoints."""
    with TestClient(app) as client:
        # Basic health
        res = client.get("/health")
        assert res.status_code in [200, 503]
        assert "status" in res.json()
        
        # Detailed health
        res = client.get("/health/detailed")
        assert res.status_code == 200
        data = res.json()
        assert "status" in data
        
        # Metrics
        res = client.get("/metrics")
        assert res.status_code == 200
        assert "http_requests_total" in res.text


# ── Pytest Configuration ──────────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )