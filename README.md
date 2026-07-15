# AI Interview Coach — Mock Recruitment Platform

A full-stack, end-to-end mock interview platform that simulates real company hiring pipelines with AI-assisted proctoring, resume parsing, multi-round assessments, candidate dashboards, a recruiter portal, and detailed performance reports.

---

## Features

### Core Interview Flow
- **Resume upload & parsing** — Upload a PDF or TXT résumé; the backend extracts name, email, phone, skills, education, experience, projects, and certifications automatically.
- **Company selection** — Choose one or more companies from a catalogue of 20+ firms (product-based, service-based, and hybrid). Interview rounds are merged and de-duplicated across selections.
- **Multi-round assessments**
  - **Aptitude** — Timed MCQ quiz (20 s per question) with per-category scoring.
  - **Coding** — In-browser code editor supporting multiple languages. Code is executed using the Judge0 API (with a seamless fallback to heuristic matching if no API key is provided).
  - **Technical & HR** — Dynamic, AI-generated interview questions powered by Google Gemini, tailored specifically to the candidate's parsed skills and selected company.
- **AI-Powered Evaluation** — Real answer scoring and deep, personalized feedback (strengths, weaknesses, recommendations) powered by Gemini LLM.
- **Performance report** — Per-round scores, overall score, strengths/weaknesses, AI feedback, and PDF export via jsPDF.

### Candidate Dashboard
- **Stats overview** — Total interviews completed, average score, best score, and number of companies practiced.
- **Performance trend chart** — Line chart (Recharts) tracking Overall, Aptitude, Coding, Technical, and HR scores across all past interviews.
- **Interview history** — Sortable table listing every past session with date, company, rounds completed, score, and a drill-down view.
- **Session detail modal** — Click any session to see full report (scores, strengths, weaknesses, AI feedback, proctoring summary).

### Recruiter / Admin Portal
- **Role-based access** — Only users with `recruiter` or `admin` roles can access the portal. The first registered user automatically becomes an admin.
- **Overview tab** — Platform-wide stats: total candidates, total interviews, average platform score, top score.
- **Candidates tab** — Filterable list of all candidates with name, email, interview count, average score, and last active date.
- **Sessions tab** — Filterable list of every interview session across all candidates with company, rounds, score, and actions.
- **Session detail modal** — Full report view for any candidate's session including AI feedback and recommendations.
- **Proctoring viewer** — Integrity score, violation timeline, and webcam snapshot grid for any session.

### Proctoring System
- **AI proctoring** — Face detection (face-api.js), object detection (TensorFlow COCO-SSD), tab-switch detection, fullscreen enforcement, screen-share monitoring, copy-paste & DevTools blocking.
- **Violation tracking** — All events logged to the database with timestamps, penalties, and integrity scores.

### Authentication
- **JWT-based auth** — Email + password registration/login with OTP verification (SMTP) and a server-side CAPTCHA. JWT tokens are issued on login and validated on all protected endpoints.
- **Role system** — Users have roles (`candidate`, `recruiter`, `admin`) stored in SQLite. The first registered user is automatically promoted to `admin`.

---

## Project Structure

```
AI-Interview-Coach-main/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI application (all routes, JWT auth, AI integration)
│   │   └── db.py            # SQLite database operations (users, sessions, OTP, captcha, proctoring)
│   ├── scripts/
│   │   └── build_aptitude_bank.py   # Utility to regenerate the aptitude question bank
│   ├── accounts.json        # Legacy user accounts (auto-migrated to SQLite on startup)
│   ├── app.db               # SQLite database (auto-created)
│   ├── .env.example         # Configuration template (SMTP, Gemini, Judge0, JWT_SECRET)
│   └── requirements.txt
├── frontend/
│   ├── public/
│   │   ├── logo/            # Company logo assets
│   │   └── questions/       # Aptitude question bank (JSON, served statically)
│   └── src/
│       ├── App.jsx           # Single-page application (all views & routing)
│       ├── MathRenderer.jsx  # KaTeX wrapper component
│       ├── main.jsx          # React entry point
│       ├── styles.css        # Global styles (Tailwind + custom)
│       ├── proctoring/
│       │   ├── useAssessmentProctoring.js  # Proctoring hook (face, tab, DevTools…)
│       │   ├── proctoringState.js          # State helpers & violation penalties
│       │   └── ProctoringUI.jsx            # Proctoring overlay components
│       └── utils/
│           └── questionFormat.js           # Question text formatter
└── shared/
    ├── company_profiles.json    # Company round definitions
    ├── coding_questions.json    # Coding challenge bank
    ├── technical_questions.json # Technical Q&A bank
    └── hr_questions.json        # HR / behavioural question bank
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

### Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
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

---

## Email OTP Setup (optional)

OTP verification is optional for development — when SMTP is not configured, the API response includes a `dev_otp` field with the plaintext OTP for testing.

To enable real email delivery:

1. Copy `backend/.env.example` to `backend/.env`.
2. Fill in your SMTP credentials.
3. Restart the backend.

**Gmail example** — use a [Google App Password](https://support.google.com/accounts/answer/185833), not your normal password:

```env
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_16_character_gmail_app_password
SMTP_FROM=your_email@gmail.com
```

Check SMTP configuration status at any time:

```
GET http://127.0.0.1:8000/health/smtp
```

---

## API Reference

All endpoints are served by FastAPI at `http://127.0.0.1:8000`. Interactive docs are available at `/docs`.

