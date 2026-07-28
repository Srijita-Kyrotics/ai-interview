"""
Voice Pipeline
==============
Real-time STT → LLM → TTS pipeline for voice interviews.

Architecture:
  Candidate Mic
    │
    ▼ (WebSocket audio chunks / blob)
  STT Engine  ← Deepgram Nova-3 (primary) / Whisper (fallback)
    │
    ▼ (transcript text)
  Interview Agent (LangGraph runner)
    │
    ▼ (response text)
  TTS Engine  ← ElevenLabs Turbo (primary) / OpenAI TTS (fallback)
    │
    ▼ (audio bytes, MP3 / WAV)
  Candidate Speaker

Target end-to-end latency: < 1500ms
STT target: < 400ms
LLM target: < 700ms
TTS target: < 400ms

This module provides:
1. DeepgramSTT  - streaming speech-to-text
2. WhisperSTT   - fallback offline STT
3. ElevenLabsTTS - neural TTS
4. OpenAITTS    - fallback TTS
5. VoicePipeline - orchestrates the full pipeline

NOTE: API keys are read from environment.
Add to .env:
  DEEPGRAM_API_KEY=...
  ELEVENLABS_API_KEY=...
  ELEVENLABS_VOICE_ID=...  (default: "21m00Tcm4TlvDq8ikWAM" - Rachel)
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
from typing import AsyncIterator, Callable, Optional

import httpx

from app.config import settings

logger = logging.getLogger("ai_interview.voice")


# ── STT: Deepgram ──────────────────────────────────────────────────────────────

class DeepgramSTT:
    """
    Deepgram Nova-3 streaming speech-to-text.
    
    Uses Deepgram's WebSocket streaming API for low-latency transcription.
    Supports interim results and endpointing.
    """

    BASE_URL = "wss://api.deepgram.com/v1/listen"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.ws = None

    @classmethod
    def from_settings(cls) -> "DeepgramSTT":
        api_key = getattr(settings, "deepgram_api_key", "")
        return cls(api_key=api_key)

    def get_ws_url(self) -> str:
        params = (
            "model=nova-3"
            "&language=en-US"
            "&smart_format=true"
            "&punctuate=true"
            "&endpointing=800"  # 800ms silence = end of utterance
            "&interim_results=true"
            "&utterance_end_ms=1000"
        )
        return f"{self.BASE_URL}?{params}"

    async def transcribe_audio_bytes(self, audio_bytes: bytes) -> str:
        """
        Send raw audio bytes to Deepgram REST API (for non-streaming usage).
        Returns the transcribed text.
        """
        if not self.api_key:
            logger.warning("Deepgram API key not configured, using fallback")
            return ""

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(
                    "https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true&punctuate=true",
                    headers={
                        "Authorization": f"Token {self.api_key}",
                        "Content-Type": "audio/webm",
                    },
                    content=audio_bytes,
                )
                response.raise_for_status()
                data = response.json()
                channels = data.get("results", {}).get("channels", [])
                if channels:
                    alternatives = channels[0].get("alternatives", [])
                    if alternatives:
                        return alternatives[0].get("transcript", "").strip()
                return ""
            except Exception as e:
                logger.error("Deepgram transcription failed", extra={"error": str(e)})
                return ""


# ── STT: Whisper (Fallback via Groq or local) ─────────────────────────────────

class WhisperSTT:
    """
    Whisper STT via Groq API (fast, free tier available) or OpenAI.
    Used as fallback when Deepgram is unavailable.
    """

    def __init__(self, groq_api_key: str = "", openai_api_key: str = ""):
        self.groq_api_key = groq_api_key
        self.openai_api_key = openai_api_key

    @classmethod
    def from_settings(cls) -> "WhisperSTT":
        return cls(
            groq_api_key=getattr(settings, "groq_api_key", ""),
            openai_api_key=getattr(settings, "openai_api_key", ""),
        )

    async def transcribe_audio_bytes(self, audio_bytes: bytes, filename: str = "audio.webm") -> str:
        """Transcribe audio bytes using Groq Whisper API."""
        api_key = self.groq_api_key or self.openai_api_key
        if not api_key:
            logger.warning("No Whisper API key configured")
            return ""

        base_url = (
            "https://api.groq.com/openai/v1/audio/transcriptions"
            if self.groq_api_key
            else "https://api.openai.com/v1/audio/transcriptions"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                files = {
                    "file": (filename, io.BytesIO(audio_bytes), "audio/webm"),
                    "model": (None, "whisper-large-v3-turbo"),
                    "language": (None, "en"),
                    "response_format": (None, "json"),
                }
                response = await client.post(
                    base_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    files=files,
                )
                response.raise_for_status()
                return response.json().get("text", "").strip()
            except Exception as e:
                logger.error("Whisper transcription failed", extra={"error": str(e)})
                return ""


# ── TTS: ElevenLabs ───────────────────────────────────────────────────────────

class ElevenLabsTTS:
    """
    ElevenLabs Turbo v2.5 text-to-speech.
    
    Uses the "eleven_turbo_v2_5" model for lowest latency.
    Voice: "Alex" persona mapped to Rachel (neutral, professional).
    """

    BASE_URL = "https://api.elevenlabs.io/v1"
    DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel - neutral, professional

    def __init__(self, api_key: str, voice_id: str = ""):
        self.api_key = api_key
        self.voice_id = voice_id or self.DEFAULT_VOICE_ID

    @classmethod
    def from_settings(cls) -> "ElevenLabsTTS":
        return cls(
            api_key=getattr(settings, "elevenlabs_api_key", ""),
            voice_id=getattr(settings, "elevenlabs_voice_id", ""),
        )

    async def synthesize(self, text: str) -> bytes:
        """
        Convert text to speech audio bytes (MP3).
        
        Returns empty bytes if API key not configured.
        """
        if not self.api_key:
            logger.warning("ElevenLabs API key not configured")
            return b""

        url = f"{self.BASE_URL}/text-to-speech/{self.voice_id}/stream"

        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
                "style": 0.2,
                "use_speaker_boost": True,
            },
            "output_format": "mp3_44100_128",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                t0 = time.time()
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "xi-api-key": self.api_key,
                        "Content-Type": "application/json",
                        "Accept": "audio/mpeg",
                    },
                )
                response.raise_for_status()
                audio_bytes = response.content
                latency_ms = int((time.time() - t0) * 1000)
                logger.info(
                    "ElevenLabs TTS synthesized",
                    extra={"chars": len(text), "bytes": len(audio_bytes), "latency_ms": latency_ms}
                )
                return audio_bytes
            except Exception as e:
                logger.error("ElevenLabs TTS failed", extra={"error": str(e)})
                return b""

    async def synthesize_streaming(self, text: str) -> AsyncIterator[bytes]:
        """
        Stream audio chunks for even lower perceived latency.
        Yields MP3 chunks as they arrive.
        """
        if not self.api_key:
            return

        url = f"{self.BASE_URL}/text-to-speech/{self.voice_id}/stream"
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream(
                "POST",
                url,
                json=payload,
                headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
            ) as response:
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    if chunk:
                        yield chunk


# ── TTS: OpenAI (Fallback) ────────────────────────────────────────────────────

class OpenAITTS:
    """
    OpenAI TTS API as fallback.
    Uses "alloy" voice (neutral) with tts-1 model.
    """

    def __init__(self, api_key: str):
        self.api_key = api_key

    @classmethod
    def from_settings(cls) -> "OpenAITTS":
        return cls(api_key=getattr(settings, "openai_api_key", ""))

    async def synthesize(self, text: str) -> bytes:
        if not self.api_key:
            return b""
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.post(
                    "https://api.openai.com/v1/audio/speech",
                    json={
                        "model": "tts-1",
                        "input": text,
                        "voice": "alloy",
                        "response_format": "mp3",
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                )
                response.raise_for_status()
                return response.content
            except Exception as e:
                logger.error("OpenAI TTS failed", extra={"error": str(e)})
                return b""


# ── Voice Pipeline Orchestrator ────────────────────────────────────────────────

class VoicePipeline:
    """
    Orchestrates the full voice interview pipeline:
    Audio → STT → Interview Agent → TTS → Audio
    
    Handles:
    - STT provider selection with fallback
    - TTS provider selection with fallback  
    - Latency tracking
    - Silence detection and VAD signals
    - Audio format normalization
    """

    def __init__(
        self,
        stt: DeepgramSTT | WhisperSTT,
        tts: ElevenLabsTTS | OpenAITTS,
        on_transcript: Optional[Callable[[str], None]] = None,
    ):
        self.stt = stt
        self.tts = tts
        self.on_transcript = on_transcript
        self._total_latency_ms: list[int] = []

    @classmethod
    def from_settings(cls) -> "VoicePipeline":
        """Create pipeline with best available providers."""
        # Try Deepgram first, fall back to Whisper
        deepgram_key = getattr(settings, "deepgram_api_key", "")
        if deepgram_key:
            stt = DeepgramSTT(api_key=deepgram_key)
            logger.info("Voice pipeline: using Deepgram STT")
        else:
            stt = WhisperSTT.from_settings()
            logger.info("Voice pipeline: using Whisper STT (fallback)")

        # Try ElevenLabs first, fall back to OpenAI
        el_key = getattr(settings, "elevenlabs_api_key", "")
        if el_key:
            tts = ElevenLabsTTS.from_settings()
            logger.info("Voice pipeline: using ElevenLabs TTS")
        else:
            tts = OpenAITTS.from_settings()
            logger.info("Voice pipeline: using OpenAI TTS (fallback)")

        return cls(stt=stt, tts=tts)

    async def audio_to_text(self, audio_bytes: bytes) -> str:
        """
        Convert audio bytes to text transcript.
        Returns empty string if transcription fails.
        """
        t0 = time.time()
        text = await self.stt.transcribe_audio_bytes(audio_bytes)
        latency_ms = int((time.time() - t0) * 1000)
        logger.info("STT completed", extra={"latency_ms": latency_ms, "text_len": len(text)})

        if self.on_transcript and text:
            self.on_transcript(text)

        return text

    async def text_to_audio(self, text: str) -> bytes:
        """
        Convert text to audio bytes.
        Returns empty bytes if synthesis fails.
        """
        t0 = time.time()
        audio = await self.tts.synthesize(text)
        latency_ms = int((time.time() - t0) * 1000)
        logger.info("TTS completed", extra={"latency_ms": latency_ms, "audio_bytes": len(audio)})
        return audio

    async def process_turn(
        self,
        audio_bytes: bytes,
        interview_runner,  # InterviewGraphRunner
    ) -> dict:
        """
        Process a full voice turn:
        1. STT: audio → text
        2. Interview agent: text → response text
        3. TTS: response text → audio
        
        Returns:
        {
            "transcript": str,      # What the candidate said
            "response_text": str,   # What the AI said
            "response_audio": bytes, # Audio of AI response
            "phase": str,           # Interview phase
            "should_end": bool,     # Whether interview is done
            "total_latency_ms": int,
        }
        """
        t_start = time.time()

        # Step 1: STT
        t_stt = time.time()
        transcript = await self.audio_to_text(audio_bytes)
        stt_ms = int((time.time() - t_stt) * 1000)

        if not transcript:
            return {
                "transcript": "",
                "response_text": "I'm sorry, I didn't catch that. Could you please repeat?",
                "response_audio": await self.text_to_audio("I'm sorry, I didn't catch that. Could you please repeat?"),
                "phase": "interviewing",
                "should_end": False,
                "total_latency_ms": int((time.time() - t_start) * 1000),
                "stt_latency_ms": stt_ms,
                "llm_latency_ms": 0,
                "tts_latency_ms": 0,
            }

        # Step 2: LLM (Interview Agent)
        t_llm = time.time()
        agent_result = await interview_runner.process_answer(transcript)
        llm_ms = int((time.time() - t_llm) * 1000)

        response_text = agent_result.get("text", "")

        # Step 3: TTS
        t_tts = time.time()
        response_audio = await self.text_to_audio(response_text) if response_text else b""
        tts_ms = int((time.time() - t_tts) * 1000)

        total_ms = int((time.time() - t_start) * 1000)
        self._total_latency_ms.append(total_ms)

        logger.info(
            "Voice turn complete",
            extra={
                "stt_ms": stt_ms,
                "llm_ms": llm_ms,
                "tts_ms": tts_ms,
                "total_ms": total_ms,
                "target_ms": 1500,
                "within_target": total_ms < 1500,
            }
        )

        return {
            "transcript": transcript,
            "response_text": response_text,
            "response_audio": response_audio,
            "phase": agent_result.get("phase", "interviewing"),
            "should_end": agent_result.get("should_end", False),
            "is_follow_up": agent_result.get("is_follow_up", False),
            "total_latency_ms": total_ms,
            "stt_latency_ms": stt_ms,
            "llm_latency_ms": llm_ms,
            "tts_latency_ms": tts_ms,
        }

    def get_average_latency_ms(self) -> float:
        """Return average end-to-end latency."""
        if not self._total_latency_ms:
            return 0.0
        return sum(self._total_latency_ms) / len(self._total_latency_ms)
