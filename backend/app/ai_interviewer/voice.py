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
import contextlib
import io
import logging
import re
import time
from collections.abc import AsyncIterator, Callable

import httpx

from app.config import settings

logger = logging.getLogger("ai_interview.voice")

# Shared HTTP clients so every TTS/STT call reuses the TCP+TLS connection
# instead of paying a handshake (~100-400ms) on each request.
_HTTP_CLIENTS: dict[float, httpx.AsyncClient] = {}


def _shared_client(timeout: float) -> httpx.AsyncClient:
    if timeout not in _HTTP_CLIENTS:
        _HTTP_CLIENTS[timeout] = httpx.AsyncClient(timeout=timeout)
    return _HTTP_CLIENTS[timeout]


def _close_http_clients() -> None:
    for client in _HTTP_CLIENTS.values():
        with contextlib.suppress(Exception):
            asyncio.get_event_loop().run_until_complete(client.aclose())
    _HTTP_CLIENTS.clear()

# Strip characters that should never be spoken aloud: markdown, URLs,
# emoji, bullet symbols and control noise. Keeps TTS output clean and
# lets the voice sound like a person, not a read-aloud bot.
_MARKDOWN_RE = re.compile(r"(\*\*|__|\*|_|`|#+|\>|~~|--+)")
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002702-\U000027B0\U0001F1E6-\U0001F1FF\U00002600-\U000026FF\U0000FE0F]"
)


def clean_text_for_speech(text: str) -> str:
    """Normalize LLM output so it reads naturally when spoken aloud."""
    if not text:
        return ""
    cleaned = _URL_RE.sub(" ", text)
    cleaned = _MARKDOWN_RE.sub("", cleaned)
    cleaned = _EMOJI_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("\\n", " ")
    cleaned = cleaned.replace("\r", " ")
    cleaned = _MULTISPACE_RE.sub(" ", cleaned)
    cleaned = cleaned.replace("\n\n", ". ")
    cleaned = " ".join(cleaned.split())
    return cleaned.strip()


# ── Multi-Language Support ──────────────────────────────────────────────────────

# Language codes mapping for different providers
LANGUAGE_MAP = {
    "en": {"deepgram": "en-US", "whisper": "en", "elevenlabs": "en-US", "openai": "en"},
    "es": {"deepgram": "es", "whisper": "es", "elevenlabs": "es", "openai": "es"},
    "fr": {"deepgram": "fr", "whisper": "fr", "elevenlabs": "fr", "openai": "fr"},
    "de": {"deepgram": "de", "whisper": "de", "elevenlabs": "de", "openai": "de"},
    "it": {"deepgram": "it", "whisper": "it", "elevenlabs": "it", "openai": "it"},
    "pt": {"deepgram": "pt", "whisper": "pt", "elevenlabs": "pt", "openai": "pt"},
    "hi": {"deepgram": "hi", "whisper": "hi", "elevenlabs": "hi", "openai": "hi"},
    "ja": {"deepgram": "ja", "whisper": "ja", "elevenlabs": "ja", "openai": "ja"},
    "ko": {"deepgram": "ko", "whisper": "ko", "elevenlabs": "ko", "openai": "ko"},
    "zh": {"deepgram": "zh", "whisper": "zh", "elevenlabs": "zh", "openai": "zh"},
}

# ElevenLabs multilingual voices (v2.5 supports 28+ languages)
ELEVENLABS_VOICES = {
    "en-US": {"male": "pNInz6obpgDQGcFmaJgB", "female": "21m00Tcm4TlvDq8ikWAM"},  # Adam, Rachel
    "es": {"male": "ErXwobaYiN019PkySvjV", "female": "AZnzlk1XvdvUeBnXmlld"},
    "fr": {"male": "VR6AewLTigWG4xSOukaG", "female": "pMsXgVXv3BLzUgSXRzdE"},
    "de": {"male": "MF3mGyEYCl7XYWbV9V6O", "female": "EXAVITQu4vr4xnSDxMaL"},
    "it": {"male": "zcAOhNBS3c14rBihAFp1", "female": "eKpK1MX9V4pP3y1Dn30S"},
    "pt": {"male": "TxGEqnHWrfWFTfGW9XjX", "female": "GBvfxmT1sQBllAIe52uv"},
    "hi": {"male": "iP95p4xoKVk53GoZ742B", "female": "jBpfuIE2acCO8z3wKNLl"},
    "ja": {"male": "cgSgspJ2msm6clMCkdW9", "female": "fYdN0eO5P5mV7Z4kL2jD"},
    "ko": {"male": "bVMeCyTHy58xNoL34h3p", "female": "ZF6FPAbjXT4488Vc0Rww"},
    "zh": {"male": "zrHiDhphv9ZnVXBqCLjz", "female": "Xb7hH8MSUJpSbSDYk0k2"},
}

