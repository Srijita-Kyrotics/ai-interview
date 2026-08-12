# AI Interview Coach — Mock Recruitment Platform

A full-stack, end-to-end mock interview platform that simulates real company hiring pipelines with AI-assisted proctoring, resume parsing, multi-round assessments, a LangGraph-powered AI interviewer with live coding support, candidate dashboards, a recruiter portal, and detailed performance reports.

---

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [Supported Companies](#supported-companies)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [AI Interviewer System (LangGraph)](#ai-interviewer-system-langgraph)
- [Live Coding Integration](#live-coding-integration)
- [Voice Pipeline](#voice-pipeline)
- [Proctoring System](#proctoring-system)
- [Authentication & Roles](#authentication--roles)
- [Tech Stack](#tech-stack)
- [Deployment](#deployment)
- [Development Notes](#development-notes)

---

## Features

### Core Interview Flow
- **Resume upload & parsing** — Upload a PDF or TXT resume; the backend extracts name, email, phone, skills, education, experience, projects, and certifications automatically.
- **Company selection** — Choose one or more companies from a catalogue of 20+ firms (product-based, service-based, and hybrid). Interview rounds are merged and de-duplicated across selections.
- **Multi-round assessments**
  - **Aptitude** — Timed MCQ quiz (20s per question) with per-category scoring (quantitative, logical, verbal).
  - **Coding** — In-browser CodeMirror 6 code editor supporting Python, JavaScript, Java, and C++. Code is executed via the Judge0 API (with a seamless heuristic fallback if no API key is provided).
  - **Technical & HR** — Dynamic, AI-generated interview questions powered by the OpenRouter LLM, tailored to the candidate's parsed skills and selected company.

### AI Interviewer (LangGraph Pipeline)
- **Structured interview pipeline** — A 10-node LangGraph state graph that autonomously conducts multi-stage interviews: resume analysis, interview planning, question generation, answer analysis, follow-up generation, stage advancement, scoring, and report generation.
- **Voice-first interface** — Hold-to-talk voice input with real-time STT (Deepgram/Groq Whisper) and natural-sounding TTS (ElevenLabs/OpenAI).
- **Live coding integration** — A toggleable Chat/Code tab system with a full CodeMirror editor. Code is sent alongside voice answers and evaluated by Obi (the AI interviewer) in real-time.
- **Adaptive questioning** — Obi adapts difficulty based on answer quality, probes shallow answers with targeted follow-ups, and verifies claims against the resume.
- **Memory system** — Tracks topics covered, candidate strengths/weaknesses, unresolved claims, and per-topic depth across the entire interview.
- **Multi-dimensional scoring** — Technical accuracy, depth, clarity, confidence, completeness, and communication quality scored on 0-10 scales with weighted aggregation.

### Candidate Dashboard
- **Stats overview** — Total interviews completed, average score, best/worst scores, and companies practiced.
- **Performance trend chart** — Line chart (Recharts) tracking Overall, Aptitude, Coding, Technical, and HR scores across all past interviews.
- **Interview history** — Sortable table listing every past session with date, company, rounds completed, score, and drill-down view.
- **Session detail modal** — Full report view (scores, strengths, weaknesses, AI feedback, proctoring summary).

### Recruiter / Admin Portal
- **Role-based access** — Only users with `recruiter` or `admin` roles can access. First registered user is automatically admin.
- **Overview tab** — Platform-wide stats: total candidates, total interviews, average platform score, top score.
- **Candidates tab** — Filterable list with name, email, interview count, average score, and last active date.
- **Sessions tab** — Filterable list of every session with company, rounds, score, and actions.
- **Candidate comparison** — Compare up to 5 sessions side-by-side.
- **Session replay** — Full timeline view of answers and proctoring violations.
- **Proctoring viewer** — Integrity score, violation timeline, and webcam snapshot grid.

### Proctoring System
- **AI proctoring** — Face detection (face-api.js), object detection (TensorFlow COCO-SSD), tab-switch detection, fullscreen enforcement, screen-share monitoring, copy-paste & DevTools blocking.
- **Violation tracking** — All events logged to the database with timestamps, penalties, and integrity scores.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                         │
│                                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │   Auth   │  │  Resume  │  │  Rounds  │  │  AI Interview │   │
│  │  Page    │  │  Upload  │  │  (Apti/  │  │  (Voice+Code) │   │
│  │          │  │          │  │  Code/   │  │              │   │
│  │          │  │          │  │  Tech/HR)│  │              │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────┬───────┘   │
│                                                     │           │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────┴────────┐  │
│  │  Dashboard   │  │  Recruiter   │  │     Report Page      │  │
│  │  (Candidate) │  │  Portal      │  │  (PDF Export)        │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
│                                                                 │
│  WebSocket: /ai-interview/ws/voice                              │
│  Binary: Audio (WebM/opus) → Server                             │
│  Binary: TTS (MP3) ← Server                                     │
│  JSON: {code, language, audio_end} → Server                     │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI)                             │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              AI Interviewer Package                      │   │
│  │                                                          │   │
│  │  ┌──────────┐    ┌──────────────┐    ┌──────────────┐  │   │
│  │  │  Voice   │───▶│    Graph     │───▶│    Nodes     │  │   │
│  │  │ Pipeline │    │  (LangGraph) │    │  (10 nodes)  │  │   │
│  │  │ STT + TTS│    │              │    │              │  │   │
│  │  └──────────┘    └──────────────┘    └──────────────┘  │   │
│  │                       │                    │            │   │
│  │                  ┌────┴────┐          ┌────┴────┐      │   │
│  │                  │  State  │          │ Prompts │      │   │
│  │                  │ Schema  │          │ (8 LLM  │      │   │
│  │                  │         │          │ prompts)│      │   │
│  │                  └─────────┘          └─────────┘      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Platform Services                           │   │
│  │  Auth (JWT) │ Resume Parser │ Scoring │ Proctoring       │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              Database (PostgreSQL)                       │   │
│  │  users | sessions | otp_state | captcha | proctoring     │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Project Structure

```
AI-Interview-Coach-main/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app, all REST endpoints, JWT auth
│   │   ├── config.py                  # Pydantic Settings (all env vars)
│   │   ├── db.py                      # PostgreSQL database layer
│   │   ├── helpers.py                 # JWT, password hashing, utilities
│   │   ├── resume_parser.py           # PDF/text resume parsing
│   │   ├── interview_ws.py            # Legacy WebSocket interviewer
│   │   ├── ai_interviewer/            # NEW: LangGraph AI interviewer package
│   │   │   ├── __init__.py
│   │   │   ├── state.py               # TypedDict interview state schema
│   │   │   ├── nodes.py               # 10 LangGraph node implementations
│   │   │   ├── graph.py               # LangGraph graph assembly & runner
│   │   │   ├── prompts.py             # 8 LLM prompt templates
│   │   │   ├── router.py              # REST + WebSocket endpoints
│   │   │   ├── memory.py              # Interview memory manager
│   │   │   └── voice.py               # STT/TTS voice pipeline
│   │   └── scripts/
│   │       └── build_aptitude_bank.py  # Regenerate aptitude question bank
│   ├── requirements.txt
│   └── accounts.json                   # Legacy accounts (auto-migrated)
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx                    # React entry point
│       ├── App.jsx                     # SPA routing (all views)
│       ├── api.js                      # HTTP client wrapper
│       ├── constants.js
│       ├── styles.css                  # Global styles (Tailwind + custom)
│       ├── MathRenderer.jsx            # KaTeX math rendering
│       ├── ErrorBoundary.jsx
│       ├── hooks/
│       │   └── useInterviewWebSocket.js
│       ├── utils/
│       │   ├── ToastContext.jsx
│       │   ├── speak.js                # Web Speech API helpers
│       │   ├── score.js
│       │   ├── questionFormat.js
│       │   ├── formatTime.js
│       │   ├── audio.js
│       │   └── aptitudeFormat.js
│       ├── proctoring/
│       │   ├── useAssessmentProctoring.js
│       │   ├── ProctoringUI.jsx
│       │   └── proctoringState.js
│       └── components/
│           ├── AIInterviewer.jsx       # NEW: LangGraph AI interviewer UI
│           ├── CodeEditor.jsx          # CodeMirror 6 code editor
│           ├── LiveInterview.jsx       # Legacy chat interviewer
│           ├── ChatInterview.jsx
│           ├── AuthPage.jsx
│           ├── Home.jsx
│           ├── ResumePage.jsx
│           ├── CompanyPage.jsx
│           ├── RoundPage.jsx
│           ├── DashboardPage.jsx
│           ├── ReportPage.jsx
│           ├── RecruiterPage.jsx
│           ├── Shell.jsx
│           ├── Skeleton.jsx
│           ├── TerminatedPage.jsx
│           ├── VoiceAnswerControls.jsx
│           ├── SessionDetailModal.jsx
│           ├── SessionReplay.jsx
│           ├── CompareModal.jsx
│           └── AdminSessionModal.jsx
├── shared/
│   ├── company_profiles.json           # 20+ company round definitions
│   ├── coding_questions.json           # Coding challenge bank
│   ├── technical_questions.json        # Technical Q&A bank
│   ├── hr_questions.json               # HR / behavioural Q&A bank
│   └── custom_questions/               # Admin-uploaded custom questions
├── docker-compose.yml                  # PostgreSQL + Backend + Nginx
├── Dockerfile                          # Multi-stage: Node build → Python runtime
├── nginx.conf                          # Reverse proxy + WebSocket support
├── pyproject.toml
├── playwright.config.js                # E2E test config
└── .env.example                        # All environment variables
```

---

## Supported Companies

| Type | Companies |
|------|-----------|
| **Product-based** | Google, Microsoft, Amazon, Adobe, Oracle, Salesforce, Atlassian, NVIDIA |
| **Service-based** | TCS, Infosys, Wipro, HCLTech, Tech Mahindra, Cognizant, Capgemini, LTIMindtree |
| **Hybrid** | Accenture, IBM |

Each company has its own round sequence defined in `shared/company_profiles.json`. When multiple companies are selected, rounds are merged and de-duplicated.

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL (for production) or SQLite (for development)

### Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your API keys (see Environment Variables section)

uvicorn app.main:app --reload
```

The API is now available at `http://127.0.0.1:8000`. Interactive docs at `/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at `http://localhost:5173` by default.

### Docker (Production)

```bash
# Build frontend
cd frontend && npm run build && cd ..

# Start all services
docker-compose up -d
```

This starts PostgreSQL, the FastAPI backend, and an Nginx reverse proxy.

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

### Required

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:postgres@localhost:5432/ai_interview` |
| `OPENAI_API_KEY` | OpenAI API key (`sk-proj-...`) — the sole LLM provider powering Obi | — |
| `OPENAI_MODEL` | Luna model slug (Obi's reasoning brain) | `gpt-5.6-luna` |
| `JWT_SECRET` | JWT signing secret (auto-generated if blank) | — |

### AI Interviewer — LLM

| Variable | Description | Default |
|----------|-------------|---------|
| `AI_INTERVIEWER_MAX_QUESTIONS` | Max questions per interview | `12` |
| `AI_INTERVIEWER_TEMPERATURE` | LLM temperature | `0.7` |
| `AI_INTERVIEWER_SESSION_TTL_HOURS` | Session expiry in hours | `4` |

### AI Interviewer — Voice Pipeline

| Variable | Description | Default |
|----------|-------------|---------|
| `DEEPGRAM_API_KEY` | Deepgram Nova-3 STT (primary) | — |
| `GROQ_API_KEY` | Groq Whisper STT (fallback) | — |
| `ELEVENLABS_API_KEY` | ElevenLabs Turbo v2.5 TTS (primary) | — |
| `ELEVENLABS_VOICE_ID` | ElevenLabs voice ID | `21m00Tcm4TlvDq8ikWAM` (Rachel) |
| `OPENAI_API_KEY` | OpenAI TTS/STT (fallback) | — |

### Optional Services

| Variable | Description | Default |
|----------|-------------|---------|
| `JUDGE0_API_KEY` | Judge0 code execution API (RapidAPI) | — |
| `SMTP_HOST` / `SMTP_PORT` | Email OTP delivery | `smtp.gmail.com:587` |
| `SMTP_USER` / `SMTP_PASSWORD` | SMTP credentials | — |

### CORS & Security

| Variable | Description | Default |
|----------|-------------|---------|
| `ALLOWED_ORIGINS` | Comma-separated CORS origins | `http://localhost:5173` |
| `OTP_TTL_SECONDS` | OTP expiry time | `300` |
| `CODE_RATE_LIMIT` | Code execution rate limit | `20` per `600s` |

---

## API Reference

All endpoints are served by FastAPI at `http://127.0.0.1:8000`. Interactive docs at `/docs`.

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/auth/captcha` | — | Get a CAPTCHA challenge token |
| `POST` | `/auth/send-otp` | — | Send a 6-digit OTP to an email address |
| `POST` | `/auth/verify` | — | Verify OTP + CAPTCHA |
| `POST` | `/auth/register` | — | Register a new account (returns JWT) |
| `POST` | `/auth/login` | — | Log in (returns JWT + user info) |
| `POST` | `/auth/check-email` | — | Check whether an email is registered |
| `POST` | `/auth/forgot-password` | — | Send password reset token |
| `POST` | `/auth/reset-password` | — | Reset password with token |

### Session & Rounds

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/upload-resume` | Bearer | Upload PDF/TXT resume |
| `GET`  | `/companies` | — | List all company profiles |
| `POST` | `/select-company` | Bearer | Attach companies to session |
| `POST` | `/start-round` | Bearer | Mark a round as started |
| `GET`  | `/rounds/{company}` | — | Fetch round definitions |
| `GET`  | `/questions/{round_type}` | — | Fetch static question bank |
| `POST` | `/ai/questions` | Bearer | Generate AI questions |
| `POST` | `/submit-answer` | Bearer | Submit answer for aptitude/technical/HR |
| `POST` | `/submit-code` | Bearer | Save a coding submission |
| `POST` | `/run-code` | Bearer | Execute code via Judge0 |
| `POST` | `/ai/feedback` | Bearer | Generate AI feedback |
| `GET`  | `/report` | Bearer | Generate performance report |

### AI Interviewer (LangGraph)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/ai-interview/start` | Bearer | Initialize a new AI interview session |
| `GET`  | `/ai-interview/{id}/state` | Bearer | Get current session state |
| `GET`  | `/ai-interview/{id}/report` | Bearer | Get final interview report |
| `WS`   | `/ai-interview/ws` | Token | Text-based interview WebSocket |
| `WS`   | `/ai-interview/ws/voice` | Token | Voice + code interview WebSocket |

### Candidate Dashboard

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/user/sessions` | Bearer | List all user sessions |
| `GET`  | `/user/sessions/{id}` | Bearer | Session detail + proctoring |
| `GET`  | `/user/stats` | Bearer | Aggregate stats and trends |

### Recruiter / Admin

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/admin/candidates` | Recruiter | List all candidates |
| `GET`  | `/admin/candidates/{email}` | Recruiter | Candidate profile + sessions |
| `GET`  | `/admin/sessions` | Recruiter | List all sessions |
| `GET`  | `/admin/sessions/{id}` | Recruiter | Full report + proctoring |
| `GET`  | `/admin/sessions/{id}/proctoring` | Recruiter | Proctoring logs only |
| `GET`  | `/admin/sessions/{id}/timeline` | Recruiter | Session replay timeline |
| `GET`  | `/admin/stats` | Recruiter | Platform-wide stats |
| `POST` | `/admin/compare` | Recruiter | Compare multiple sessions |
| `POST` | `/admin/update-role` | Admin | Update user role |
| `POST` | `/admin/upload-questions` | Admin | Upload custom questions |

### Proctoring

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/proctoring/violation` | Bearer | Log a proctoring violation |
| `POST` | `/proctoring/snapshot` | Bearer | Store a webcam snapshot |
| `GET`  | `/proctoring/report` | Bearer | Retrieve proctoring logs |

### Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/health` | — | Application health check |
| `GET`  | `/health/smtp` | Admin | SMTP configuration status |

---

## AI Interviewer System (LangGraph)

The AI Interviewer ("Obi") is a LangGraph-powered autonomous interviewer that conducts structured, multi-stage technical interviews.

### Pipeline Architecture

```
START
  │
  ▼
resume_analyzer ──────────────────────────────────┐
  │                                                │ (on error)
  ▼                                                ▼
interview_planner                              error_node
  │
  ▼
opening
  │
  ▼
┌─────────────────────────────────────────────────┐
│             MAIN INTERVIEW LOOP                 │
│                                                 │
│  question_generator ◄─────────────────────┐    │
│       │                                   │    │
│       ▼                                   │    │
│  [WAIT FOR ANSWER] ←─ WebSocket           │    │
│       │                                   │    │
│       ▼                                   │    │
│  answer_analyzer                          │    │
│       │                                   │    │
│       ▼                                   │    │
│  route_after_analysis ──► follow_up_gen ──┘    │
│       │                                        │
│       ▼ (no follow-up)                         │
│  stage_advance ──────────────────────────────► │
│       │ (continue)                             │
│       └───────────────────────────────────────►│
│                   (loop)                       │
└─────────────────────────────────────────────────┘
  │ (should_end == True)
  ▼
closing
  │
  ▼
scoring
  │
  ▼
report_generator
  │
  ▼
END
```

### Node Descriptions

| Node | Purpose | LLM Call |
|------|---------|----------|
| `resume_analyzer_node` | Parses resume, extracts skills, projects, red flags, and interview intelligence | LLM (structured JSON) |
| `interview_planner_node` | Creates multi-stage interview roadmap (warmup → technical → problem solving → behavioral) | LLM (structured JSON) |
| `opening_node` | Generates warm opening message with self-introduction | LLM (structured JSON) |
| `question_generator_node` | Generates next question based on stage, memory, previous evaluation, and resume | LLM (structured JSON) |
| `answer_analyzer_node` | Scores answer on 6 dimensions (technical, depth, clarity, confidence, completeness, communication) | LLM (structured JSON) |
| `follow_up_generator_node` | Generates targeted follow-up for shallow/vague answers with escalation levels 1-3 | LLM (structured JSON) |
| `stage_advance_node` | Checks if stage questions are exhausted, advances to next stage with transition message | LLM (structured JSON) |
| `scoring_node` | Aggregates all evaluations into weighted FinalScores | Pure computation |
| `report_generator_node` | Generates comprehensive hiring report with strengths, weaknesses, rationale | LLM (structured JSON) |
| `closing_node` | Generates professional closing message | LLM (structured JSON) |

### State Schema (`state.py`)

The interview state flows through all nodes as a `TypedDict` with these major sections:

- **Identity** — session_id, candidate_email, role, company
- **Resume Data** — raw text, parsed data, full `ResumeAnalysis`
- **Interview Plan** — stages, focus areas, strategies, `InterviewPlan`
- **Conversation** — questions history, answers history, evaluations, transcript
- **Current Turn** — current question, answer, evaluation, code snapshot
- **Memory** — topics covered/pending, strengths, weaknesses, unresolved claims
- **Timing** — start time, last activity, question start time
- **Control Flow** — phase, questions asked, max questions, should_end
- **Final Output** — `FinalReport` with scores and hiring recommendation
- **Voice Pipeline** — audio chunk buffer, TTS audio response

### Memory System (`memory.py`)

- Tracks topics covered vs. pending across all stages
- Maintains candidate strengths/weaknesses from evaluation signals
- Tracks unresolved claims (resume claims needing verification)
- Maps per-topic depth levels
- Generates compressed conversation context for long interviews
- Provides summary snapshots for LLM prompts

---

## Live Coding Integration

The Live Coding feature allows candidates to write code in real-time during the AI interview. Obi evaluates both the spoken answer AND the code simultaneously.

### How It Works

1. **Tab System** — The interview room has a toggleable Chat/Code tab bar. The candidate can switch between reading Obi's messages and writing code.
2. **Language Selection** — Python, JavaScript, Java, and C++ are supported. The language selector updates the CodeMirror editor's syntax highlighting.
3. **Code Submission** — When the candidate finishes speaking (releases the hold-to-talk button), the current code snapshot is bundled with the audio and sent to the backend:
   ```json
   {
     "type": "audio_end",
     "code": "def solution(nums):\n    return sorted(nums)",
     "language": "python"
   }
   ```
4. **Backend Processing** — The WebSocket handler extracts the code and passes it to `InterviewGraphRunner.process_answer()`, which stores it in the `InterviewState`.
5. **LLM Evaluation** — The `answer_analyzer_node` and `follow_up_generator_node` receive the code snapshot and evaluate it alongside the spoken answer.
6. **Intelligent Follow-ups** — Obi can reference specific lines of code in follow-up questions (e.g., "I see you used a nested loop on line 12, what is the time complexity of that?").
7. **Report Inclusion** — All code snapshots are included in the final interview report for comprehensive evaluation.

### Frontend Components

- **`AIInterviewer.jsx`** — Main interview component with tab UI, CodeEditor integration, and code state management
- **`CodeEditor.jsx`** — CodeMirror 6-based editor with dark theme, syntax highlighting, bracket matching, autocomplete, and fold gutters

### Backend Files

- **`router.py`** — Extracts `code` from WebSocket messages, passes to `process_answer()`
- **`state.py`** — `current_code_snapshot` in `InterviewState`, `code_snapshot` in `AnswerRecord`
- **`graph.py`** — `process_answer(answer_text, code_snapshot)` stores code in state
- **`nodes.py`** — `answer_analyzer_node` and `follow_up_generator_node` format code into prompts
- **`prompts.py`** — Updated prompts include code context for evaluation

### Code Evaluation Principles

When code is provided, Obi evaluates:
- **Correctness** — Does the code solve the stated problem?
- **Consistency** — Does the code match what the candidate described verbally?
- **Efficiency** — Time/space complexity of the implementation
- **Readability** — Naming conventions, structure, error handling
- **Depth signals** — Does the code demonstrate claimed expertise level?
- **Red flags** — Copy-paste patterns, syntax errors, fundamental misunderstandings

---

## Voice Pipeline

The voice pipeline enables real-time voice interviews with sub-1.5s end-to-end latency.

### STT (Speech-to-Text)

| Provider | Model | Priority | Notes |
|----------|-------|----------|-------|
| Deepgram | Nova-3 | Primary | REST batch transcription, highest accuracy |
| Groq | Whisper | Fallback | Faster than OpenAI Whisper |
| OpenAI | Whisper | Fallback | General-purpose fallback |

### TTS (Text-to-Speech)

| Provider | Model | Priority | Latency |
|----------|-------|----------|---------|
| ElevenLabs | Turbo v2.5 | Primary | ~400ms |
| OpenAI | tts-1 (alloy) | Fallback | ~600ms |

### Voice Interview Flow

```
Candidate speaks → MediaRecorder (WebM/opus)
  → Binary audio sent via WebSocket
  → Server: Deepgram STT → text transcript
  → Server: InterviewGraphRunner.process_answer(transcript, code)
  → Server: OpenRouter LLM generates response
  → Server: ElevenLabs TTS → audio bytes
  → Binary TTS audio sent back to client
  → Web Audio API plays response
```

---

## Proctoring System

The proctoring module runs entirely in the browser and syncs events to the backend.

### Monitored Behaviours

| Violation | Penalty | Detection |
|-----------|---------|-----------|
| Tab switch | -10 pts | `visibilitychange` event |
| Fullscreen exit | -10 pts | `fullscreenchange` event |
| Screen share stopped | -15 pts | Screen share stream ended |
| No face / face missing | -15 pts | face-api.js face detection |
| Multiple faces detected | -20 pts | face-api.js face count |
| Copy / Paste | -15 pts | `copy`/`paste` events |
| DevTools opened | -20 pts | DevTools detection heuristic |
| Right click | 0 pts (logged) | `contextmenu` event |
| Restricted shortcut | 0 pts (logged) | Keyboard shortcut detection |

The integrity score starts at **100**. Sessions with excessive violations are flagged.

---

## Authentication & Roles

- **JWT tokens** — Issued on login/register, expire after 24 hours.
- **Protected endpoints** — Require `Authorization: Bearer <token>` header.
- **Roles**: `candidate` (default), `recruiter`, `admin`.
- **First registered user** automatically becomes `admin`.
- **Password policy** — Minimum 8 characters, must include uppercase letter and digit. Hashed with PBKDF2-HMAC-SHA256 (120,000 iterations).
- **OTP verification** — Optional email-based 6-digit OTP with CAPTCHA. In development mode, the OTP is returned in the response for testing.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend Framework** | Python 3.12, FastAPI 0.115, Uvicorn |
| **Frontend Framework** | React 18, Vite 6, React Router DOM 6 |
| **Styling** | Tailwind CSS 3.4, Custom CSS (dark theme) |
| **Code Editor** | CodeMirror 6 (Python, JS, Java, C++ support) |
| **AI/LLM** | OpenAI (single provider; Luna via `OPENAI_MODEL`, default `gpt-5.6-luna`) |
| **Voice — STT** | Deepgram Nova-3, Groq Whisper, OpenAI Whisper |
| **Voice — TTS** | ElevenLabs Turbo v2.5, OpenAI TTS |
| **Orchestration** | LangGraph 0.2 (10-node state graph) |
| **Database** | PostgreSQL (production), SQLite (dev fallback) |
| **Code Execution** | Judge0 CE (RapidAPI) with heuristic fallback |
| **Proctoring** | face-api.js, TensorFlow.js (COCO-SSD) |
| **Charts** | Recharts 2.15 |
| **PDF Export** | jsPDF 4.2 |
| **Math Rendering** | KaTeX 0.17 |
| **Icons** | Lucide React |
| **Testing** | Vitest 2.1, Playwright 1.62, pytest 8.3 |
| **Linting** | ESLint 9, Ruff 0.8, Prettier 3 |
| **Deployment** | Docker, Nginx, Docker Compose |

---

## Deployment

### Docker Compose (Recommended)

```bash
# 1. Build the frontend
cd frontend && npm run build && cd ..

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Start services
docker-compose up -d
```

**Services:**
- **db** — PostgreSQL 16 Alpine on port 5432
- **backend** — FastAPI on port 8000
- **frontend** — Nginx serving static build on port 80

### Manual Deployment

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2

# Frontend
cd frontend
npm install
npm run build
# Serve dist/ with any static file server
```

### Nginx Configuration

The included `nginx.conf` handles:
- Static asset caching (1 year, immutable)
- API proxy to backend (with WebSocket upgrade support)
- SPA fallback (all routes → index.html)
- Security headers (CSP, X-Frame-Options, HSTS)
- Gzip compression

---

## Development Notes

- **API Keys (Optional)** — The platform supports `OPENAI_API_KEY` (Luna, default `gpt-5.6-luna`) for dynamic AI questions/feedback and `JUDGE0_API_KEY` for real code execution. Without these, the system falls back to a deterministic offline mock LLM and heuristic code validation.
- **JWT Secret** — Set `JWT_SECRET` in `.env` for production. If blank, a random secret is auto-generated and persisted to `backend/.jwt_secret`.
- **Database** — Users, sessions, OTPs, CAPTCHAs, and proctoring logs are stored in PostgreSQL (or SQLite in dev). Restarting does not clear data.
- **Aptitude Bank** — Run `python backend/scripts/build_aptitude_bank.py` to regenerate the aptitude question bank.
- **CORS** — Default allows `localhost:5173`. Restrict before public deployment.
- **Two Interview Systems** — The legacy `LiveInterview.jsx` (simple chat interviewer) coexists with the new `AIInterviewer.jsx` (LangGraph pipeline). The `/technical` and `/hr` routes currently use the new AI Interviewer.
- **WebSocket Protocol** — Voice interview uses binary frames for audio and JSON text frames for control messages. The `audio_end` message optionally includes `code` and `language` fields for live coding.
- **Rate Limiting** — DB-backed rate limiting on code execution, AI requests, OTP sends, and admin operations. Works across multiple Uvicorn workers.
