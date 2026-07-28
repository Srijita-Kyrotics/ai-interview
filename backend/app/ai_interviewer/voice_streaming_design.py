"""
Streaming Voice Pipeline — Architecture Design
================================================
PURPOSE: Design document only. No implementation.
DESIGN PHASE: Architecture + migration plan for batch → streaming STT.

Current State:
  Hold-to-Talk → Full Audio Blob → Batch STT → LLM → TTS → Play

Target State:
  Continuous Streaming → Partial Transcripts → Incremental LLM Reasoning → Streaming TTS
"""

# ══════════════════════════════════════════════════════════════════════════════
# ARCHITECTURE: Streaming Voice Pipeline
# ══════════════════════════════════════════════════════════════════════════════
#
# ┌──────────────────────────────────────────────────────────────────────────┐
# │                    CURRENT: Batch Pipeline                              │
# │                                                                        │
# │  Candidate speaks                                                      │
# │      │                                                                 │
# │      ▼ (hold-to-talk)                                                  │
# │  MediaRecorder captures full audio                                     │
# │      │                                                                 │
# │      ▼ (release button)                                                │
# │  Send complete audio blob via WebSocket                                │
# │      │                                                                 │
# │      ▼                                                                 │
# │  Batch STT (Deepgram REST) ─── ~300-500ms                             │
# │      │                                                                 │
# │      ▼                                                                 │
# │  Full transcript → LLM processing ─── ~500-1500ms                     │
# │      │                                                                 │
# │      ▼                                                                 │
# │  TTS synthesis ─── ~300-500ms                                          │
# │      │                                                                 │
# │      ▼                                                                 │
# │  Play audio to candidate                                               │
# │                                                                        │
# │  Total latency: 1100-2500ms (after button release)                     │
# └──────────────────────────────────────────────────────────────────────────┘
#
# ┌──────────────────────────────────────────────────────────────────────────┐
# │                    TARGET: Streaming Pipeline                           │
# │                                                                        │
# │  Candidate speaks                                                      │
# │      │                                                                 │
# │      ▼ (continuous)                                                    │
# │  WebSocket streams audio chunks ─── 100ms intervals                    │
# │      │                                                                 │
# │      ▼                                                                 │
# │  Streaming STT (Deepgram WS) ─── partial transcripts                  │
# │      │                                                                 │
# │      ├──▶ Live transcript preview (shows as candidate speaks)          │
# │      │                                                                 │
# │      ▼ (speech ended / VAD silence detection)                         │
# │  Final transcript (high confidence)                                    │
# │      │                                                                 │
# │      ├──▶ Incremental LLM reasoning (start on partial transcript)      │
# │      │                                                                 │
# │      ▼                                                                 │
# │  Full answer processing → evaluation                                   │
# │      │                                                                 │
# │      ▼                                                                 │
# │  Streaming TTS (chunked playback)                                      │
# │      │                                                                 │
# │      ▼                                                                 │
# │  Candidate hears response                                              │
# │                                                                        │
# │  Perceived latency: ~500ms (overlaps with speech)                      │
# │  Actual latency: ~800ms (after speech ends)                            │
# └──────────────────────────────────────────────────────────────────────────┘


# ══════════════════════════════════════════════════════════════════════════════
# COMPONENT DESIGN
# ══════════════════════════════════════════════════════════════════════════════