# OpenAI TTS voices
OPENAI_VOICES = {
    "en": {"male": "echo", "female": "nova"},
    "es": {"male": "onyx", "female": "nova"},
    "fr": {"male": "onyx", "female": "nova"},
    "de": {"male": "onyx", "female": "nova"},
    "it": {"male": "onyx", "female": "nova"},
    "pt": {"male": "onyx", "female": "nova"},
    "hi": {"male": "onyx", "female": "nova"},
    "ja": {"male": "onyx", "female": "nova"},
    "ko": {"male": "onyx", "female": "nova"},
    "zh": {"male": "onyx", "female": "nova"},
}


def get_supported_languages() -> list[dict]:
    """Get list of supported languages with their codes and native names."""
    return [
        {"code": "en", "name": "English", "native": "English"},
        {"code": "es", "name": "Spanish", "native": "Español"},
        {"code": "fr", "name": "French", "native": "Français"},
        {"code": "de", "name": "German", "native": "Deutsch"},
        {"code": "it", "name": "Italian", "native": "Italiano"},
        {"code": "pt", "name": "Portuguese", "native": "Português"},
        {"code": "hi", "name": "Hindi", "native": "हिन्दी"},
        {"code": "ja", "name": "Japanese", "native": "日本語"},
        {"code": "ko", "name": "Korean", "native": "한국어"},
        {"code": "zh", "name": "Chinese", "native": "中文"},
    ]


async def detect_language(audio_bytes: bytes) -> str:
    """
    Detect the language from audio bytes.
    
    Uses a simple heuristic - in production, you'd use a dedicated
    language identification model like fastText or Whisper's built-in
    language detection.
    
    For now, returns the default language.
    """
    # TODO: Implement actual language detection
    # Could use whisper-large-v3's language detection
    return "en-US"


def get_voice_for_language(language: str, gender: str = "male", provider: str = "elevenlabs") -> str:
    """Get the appropriate voice ID for a language and provider."""
    lang_code = language.split("-")[0]  # Extract base language code
    
    if provider == "elevenlabs":
        voices = ELEVENLABS_VOICES.get(lang_code, ELEVENLABS_VOICES.get("en-US", {}))
        return voices.get(gender, ELEVENLABS_VOICES["en-US"][gender])
    elif provider == "openai":
        voices = OPENAI_VOICES.get(lang_code, OPENAI_VOICES.get("en", {}))
        return voices.get(gender, OPENAI_VOICES["en"][gender])
    return ELEVENLABS_VOICES["en-US"][gender]


# ── STT: Deepgram ──────────────────────────────────────────────────────────────

