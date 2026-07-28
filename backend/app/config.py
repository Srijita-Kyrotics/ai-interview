"""Centralized configuration module. All settings live here and read from environment variables."""

from __future__ import annotations

import secrets
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # ── App ────────────────────────────────────────────────────────────────
    environment: str = Field("development", alias="ENVIRONMENT")
    debug: bool = Field(False, alias="DEBUG")

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str = Field(
        "postgresql://postgres:postgres@localhost:5432/ai_interview",
        alias="DATABASE_URL",
    )
    db_pool_min: int = Field(2, alias="DB_POOL_MIN")
    db_pool_max: int = Field(10, alias="DB_POOL_MAX")

    # ── Auth / JWT ────────────────────────────────────────────────────────
    jwt_secret: str = Field("", alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = Field(24, alias="JWT_EXPIRY_HOURS")

    # ── SMTP ──────────────────────────────────────────────────────────────
    smtp_host: str = Field("", alias="SMTP_HOST")
    smtp_port: int = Field(587, alias="SMTP_PORT")
    smtp_user: str = Field("", alias="SMTP_USER")
    smtp_password: str = Field("", alias="SMTP_PASSWORD")
    smtp_from: str = Field("", alias="SMTP_FROM")

    # ── External APIs ─────────────────────────────────────────────────────
    gemini_api_key: str = Field("", alias="GEMINI_API_KEY")
    gemini_model: str = Field("gemini-1.5-flash", alias="GEMINI_MODEL")
    judge0_api_key: str = Field("", alias="JUDGE0_API_KEY")
    judge0_host: str = Field("judge0-ce.p.rapidapi.com", alias="JUDGE0_HOST")
    judge0_timeout: float = Field(10.0, alias="JUDGE0_TIMEOUT")
    judge0_language_ids: dict[str, int] = Field(
        {"python": 71, "javascript": 63, "java": 62, "c": 50, "csharp": 51},
        alias="JUDGE0_LANGUAGE_IDS",
    )

    # ── AI Interviewer: Voice Pipeline ────────────────────────────────────
    deepgram_api_key: str = Field("", alias="DEEPGRAM_API_KEY")
    elevenlabs_api_key: str = Field("", alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field("21m00Tcm4TlvDq8ikWAM", alias="ELEVENLABS_VOICE_ID")
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    groq_api_key: str = Field("", alias="GROQ_API_KEY")

    # ── AI Interviewer: LangGraph ─────────────────────────────────────────
    ai_interviewer_max_questions: int = Field(12, alias="AI_INTERVIEWER_MAX_QUESTIONS")
    ai_interviewer_gemini_model: str = Field("gemini-1.5-pro", alias="AI_INTERVIEWER_GEMINI_MODEL")
    ai_interviewer_temperature: float = Field(0.7, alias="AI_INTERVIEWER_TEMPERATURE")
    ai_interviewer_session_ttl_hours: int = Field(4, alias="AI_INTERVIEWER_SESSION_TTL_HOURS")

    # ── CORS ──────────────────────────────────────────────────────────────
    allowed_origins: str = Field(
        "http://localhost:5173,http://127.0.0.1:5173", alias="ALLOWED_ORIGINS"
    )

    # ── CSP ──────────────────────────────────────────────────────────────
    csp_connect_sources: str = Field(
        "'self' http://localhost:* ws://localhost:*", alias="CSP_CONNECT_SOURCES"
    )

    # ── Uploads ───────────────────────────────────────────────────────────
    max_upload_bytes: int = Field(10 * 1024 * 1024, alias="MAX_UPLOAD_BYTES")

    # ── Paths ────────────────────────────────────────────────────────────
    shared_dir: str = Field("", alias="SHARED_DIR")
    frontend_questions_dir: str = Field("", alias="FRONTEND_QUESTIONS_DIR")

    # ── Password Policy ──────────────────────────────────────────────────
    min_password_length: int = Field(8, alias="MIN_PASSWORD_LENGTH")
    pbkdf2_iterations: int = Field(120000, alias="PBKDF2_ITERATIONS")

    # ── Scoring ──────────────────────────────────────────────────────────
    default_aptitude_score: int = Field(80, alias="DEFAULT_APTITUDE_SCORE")
    default_coding_score: int = Field(75, alias="DEFAULT_CODING_SCORE")
    default_technical_score: int = Field(70, alias="DEFAULT_TECHNICAL_SCORE")
    default_hr_score: int = Field(85, alias="DEFAULT_HR_SCORE")

    # ── OTP / Captcha ────────────────────────────────────────────────────
    otp_ttl_seconds: int = Field(300, alias="OTP_TTL_SECONDS")
    captcha_ttl_seconds: int = Field(300, alias="CAPTCHA_TTL_SECONDS")
    otp_rate_limit: int = Field(5, alias="OTP_RATE_LIMIT")
    otp_rate_window: int = Field(600, alias="OTP_RATE_WINDOW")
    otp_ip_rate_limit: int = Field(20, alias="OTP_IP_RATE_LIMIT")
    max_otp_attempts: int = Field(5, alias="MAX_OTP_ATTEMPTS")

    # ── Rate Limits ───────────────────────────────────────────────────────
    code_rate_limit: int = Field(20, alias="CODE_RATE_LIMIT")
    code_rate_window: int = Field(600, alias="CODE_RATE_WINDOW")
    ai_rate_limit: int = Field(10, alias="AI_RATE_LIMIT")
    ai_rate_window: int = Field(600, alias="AI_RATE_WINDOW")
    admin_rate_limit: int = Field(30, alias="ADMIN_RATE_LIMIT")
    admin_rate_window: int = Field(600, alias="ADMIN_RATE_WINDOW")
    max_compare_sessions: int = Field(5, alias="MAX_COMPARE_SESSIONS")

    # ── Logging ───────────────────────────────────────────────────────────
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    log_format: str = Field("json", alias="LOG_FORMAT")  # "json" or "text"

    # ── Email ────────────────────────────────────────────────────────────
    email_subject: str = Field("AI Interview Platform OTP", alias="EMAIL_SUBJECT")

    # ── Resume ───────────────────────────────────────────────────────────
    resume_raw_text_limit: int = Field(2000, alias="RESUME_RAW_TEXT_LIMIT")

    # ── Session cleanup ───────────────────────────────────────────────────
    session_retention_days: int = Field(30, alias="SESSION_RETENTION_DAYS")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def smtp_configured(self) -> bool:
        return all([self.smtp_host, self.smtp_user, self.smtp_password, self.smtp_from])

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def shared_dir_path(self) -> Path:
        if self.shared_dir:
            return Path(self.shared_dir)
        return BASE_DIR / "shared"

    @property
    def frontend_questions_dir_path(self) -> Path:
        if self.frontend_questions_dir:
            return Path(self.frontend_questions_dir)
        return BASE_DIR / "frontend" / "public" / "questions"

    @property
    def default_scores(self) -> dict[str, int]:
        return {
            "aptitude": self.default_aptitude_score,
            "coding": self.default_coding_score,
            "technical": self.default_technical_score,
            "hr": self.default_hr_score,
        }

    @property
    def resolved_jwt_secret(self) -> str:
        if self.jwt_secret:
            return self.jwt_secret
        secret_file = BASE_DIR / "backend" / ".jwt_secret"
        if secret_file.exists():
            return secret_file.read_text(encoding="utf-8").strip()
        secret = secrets.token_hex(32)
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        secret_file.write_text(secret, encoding="utf-8")
        return secret

    model_config = {
        "env_file": [str(BASE_DIR / "backend" / ".env"), str(BASE_DIR / ".env")],
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
