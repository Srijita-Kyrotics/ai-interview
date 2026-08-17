# AI Interview Coach — Autonomous Mock Recruitment & AI Interview Platform

A full-stack, enterprise-grade AI interview and mock recruitment platform powered by **LangGraph**, **FastAPI**, **React 18**, **PostgreSQL**, **Redis**, and **Docker**. 

Features an autonomous voice & code AI interviewer (**"Jack"**), real-time browser proctoring, resume intelligence, multi-round company assessment pipelines, candidate analytics, recruiter monitoring tools, and automated hiring report generation.

---

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Project Structure](#project-structure)
- [AI Interviewer System (LangGraph)](#ai-interviewer-system-langgraph)
- [Voice & Live Code Pipeline](#voice--live-code-pipeline)
- [Docker Architecture & Services](#docker-architecture--services)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [API Reference](#api-reference)
- [Proctoring System](#proctoring-system)
- [Testing & Quality Assurance](#testing--quality-assurance)
- [Tech Stack](#tech-stack)

---

## Features

### 🎙️ Standalone AI Interviewer ("Jack")
- **Autonomous Technical Interviewer** — Jack conducts multi-turn, role-tailored technical and behavioral interviews using a structured 10-node **LangGraph** engine.
- **Dynamic Role Selection** — Select candidate target roles: Full-Stack Engineer, Frontend, Backend, AI/ML Engineer, DevOps, Data Engineer, or Product Manager.
- **Root App Entry & Instant Link Sharing** — Jack operates as the standalone application entry on `/` (as well as direct `/interview` and `/technical` routes) with automatic guest authentication for friction-free candidate onboarding.
- **Integrated Top-Right Proctoring** — Real-time camera feeds and integrity scores pinned to the header throughout the interview session.

### ⚡ Voice & Live Coding Pipeline
- **Hold-to-Talk Voice Stream** — Real-time Speech-to-Text (STT) via **Deepgram Nova-3** (with Groq Whisper & OpenAI Whisper fallbacks) and natural Text-to-Speech (TTS) via **ElevenLabs Turbo v2.5** (Rachel / Male voice options).
- **CodeMirror 6 Live Code Runner** — Embedded syntax-highlighted editor supporting Python, JavaScript, C++, and Java. Spoken answers and code snapshots are evaluated simultaneously by the AI interviewer.
- **Dual Code Execution** — Fast isolated local code execution engine with Judge0 API integration.

### 🏢 Full Recruitment Pipeline & Company Catalogue
- **Resume Intelligence** — Upload PDF/TXT resumes; the system extracts skills, work experience, projects, education, and red flags automatically.
- **20+ Top Tech Companies** — Select target companies (Google, Microsoft, Amazon, TCS, Infosys, Wipro, Accenture, etc.) with automated round merging and de-duplication.
- **Multi-Round Assessments** — Aptitude (timed MCQ with category analytics), Coding (Judge0 / local runner), Technical, and HR interviews.

### 📊 Candidate Dashboard & Recruiter Portal
- **Candidate Analytics** — Historical interview timeline, performance trends (Recharts), aggregate scores, and downloadable PDF performance reports (jsPDF).
- **Recruiter & Admin Tools** — Platform-wide metrics, candidate search, session replay timelines, side-by-side session comparisons, and proctoring violation logs.

---

## Architecture Overview

```
                                  ┌──────────────────────────────────────────────────┐
                                  │                FRONTEND (React 18 + Vite)        │
                                  │                                                  │
                                  │   Jack Standalone Entry  │  Company Selector    │
                                  │   CodeMirror 6 Editor    │  Recharts Analytics  │
                                  │   Proctoring (Face/COCO) │  jsPDF Reports       │
                                  └────────────────────────┬─────────────────────────┘
                                                           │
                                             WebSocket / REST HTTP APIs
                                                           │
                                                           ▼
                                  ┌──────────────────────────────────────────────────┐
                                  │               REVERSE PROXY (Nginx)              │
                                  └────────────────────────┬─────────────────────────┘
                                                           │
                                                           ▼
                                  ┌──────────────────────────────────────────────────┐
                                  │               BACKEND (FastAPI / Python)         │
                                  │                                                  │
                                  │   ┌──────────────────────────────────────────┐   │
                                  │   │        AI Interviewer Package            │   │
                                  │   │  - 10-Node LangGraph State Machine       │   │
                                  │   │  - STT (Deepgram/Groq) + TTS (ElevenLabs)│   │
                                  │   │  - Multi-Provider LLM Fallbacks          │   │
                                  │   └────────────────────┬─────────────────────┘   │
                                  │                        │                         │
                                  │   ┌────────────────────┴─────────────────────┐   │
                                  │   │         Platform & Auth Services         │   │
                                  │   │  JWT Auth │ Resume Parser │ Code Executor│   │
                                  │   └──────────────────────────────────────────┘   │
                                  └───────────────┬──────────────────────┬───────────┘
                                                  │                      │
                                                  ▼                      ▼
                                     ┌──────────────────────┐  ┌───────────────────┐
                                     │  PostgreSQL 16 DB    │  │   Redis 7 Cache   │
                                     │  (Users/Sessions/    │  │  (State Store &   │
                                     │   Proctoring Logs)   │  │   Rate Limiting)  │
                                     └──────────────────────┘  └───────────────────┘
```

---

## Project Structure

```
ai-interview/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI application, route mounting, CORS, middleware
│   │   ├── config.py                  # Pydantic BaseSettings environment variables
│   │   ├── db.py                      # PostgreSQL connection pool & SQLAlchemy/asyncpg schema
│   │   ├── helpers.py                 # JWT token management & password hashing
│   │   ├── auth_routes.py             # User registration, login, guest auth, OTP, CAPTCHA
│   │   ├── auth_service.py            # Authentication business logic & security checks
│   │   ├── session_routes.py          # Interview sessions, resume upload, round management
│   │   ├── resume_parser.py           # PDF & text resume extraction engine
│   │   ├── code_executor.py           # Isolated local Python/JS code runner & Judge0 client
│   │   └── ai_interviewer/            # Autonomous AI Interviewer Package
│   │       ├── graph.py               # 10-Node LangGraph state graph assembly & async runner
│   │       ├── nodes.py               # 10 graph node functions (analyzer, planner, analyzer, etc.)
│   │       ├── state.py               # TypedDict interview state schema
│   │       ├── state_store.py         # Redis-backed persistent session state store
│   │       ├── llm_providers.py       # Multi-provider LLM handler (Gemini 2.5, OpenRouter/GPT-5.6)
│   │       ├── prompts.py             # Dynamic prompt templates for Jack AI persona
│   │       ├── router.py              # WebSocket (/ai-interview/ws/voice) & REST endpoints
│   │       ├── voice.py               # STT/TTS audio streaming & buffer processing
│   │       ├── memory.py              # Interview memory manager (topics, depth, claim verification)
│   │       ├── coding_judge.py        # Code snapshot evaluation & criteria matching
│   │       ├── evidence_graph.py      # Candidate claim & response evidence tracker
│   │       └── communication_analyzer.py # Verbal communication & clarity scoring
│   ├── alembic/                       # Database schema migration scripts
│   ├── scripts/                       # Question bank generation & test data utilities
│   ├── tests/                         # Pytest automated test suite (LLM, parser, code runner, judge)
│   └── requirements.txt               # Backend Python dependencies
├── frontend/
│   ├── src/
│   │   ├── main.jsx                   # React DOM entry point
│   │   ├── App.jsx                    # SPA Routing, standalone Jack entrance, navigation
│   │   ├── api.js                     # Axios HTTP client with JWT interceptors
│   │   ├── styles.css                 # Global CSS design system & Tailwind directives
│   │   ├── components/
│   │   │   ├── AIInterviewer.jsx      # Standalone Jack AI Interviewer room controller
│   │   │   ├── ObiAvatar.jsx          # AI Interviewer avatar component
│   │   │   ├── CodeEditor.jsx         # CodeMirror 6 code editor wrapper
│   │   │   ├── aiInterviewer/
│   │   │   │   ├── StartCard.jsx      # Pre-interview setup, role selection, resume upload
│   │   │   │   ├── CodingPanel.jsx    # Live problem statement, code editor & test runner UI
│   │   │   │   └── parts.jsx          # Live speech bubbles, status indicators, score gauges
│   │   │   ├── DashboardPage.jsx      # Candidate dashboard with historical trends
│   │   │   ├── RecruiterPage.jsx      # Recruiter portal, candidate search & session replay
│   │   │   ├── ReportPage.jsx         # Detailed PDF exportable performance breakdown
│   │   │   └── AuthPage.jsx           # Login, registration, OTP & CAPTCHA page
│   │   ├── proctoring/                # Face-api.js & COCO-SSD browser proctoring
│   │   └── __tests__/                 # Vitest frontend unit tests
│   ├── e2e/                           # Playwright end-to-end interview flow tests
│   ├── package.json                   # Frontend dependencies & scripts
│   └── vite.config.js                 # Vite bundler & dev proxy configuration
├── shared/                            # Centralized company profiles & question banks
├── docker-compose.yml                 # Production multi-container Docker orchestration
├── docker-compose.dev.yml             # Hot-reloading development Docker stack
├── Dockerfile                         # Multi-stage build (Node 20 -> Python 3.12)
├── nginx.conf                         # Reverse proxy, static asset server & WebSocket upgrades
└── README.md                          # Platform documentation
```

---

## AI Interviewer System (LangGraph)

The AI Interviewer **"Jack"** is driven by a 10-node autonomous **LangGraph** execution graph:

```
[START] ──► resume_analyzer ──► interview_planner ──► opening
                                                         │
    ┌────────────────────────────────────────────────────┘
    ▼
question_generator ◄──────────────────┐
    │                                 │
 [Candidate Answer + Code]            │
    │                                 │
    ▼                                 │
answer_analyzer                       │
    │                                 │
    ├──► (needs follow-up) ──► follow_up_generator ──┘
    │
    └──► stage_advance ───────────────► (next stage) ──┘
             │
      (should_end)
             │
             ▼
          closing ──► scoring ──► report_generator ──► [END]
```

### Node Responsibilities

| Node Name | Function |
| :--- | :--- |
| `resume_analyzer_node` | Analyzes resume text, flags key projects, skills, gaps, and verification points. |
| `interview_planner_node` | Builds a candidate-tailored roadmap across technical & behavioral stages. |
| `opening_node` | Introduces Jack and sets expectations for the candidate session. |
| `question_generator_node` | Generates role-relevant questions dynamically based on state and covered topics. |
| `answer_analyzer_node` | Evaluates spoken response and submitted code across 6 performance dimensions. |
| `follow_up_generator_node` | Probes shallow, incomplete, or ambiguous answers with targeted follow-ups. |
| `stage_advance_node` | Manages stage transitions (Warmup → Technical → Problem Solving → Behavioral). |
| `scoring_node` | Aggregates turn scores into weighted FinalScores. |
| `report_generator_node` | Produces an executive hiring summary, strengths, weaknesses, and recommendations. |
| `closing_node` | Concludes the interview session professionally. |

---

## Voice & Live Code Pipeline

1. **Audio Streaming**: Candidate voice is recorded via WebRTC (`MediaRecorder`) in WebM/Opus format and streamed over WebSockets (`/ai-interview/ws/voice`).
2. **STT Transcription**: Converted to text via Deepgram Nova-3 (or Groq Whisper).
3. **Dual Spoken + Code Evaluation**: Spoken text and current CodeMirror code snapshot are delivered into `InterviewGraphRunner.process_answer()`.
4. **LLM Evaluation**: Jack evaluates code efficiency, syntax correctness, and verbal alignment simultaneously.
5. **TTS Audio Output**: Response text is converted to high-fidelity audio via ElevenLabs Turbo v2.5 (or OpenAI TTS) and streamed back to the browser for playback.

---

## Docker Architecture & Services

The application is fully dockerized with a production multi-stage build and a development override.

| Service | Container Image | Port | Description |
| :--- | :--- | :--- | :--- |
| **frontend** | `nginx:alpine` | `80` | Serves compiled static Vite build & proxies API/WS requests |
| **backend** | `ai-interview-backend` | `8000` | FastAPI app, LangGraph engine, voice & code handlers |
| **db** | `postgres:16-alpine` | `5433` | PostgreSQL database for users, sessions, and proctoring |
| **redis** | `redis:7-alpine` | `6379` | Persistent Redis store for LangGraph session state & rate limits |

---

## Getting Started

### Using Docker (Recommended)

```bash
# 1. Clone repository
git clone https://github.com/Srijita-Kyrotics/ai-interview.git
cd ai-interview

# 2. Configure environment variables
cp .env.example .env

# 3. Build and launch all services
docker compose up -d --build
```
Access the application at **[http://localhost](http://localhost)**.

### Local Development (Without Docker)

#### Backend Setup
```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

#### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```
Access the dev server at **[http://localhost:5173](http://localhost:5173)**.

---

## Environment Variables

Key settings in `.env`:

```env
# Database & Cache
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_interview
REDIS_URL=redis://localhost:6379/0

# LLM Providers (OpenAI / OpenRouter / Gemini)
OPENAI_API_KEY=sk-proj-...
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=openai/gpt-5.6-luna
AI_INTERVIEWER_GEMINI_MODEL=gemini-2.5-flash-lite

# Voice STT / TTS Keys
DEEPGRAM_API_KEY=your_deepgram_api_key
GROQ_API_KEY=your_groq_api_key
ELEVENLABS_API_KEY=your_elevenlabs_api_key

# Code Execution (Judge0)
JUDGE0_API_KEY=your_rapidapi_judge0_key
```

---

## API Reference

### Auth & User Management
- `POST /auth/guest` — Quick guest user authentication for instant interview access.
- `POST /auth/register` — User registration with password hashing.
- `POST /auth/login` — User authentication returning JWT bearer token.

### AI Interviewer (LangGraph)
- `POST /ai-interview/start` — Initialize a new AI interview session with role & resume.
- `GET /ai-interview/{id}/state` — Fetch current interview graph state.
- `GET /ai-interview/{id}/report` — Retrieve final generated interview report.
- `WS /ai-interview/ws/voice` — Real-time binary voice & code submission WebSocket.

### Sessions & Assessment
- `POST /upload-resume` — Parse PDF/TXT resume.
- `POST /run-code` — Execute code via Judge0 or local fallback runner.
- `GET /user/sessions` — Fetch historical candidate sessions and scores.
- `GET /admin/sessions` — Recruiter view of platform candidate sessions.

---

## Proctoring System

The browser-based proctoring suite continuously monitors:
- 👁️ **Face Detection** — `face-api.js` tracks presence and flags multi-face or missing candidate events.
- 📦 **Object Detection** — TensorFlow `coco-ssd` checks for forbidden items (e.g. mobile phones).
- 🖥️ **Tab & Window Focus** — Tracks tab switches (`visibilitychange`) and fullscreen exits.
- ⌨️ **Keyboard & Mouse Rules** — Prevents copy/paste, right-click, and restricted hotkeys.

Integrity penalties are calculated in real-time and recorded in the database alongside session logs.

---

## Testing & Quality Assurance

Run backend pytest suite:
```bash
cd backend
pytest -v
```

Run frontend unit & E2E tests:
```bash
cd frontend
npm run test
npm run e2e
```

---

## Tech Stack

- **Backend**: Python 3.12, FastAPI, LangGraph, Pydantic, SQLAlchemy, Asyncpg, Redis, Uvicorn
- **Frontend**: React 18, Vite 6, React Router DOM 6, CodeMirror 6, Recharts, jsPDF, Lucide Icons
- **AI & Speech**: Deepgram Nova-3, Groq Whisper, ElevenLabs Turbo v2.5, OpenRouter / Gemini LLM
- **Proctoring**: face-api.js, TensorFlow.js (COCO-SSD)
- **Infrastructure**: Docker, Docker Compose, Nginx, PostgreSQL 16, Redis 7