class DeepgramSTT:
    """
    Deepgram Nova-3 streaming speech-to-text.

    Uses Deepgram's WebSocket streaming API for low-latency transcription.
    Supports interim results and endpointing.
    """

    BASE_URL = "wss://api.deepgram.com/v1/listen"

    def __init__(self, api_key: str, language: str = "en-US"):
        self.api_key = api_key
        self.language = language
        self.ws = None

    @classmethod
    def from_settings(cls, language: str = "en-US") -> DeepgramSTT:
        api_key = getattr(settings, "deepgram_api_key", "")
        return cls(api_key=api_key, language=language)

    def get_ws_url(self) -> str:
        params = (
            f"model=nova-3"
            f"&language={self.language}"
            "&smart_format=true"
            "&punctuate=true"
            "&endpointing=800"  # 800ms silence = end of utterance
            "&interim_results=true"
            "&utterance_end_ms=1000"
        )
        return f"{self.BASE_URL}?{params}"

    def set_language(self, language: str) -> None:
        """Change the transcription language."""
        self.language = language

    async def transcribe_audio_bytes(self, audio_bytes: bytes, language: str | None = None) -> str:
        """
        Send raw audio bytes to Deepgram REST API (for non-streaming usage).
        Returns the transcribed text.
        """
        if not self.api_key:
            logger.warning("Deepgram API key not configured, using fallback")
            return ""

        lang = language or self.language
        client = _shared_client(10.0)
        try:
            response = await client.post(
                f"https://api.deepgram.com/v1/listen?model=nova-3&smart_format=true&punctuate=true&language={lang}",
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
            logger.error("Deepgram transcription failed", extra={"error": str(e), "language": lang})
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
    def from_settings(cls) -> WhisperSTT:
        return cls(
            groq_api_key=getattr(settings, "groq_api_key", ""),
            openai_api_key=getattr(settings, "openai_api_key", ""),
        )

    async def transcribe_audio_bytes(self, audio_bytes: bytes, filename: str = "audio.webm", language: str = "en") -> str:
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

        client = _shared_client(30.0)
        try:
            files = {
                "file": (filename, io.BytesIO(audio_bytes), "audio/webm"),
                "model": (None, "whisper-large-v3-turbo"),
                "language": (None, language),
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
            logger.error("Whisper transcription failed", extra={"error": str(e), "language": language})
            return ""


# ── TTS: ElevenLabs ───────────────────────────────────────────────────────────

class ElevenLabsTTS:
    """
    ElevenLabs Turbo v2.5 text-to-speech.

    Uses the "eleven_turbo_v2_5" model for lowest latency.
    Supports multilingual voices for 28+ languages.
    """

    BASE_URL = "https://api.elevenlabs.io/v1"
    DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"  # Adam - professional male voice (English)

    def __init__(self, api_key: str, voice_id: str = "", language: str = "en-US", gender: str = "male"):
        self.api_key = api_key
        self.voice_id = voice_id or get_voice_for_language(language, gender, "elevenlabs")
        self.language = language
        self.gender = gender

    @classmethod
    def from_settings(cls, language: str = "en-US", gender: str = "male") -> ElevenLabsTTS:
        return cls(
            api_key=getattr(settings, "elevenlabs_api_key", ""),
            voice_id=getattr(settings, "elevenlabs_voice_id", ""),
            language=language,
            gender=gender,
        )

    def set_voice(self, language: str, gender: str = "male") -> None:
        """Change the voice for a different language."""
        self.language = language
        self.gender = gender
        self.voice_id = get_voice_for_language(language, gender, "elevenlabs")

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
            "model_id": "eleven_multilingual_v2",  # Supports 28+ languages
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
                "style": 0.2,
                "use_speaker_boost": True,
            },
            "output_format": "mp3_44100_128",
        }

        client = _shared_client(15.0)
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
                extra={"chars": len(text), "bytes": len(audio_bytes), "latency_ms": latency_ms, "language": self.language, "voice": self.voice_id}
            )
            return audio_bytes
        except Exception as e:
            logger.error("ElevenLabs TTS failed", extra={"error": str(e), "language": self.language})
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
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8},
        }

        async with httpx.AsyncClient(timeout=30.0) as client, client.stream(
            "POST",
            url,
            json=payload,
            headers={"xi-api-key": self.api_key, "Content-Type": "application/json"},
        ) as response:
            async for chunk in response.aiter_bytes(chunk_size=4096):
                if chunk:
                    yield chunk


# ── TTS: OpenAI (Fallback) ────────────────────────────────────────────────────

# ── TTS: OpenAI (Fallback) ──────────────────────────────────────────────────────