STREAMING_ARCHITECTURE = {
    "components": [
        {
            "name": "AudioChunker",
            "responsibility": "Captures microphone audio and sends 100ms chunks via WebSocket",
            "implementation": "MediaRecorder with timeslice=100ms, sends binary chunks",
            "protocol": "WS binary frames → backend",
        },
        {
            "name": "StreamingSTT",
            "responsibility": "Converts audio stream to partial + final transcripts",
            "implementation": "Deepgram Nova-3 WebSocket API (real-time streaming)",
            "fallback": "Whisper API (batch mode, triggered on silence)",
            "outputs": [
                {"type": "partial", "description": "Interim transcript, updated every 100ms"},
                {"type": "final", "description": "High-confidence transcript after VAD silence"},
            ],
        },
        {
            "name": "VoiceActivityDetector",
            "responsibility": "Detects start/end of speech from audio energy",
            "implementation": "Deepgram VAD (built into streaming API) + custom silence threshold",
            "config": {
                "silence_timeout_ms": 1500,
                "min_speech_ms": 500,
                "max_speech_ms": 30000,
            },
        },
        {
            "name": "IncrementalLLM",
            "responsibility": "Starts reasoning on partial transcripts for lower latency",
            "implementation": "Prefetch question context, pre-build prompt template on speech start",
            "optimization": "Prepare system prompt + context while candidate is still speaking",
        },
        {
            "name": "StreamingTTS",
            "responsibility": "Synthesize and play audio in chunks for lower perceived latency",
            "implementation": "ElevenLabs chunked TTS or OpenAI TTS stream API",
            "playback": "Queue of AudioBufferSourceNodes, played sequentially",
        },
        {
            "name": "InterviewAgent",
            "responsibility": "Same LangGraph runner, but called with final transcript",
            "change": "Minimal — receives text as before, just called sooner",
        },
    ],

    "websocket_protocol": {
        "client_to_server": [
            {"type": "audio_chunk", "data": "binary (100ms WebM/opus frame)"},
            {"type": "speech_end", "description": "Client-detected silence or button release"},
            {"type": "audio_end", "description": "Legacy: full blob mode for backward compat"},
        ],
        "server_to_client": [
            {"type": "partial_transcript", "text": "interim text as candidate speaks"},
            {"type": "final_transcript", "text": "high-confidence transcript"},
            {"type": "ai_response_text", "text": "response text before audio"},
            {"type": "tts_chunk", "data": "binary audio chunk for streaming playback"},
            {"type": "tts_complete", "description": "All audio chunks sent"},
        ],
    },

    "migration_plan": {
        "phase_1": {
            "name": "Streaming STT",
            "effort": "medium",
            "changes": [
                "Add Deepgram WebSocket streaming endpoint",
                "Modify voice WebSocket to forward audio chunks",
                "Add partial_transcript message type",
                "Keep existing batch flow as fallback",
            ],
            "backward_compat": True,
        },
        "phase_2": {
            "name": "Voice Activity Detection",
            "effort": "low",
            "changes": [
                "Configure Deepgram VAD parameters",
                "Add speech_end detection",
                "Auto-submit on silence (no button release needed)",
            ],
            "backward_compat": True,
        },
        "phase_3": {
            "name": "Incremental LLM Preparation",
            "effort": "medium",
            "changes": [
                "Pre-build prompt template on speech start",
                "Pre-fetch context from memory system",
                "Start LLM call as soon as final transcript arrives",
            ],
            "backward_compat": True,
        },
        "phase_4": {
            "name": "Streaming TTS",
            "effort": "high",
            "changes": [
                "Implement chunked audio playback",
                "Queue management for AudioBufferSourceNodes",
                "Handle mid-interruption (candidate starts speaking)",
            ],
            "backward_compat": True,
        },
    },

    "deepgram_ws_config": {
        "endpoint": "wss://api.deepgram.com/v1/listen",
        "params": {
            "model": "nova-3",
            "language": "en",
            "smart_format": "true",
            "diarize": "false",
            "encoding": "webm",
            "sample_rate": 48000,
            "channels": 1,
            "vad_events": "true",
            "interim_results": "true",
            "endpointing": 300,
            "utterance_end_ms": 1000,
        },
        "auth": "Token {DEEPGRAM_API_KEY}",
        "message_format": {
            "type": "audio",
            "data": "base64-encoded audio chunk",
        },
    },

    "latency_budget": {
        "current_batch": {
            "stt": "300-500ms",
            "llm": "500-1500ms",
            "tts": "300-500ms",
            "total": "1100-2500ms",
        },
        "target_streaming": {
            "stt_overlap": "0ms (happens during speech)",
            "stt_final": "100-200ms",
            "llm_overlap": "0ms (prefetch during speech)",
            "llm_final": "500-1000ms",
            "tts_overlap": "200ms (chunked start)",
            "tts_final": "300-500ms",
            "total_perceived": "~500ms",
            "total_actual": "~800ms",
        },
    },

    "interruption_handling": {
        "description": "When candidate starts speaking while TTS is playing",
        "behavior": "Stop TTS playback, capture new speech, process as new answer",
        "implementation": "Track AudioBufferSourceNode, call .stop() on speech_start event",
    },
}