### Auth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/auth/captcha` | — | Get a CAPTCHA challenge token |
| `POST` | `/auth/send-otp` | — | Send a 6-digit OTP to an email address |
| `POST` | `/auth/verify` | — | Verify OTP + CAPTCHA (standalone) |
| `POST` | `/auth/register` | — | Register a new account (returns JWT token) |
| `POST` | `/auth/login` | — | Log in (returns JWT token + user info) |
| `POST` | `/auth/check-email` | — | Check whether an email is already registered |

### Session & Rounds

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/upload-resume` | Bearer | Upload a PDF/TXT résumé; links session to authenticated user |
| `GET`  | `/companies` | — | List all available company profiles |
| `POST` | `/select-company` | — | Attach selected companies to a session; returns merged round list |
| `POST` | `/start-round` | — | Mark a round as started in the session |
| `GET`  | `/rounds/{company}` | — | Fetch round definitions for a specific company |
| `GET`  | `/questions/{round_type}` | — | Fetch static question bank (fallback) |
| `POST` | `/ai/questions` | — | Generate dynamic AI questions tailored to the candidate |
| `POST` | `/submit-answer` | — | Submit an answer for aptitude, technical, or HR questions |
| `POST` | `/submit-code` | — | Save a coding submission |
| `POST` | `/run-code` | — | Run code via Judge0 API (or heuristic simulation fallback) |
| `POST` | `/ai/feedback` | — | Generate personalized AI feedback and scoring |
| `GET`  | `/report` | — | Generate final performance report for a session |

### Candidate Dashboard

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/user/sessions` | Bearer | List all sessions for the authenticated user |
| `GET`  | `/user/sessions/{session_id}` | Bearer | Get full session detail + proctoring for a user's session |
| `GET`  | `/user/stats` | Bearer | Aggregate stats: total interviews, averages, trend data |

### Recruiter / Admin Portal

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET`  | `/admin/candidates` | Recruiter | List all candidates with interview count and average score |
| `GET`  | `/admin/candidates/{email}` | Recruiter | Get a specific candidate's profile and all sessions |
| `GET`  | `/admin/sessions` | Recruiter | List all sessions across all candidates |
| `GET`  | `/admin/sessions/{session_id}` | Recruiter | Get full report + proctoring for any session |
| `GET`  | `/admin/sessions/{session_id}/proctoring` | Recruiter | Get proctoring logs only |
| `GET`  | `/admin/stats` | Recruiter | Platform-wide aggregate stats |

### Proctoring

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/proctoring/violation` | — | Log a proctoring violation event |
| `POST` | `/proctoring/snapshot` | — | Store a webcam snapshot |
| `GET`  | `/proctoring/report` | — | Retrieve the proctoring log for a session |

---

## Proctoring System

The proctoring module runs entirely in the browser and syncs events to the backend.

**Monitored behaviours & integrity score penalties:**

| Violation | Penalty |
|-----------|---------|
| Tab switch | −10 pts |
| Fullscreen exit | −10 pts |
| Screen share stopped | −15 pts |
| No face / face missing | −15 pts |
| Multiple faces detected | −20 pts |
| Copy / Paste | −15 pts |
| DevTools opened | −20 pts |
| Right click | 0 pts (logged only) |
| Restricted shortcut | 0 pts (logged only) |

The integrity score starts at **100**. Sessions with excessive violations are flagged as compromised.

---

## Database Schema

All data is stored in a single SQLite database (`backend/app.db`).

| Table | Purpose |
|-------|---------|
| `users` | User accounts with email, password hash, role (`candidate`/`recruiter`/`admin`) |
| `sessions` | Interview sessions linked to users via `user_id`; full state stored as JSON |
| `otp_state` | Pending OTP codes with TTL and attempt tracking |
| `captcha_state` | CAPTCHA challenges with TTL |
| `proctoring_logs` | Proctoring violations, snapshots, and integrity scores per session |

---

## Auth & Roles

- **JWT tokens** are issued on login/register and expire after 24 hours.
- Protected endpoints require `Authorization: Bearer <token>` header.
- **Roles**: `candidate` (default), `recruiter`, `admin`.
- The **first registered user** automatically receives the `admin` role.
- To promote a user to recruiter, update their role directly in the SQLite database.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python, FastAPI, Uvicorn, PyMuPDF, PyJWT, python-dotenv, Pydantic |
| **Frontend** | React 18, Vite, Tailwind CSS, React Router DOM, Recharts |
| **Proctoring** | face-api.js, TensorFlow.js (COCO-SSD) |
| **Report export** | jsPDF |
| **Math rendering** | KaTeX |
| **Icons** | Lucide React |
| **Database** | SQLite (via Python `sqlite3`) |
| **AI/LLM** | Google Gemini 1.5 Flash |

---

## Development Notes

- **API Keys (Optional)** — The platform supports `GEMINI_API_KEY` for dynamic AI questions/feedback and `JUDGE0_API_KEY` for real code execution. If these are not provided in `backend/.env`, the system gracefully falls back to static JSON questions and heuristic code validation.
- **JWT Secret** — Set `JWT_SECRET` in `backend/.env` for production. If not provided, a random secret is generated on startup (tokens will not survive restarts).
- **SQLite Persistence** — Users, sessions, OTPs, CAPTCHAs, and proctoring logs are stored persistently in a local SQLite database (`backend/app.db`). Restarting the backend will **not** clear data.
- **accounts.json Migration** — Legacy user accounts in `accounts.json` are automatically migrated to the SQLite `users` table on startup.
- **Aptitude bank** — Run `backend/scripts/build_aptitude_bank.py` to regenerate the aptitude question JSON served from `frontend/public/questions/aptitude.json`.
- **CORS** — The backend currently allows all origins. Restrict this before any public deployment.