class OpenAITTS:
    """
    OpenAI TTS API as fallback.
    Supports multiple languages with tts-1 model.
    """

    def __init__(self, api_key: str, voice: str = "echo", language: str = "en"):
        self.api_key = api_key
        self.voice = voice or get_voice_for_language(language, "male", "openai")
        self.language = language

    @classmethod
    def from_settings(cls, language: str = "en", voice: str = "") -> OpenAITTS:
        return cls(
            api_key=getattr(settings, "openai_api_key", ""),
            voice=voice or getattr(settings, "openai_tts_voice", ""),
            language=language,
        )

    def set_voice(self, language: str, gender: str = "male") -> None:
        """Change the voice for a different language."""
        self.language = language
        self.voice = get_voice_for_language(language, gender, "openai")

    async def synthesize(self, text: str) -> bytes:
        if not self.api_key:
            return b""

        client = _shared_client(15.0)
        try:
            response = await client.post(
                "https://api.openai.com/v1/audio/speech",
                json={
                    "model": "tts-1",
                    "input": clean_text_for_speech(text),
                    "voice": self.voice,
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
            logger.error("OpenAI TTS failed", extra={"error": str(e), "language": self.language})
            return b""


# ── Voice Pipeline Orchestrator ────────────────────────────────────────────────
 
class VoicePipeline:
    """
    Orchestrates the full voice interview pipeline:
    Audio → STT → Interview Agent → TTS → Audio
 
    Handles:
    - STT provider selection with fallback
    - TTS provider selection with fallback
    - Multi-language support with language detection
    - Latency tracking
    - Silence detection and VAD signals
    - Audio format normalization
    """
 
    def __init__(
        self,
        stt: DeepgramSTT | WhisperSTT,
        tts: ElevenLabsTTS | OpenAITTS,
        on_transcript: Callable[[str], None] | None = None,
        language: str = "en-US",
        gender: str = "male",
    ):
        self.stt = stt
        self.tts = tts
        self.on_transcript = on_transcript
        self.language = language
        self.gender = gender
        self._total_latency_ms: list[int] = []
 
    @classmethod
    def from_settings(cls, language: str = "en-US", gender: str = "male") -> VoicePipeline:
        """Create pipeline with best available providers.
 
        STT priority: Deepgram → Groq/OpenAI Whisper.
        TTS priority: ElevenLabs → OpenAI.
        """
        # STT: Deepgram first, then Groq/OpenAI Whisper.
        deepgram_key = getattr(settings, "deepgram_api_key", "")
        if deepgram_key:
            stt = DeepgramSTT.from_settings(language=language)
            logger.info("Voice pipeline: using Deepgram STT", extra={"language": language})
        else:
            whisper_lang = language.split("-")[0]
            stt = WhisperSTT.from_settings()
            logger.info("Voice pipeline: using Whisper STT (fallback)", extra={"language": whisper_lang})
 
        # TTS: ElevenLabs first, then OpenAI.
        el_key = getattr(settings, "elevenlabs_api_key", "")
        if el_key:
            tts = ElevenLabsTTS.from_settings(language=language, gender=gender)
            logger.info("Voice pipeline: using ElevenLabs TTS", extra={"language": language, "gender": gender})
        else:
            openai_lang = language.split("-")[0]
            tts = OpenAITTS.from_settings(language=openai_lang)
            logger.info("Voice pipeline: using OpenAI TTS (fallback)", extra={"language": openai_lang})
 
        return cls(stt=stt, tts=tts, language=language, gender=gender)
 
    def set_language(self, language: str, gender: str | None = None) -> None:
        """Change the pipeline language."""
        self.language = language
        if gender:
            self.gender = gender
        
        # Update STT language
        if isinstance(self.stt, DeepgramSTT):
            self.stt.set_language(language)
        
        # Update TTS voice
        if isinstance(self.tts, ElevenLabsTTS):
            self.tts.set_voice(language, gender or self.gender)
        elif isinstance(self.tts, OpenAITTS):
            self.tts.set_voice(language, gender or self.gender)
 
    async def audio_to_text(self, audio_bytes: bytes) -> str:
        """
        Convert audio bytes to text transcript.
        Returns empty string if transcription fails.
        """
        t0 = time.time()
        # Pass language to STT
        if isinstance(self.stt, DeepgramSTT):
            text = await self.stt.transcribe_audio_bytes(audio_bytes, language=self.language)
        elif isinstance(self.stt, WhisperSTT):
            whisper_lang = self.language.split("-")[0]
            text = await self.stt.transcribe_audio_bytes(audio_bytes, language=whisper_lang)
        else:
            text = await self.stt.transcribe_audio_bytes(audio_bytes)
        
        latency_ms = int((time.time() - t0) * 1000)
        logger.info("STT completed", extra={"latency_ms": latency_ms, "text_len": len(text), "language": self.language})
 
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
