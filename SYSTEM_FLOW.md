# AI-Interview Platform: System Flow

This document describes how the application works from a candidate opening the site through interview completion and reporting. It is based on the implementation in `frontend/src`, `backend/app`, the Docker configuration, and the shared question banks.

## 1. What the platform contains

The repository provides two related assessment experiences:

1. **Conventional assessment rounds**: aptitude, coding, technical, and HR rounds built from JSON question banks.
2. **The AI interviewer**: a real-time, resume-aware interview conducted by **Jack**, with text/voice input, an adaptive LangGraph interview engine, live coding, proctoring, persistence, and a final report.

The frontend is React/Vite. The backend is FastAPI. PostgreSQL holds accounts and platform sessions; Redis holds live AI-interview state and timeline data. The AI interview uses an OpenAI-compatible LLM endpoint, with a deterministic mock provider available for local development/tests when no usable API key is configured.

```text
Browser (React/Vite)
  | REST + WebSocket
  v
FastAPI
  |- Auth, platform sessions, question banks, reports
  |- AI-interview REST and WebSocket router
  |- LangGraph-style interview runner and nodes
  |- Resume parser, code runner/judge, voice adapters
  |- PostgreSQL: users + durable platform/session records
  `- Redis: active interview state, metadata, locks, timeline
       `- OpenAI-compatible LLM / optional Deepgram, Groq, ElevenLabs or OpenAI speech APIs
```

## 2. Startup and deployment topology

### Local development

`docker-compose.yml` starts the following services:

| Service | Responsibility | Host port |
| --- | --- | --- |
| `frontend` | Nginx serving a built frontend and proxying `/api` + WebSockets | `80` |
| `frontend-dev` | Vite development server with hot reload | `5174` |
| `backend` | FastAPI/Uvicorn | `8001` |
| `db` | PostgreSQL | `5433` |
| `redis` | persistent AI interview state/cache | `6380` |

The development override bind-mounts `backend/` and `frontend/`, runs Uvicorn with reload, and has Vite proxy `/api` and WebSocket traffic to the backend container. The normal browser entry point during development is `http://localhost:5174`.

### Backend boot

`backend/app/main.py` creates the FastAPI application and, at startup:

1. Initializes database tables and migrates legacy account data if required.
2. Cleans expired cache and stale data.
3. Connects to Redis through `InterviewStateStore`; if Redis cannot be reached, it uses a process-local in-memory fallback.
4. Registers three routers:
   - `auth_routes.py`: authentication and account operations.
   - `session_routes.py`: conventional rounds, data sets, platform sessions, reports, and recruiter operations.
   - `ai_interviewer/router.py` under the `/ai-interview` prefix.
5. Adds CORS, security headers, request observability, `/health`, `/health/detailed`, and `/metrics`.

### Important production constraint

Redis is required for reliable production AI interviews. The fallback store is only local to one server process and disappears after restart. The Docker default is one Uvicorn worker so a Render deployment without Redis does not split `/start` and its WebSocket across separate in-memory stores. For resumable sessions and multi-worker scaling, configure `REDIS_URL`.

## 3. Browser application flow

### Authentication and browser state

`frontend/src/App.jsx` restores the signed-in user from `localStorage` (`mockRecruitmentUser`) and validates the JWT shape/expiry. It also retains the candidate's selected company, uploaded resume summary, session ID, rounds, and round statuses in `mockRecruitmentFlow`.

If there is no signed-in user, the app requests `/auth/guest`. This makes direct/standalone interview links usable in development/demo mode. The API wrapper in `frontend/src/api.js` adds `Authorization: Bearer <JWT>` to requests and clears the local user after a `401` response.

### Frontend data loading

After app mount, `App.jsx` loads:

- companies from `GET /companies`,
- aptitude questions from the static `public/questions/aptitude.json`,
- coding, technical, and HR questions from backend question endpoints.

For standard application routes, the `Shell` renders the page chrome and lazy-loads pages such as the dashboard, recruiter portal, report, and round screens. The following paths are special full-screen interview entries: `/`, `/technical`, and `/interview`. They render `AIInterviewer` directly rather than the normal shell.

## 4. Conventional round flow

This path is implemented mostly by `RoundPage.jsx` and `backend/app/session_routes.py`.

```text
Resume → Company selection → Select a round → Receive question set
       → Candidate submits answers/code → Backend saves session state
       → Scores/report/dashboard/recruiter views read persisted data
```

1. A candidate uploads/pastes a resume. The backend extracts PDF text with PyMuPDF when needed and parses sections, skills, experience, projects, education, and contact details in `resume_parser.py`.
2. A platform session is created and saved in PostgreSQL. The session stores resume data, selected companies, answers, code submissions, scores, and round state.
3. Company selection determines which company-specific round configuration and questions are used.
4. `RoundPage` renders timed aptitude/technical/HR questions or a coding problem. Submitted answers are persisted through the session routes.
5. Standard score helpers calculate round scores. `make_report` combines stored round outcomes with feedback into the candidate report.

The conventional code runner uses `execute_local` for local execution. The AI-interview code runner first attempts Judge0 (`execute_code`) and falls back to the local process runner if Judge0 is unavailable.

## 5. Entering the AI interviewer

`AIInterviewer.jsx` owns the live interview room. It receives the platform `sessionId`, JWT, parsed resume, company, coding questions, and proctoring state from `App.jsx`.

The initial card allows the candidate to:

- upload a `.pdf` or `.txt` resume;
- paste resume text;
- select/infer a target role;
- start the interview;
- open direct coding-demo mode.

Role inference compares parsed resume text, skills, titles, and experience against `ROLE_MAPPINGS` in `constants.js`.

### Resume/session creation

There are three entry cases:

| Candidate input | Browser request | Result |
| --- | --- | --- |
| Uploaded PDF/TXT | `POST /ai-interview/upload-resume` multipart upload | Extracted/parsed resume plus a new platform session ID |
| Pasted resume | `POST /ai-interview/create-session` | Parsed resume plus a new platform session ID |
| Existing platform session | no new upload request | Uses the existing session/resume |

When the candidate presses Begin, the client requests microphone permission (optional for typed answers) and camera permission (optional for proctoring). It then calls `POST /ai-interview/start` with the platform session, role, company, maximum question count, and voice preference.

`/start` loads the platform session, builds an `InterviewState` via `make_initial_state`, instantiates `InterviewGraphRunner`, and writes state + metadata to Redis. The response includes a new `interview_session_id` for the live interview.

## 6. AI-interview WebSocket lifecycle

The browser opens:

```text
ws(s)://<host>/api/ai-interview/ws/voice
  ?token=<JWT>
  &interview_session_id=<AI session id>
  &session_id=<platform session id>
  &client_tts=true|false
```

`getWsBase()` chooses `wss` on HTTPS and `ws` on HTTP. The client URI-encodes query values. `client_tts=true` tells the backend that the browser supports Web Speech synthesis, which avoids server TTS latency and duplicate audio.

### Connection initialization

1. The backend accepts the WebSocket and validates the JWT.
2. It restores the runner state from `InterviewStateStore`.
3. For a new interview it sends a quick `session_ready` greeting before the expensive resume/plan/question work completes.
4. It initializes the runner, generates the first question, sends a `question` event, and, when the current stage has a generated coding problem, sends a `coding_problem` event.
5. For a resumed interview it sends `session_restored`, re-sends the current question, and may re-send the active coding problem.

### Server-to-browser messages

| Type | Meaning in the UI |
| --- | --- |
| `session_ready` | Start the greeting and move to the live room. |
| `progress` / `status` | Update the preparation/status text. |
| `question` | Display the next question, set stage/progress, queue speech, and detect coding mode. |
| `transition` | Display/speak a stage-change explanation. |
| `thinking`, `processing`, `stt_result` | Drive busy/transcription/evaluation indicators and transcript entries. |
| `coding_problem` | Populate the statement, examples, tests, and starter code in the IDE. |
| `coding_submission_result` | Display objective coding outcome. |
| `interview_complete` | Switch to completion/report state and invoke `onComplete`. |
| `error` | Surface a recoverable startup/LLM/WebSocket error. |

### Browser-to-server messages

| Type | Content | Processing path |
| --- | --- | --- |
| Binary WebSocket frame | recorded WebM/Opus audio | appended to the server audio buffer |
| `audio_end` | optional browser transcript plus optional code snapshot | transcription, then `runner.process_answer` |
| `answer` | typed text plus optional code snapshot | directly calls `runner.process_answer` |
| `refresh_token` | refreshed JWT | revalidates active connection token |
| `end_voice` | no payload | finalizes interview and returns report |

The client queues browser text-to-speech one utterance at a time. Therefore the greeting completes before the first question is spoken. If browser speech is unavailable, the server streams TTS bytes and the client plays binary chunks serially instead. A typed answer cancels any pending speech, writes the candidate message immediately, then enters the thinking state.

## 7. Voice input path

```text
Microphone
  → MediaRecorder (audio/webm; codecs=opus)
  → browser SpeechRecognition when available
  → WebSocket bytes + audio_end(transcript)
  → Deepgram REST STT, then Groq/OpenAI Whisper fallback if no browser text
  → process_answer(transcript)
```

`AIInterviewer.jsx` records in 250 ms chunks. It also uses the browser's SpeechRecognition API where supported. On stop, it sends the browser transcript immediately if one exists; this reduces latency and avoids requiring a cloud STT key. If no transcript is available, `VoicePipeline.audio_to_text` uses Deepgram first and Whisper-compatible transcription as a fallback. If transcription is empty, the server asks the candidate to repeat instead of advancing the interview.

## 8. The LangGraph interview engine

The central state machine is `InterviewGraphRunner` in `backend/app/ai_interviewer/graph.py`. Its complete mutable state is typed by `InterviewState` in `state.py` and checkpointed after important work.

### Initialization

`runner.initialize()` executes the pre-interview pipeline:

```text
resume_analyzer
  → claim_extractor
  → interview_planner
  → opening
```

- **Resume analyzer** identifies seniority, skills, projects, strengths, likely weaknesses, and useful probe areas.
- **Claim extractor** turns resume claims into items to verify during the interview.
- **Interview planner** creates ordered stages, topics, question targets, and strategy.
- **Opening** produces the interview introduction and initializes the transcript/state.

`generate_first_question()` and `generate_next_question()` call either `question_generator_node` or `system_design_question_generator_node`, based on the active stage/mode.

### Per-answer pipeline

For every typed or transcribed answer, `runner.process_answer()` follows this decision flow:

```text
Candidate answer (+ optional source-code snapshot)
  → record answer / communication metrics / code evolution
  → answer analyzer
  → claim verifier + evidence/contradiction tracking
  → update topic mastery and adaptive difficulty
  ├── shallow/ambiguous answer → follow-up generator
  ├── stage still active       → next question generator
  ├── stage complete           → stage advance / optional replanning
  └── interview complete       → closing → scoring → report generator
```

The main nodes in `nodes.py` are:

| Node | Responsibility |
| --- | --- |
| `answer_analyzer_node` | Scores correctness, depth, reasoning, confidence, and communication; decides whether a follow-up is needed. |
| `follow_up_generator_node` | Creates a focused probe for weak, incomplete, or contradictory answers. |
| `claim_verifier_node` | Links answers to resume claims and updates verification status. |
| `interview_replanner_node` | Revises future focus topics if evidence warrants it. |
| `stage_advance_node` | Completes a stage and selects the next one. |
| `coding_problem_generator_node` | Produces a live-coding problem and test data when the plan enters coding. |
| `system_design_evaluator_node` | Evaluates system-design answers in the dedicated mode. |
| `scoring_node` | Aggregates overall component scores. |
| `report_generator_node` | Produces final findings, recommendation, strengths, weaknesses, and detailed records. |

The graph tracks `questions_asked` (all turns) separately from `main_questions_asked` (top-level questions). `max_questions` limits main questions and `max_turns` is a safety cap that includes follow-ups.

### Model provider behavior

`llm_providers.py` uses an OpenAI-compatible Chat Completions endpoint. The configured model defaults to `gpt-5.6-luna`; `OPENAI_FAST_MODEL` can be used for latency-critical interactive prompts. A shared `httpx.AsyncClient` reuses keep-alive connections. Calls have retry/circuit-breaker protections. In test/local fallback conditions, `MockProvider` returns schema-valid deterministic answers so the flow remains runnable without an API key.

## 9. Live coding flow

When the AI interview enters a coding stage, the backend places an `active_coding_problem` in interview state and sends its public representation over the voice WebSocket. Hidden tests are intentionally removed by `_public_coding_problem` before delivery.

The frontend uses `CodingPanel` and `CodingEditor`/`CodeEditor` (CodeMirror 6):

1. The statement, examples, constraints, visible test cases, and language-specific starter code appear in the workspace.
2. A language switch replaces the editor with that language's starter code.
3. **Run Code**:
   - if visible test cases exist, calls `POST /ai-interview/judge`;
   - otherwise calls `POST /ai-interview/run-code` with optional stdin.
4. **Submit** sends a WebSocket `answer` containing a textual submission marker, source code, and language.
5. `process_answer` records the code snapshot/version, evaluates it with the interview context, and can judge against hidden cases through `coding_judge.py`.

`code_executor.py` prefers Judge0 and falls back to a constrained local subprocess. It limits process time, captured output, and (on POSIX) CPU, memory, file descriptors, and output file size. Local support depends on installed runtimes/compilers; unavailable languages return a clear `missing_runtime` result.

Direct coding-demo mode is separate from the live AI coding stage: it loads a question-bank problem (or Two Sum fallback) directly into the editor and does not require an active interview WebSocket.

## 10. Persistence, resumption, and reporting

### Live interview state

`InterviewStateStore` uses Redis keys such as:

```text
interview:{session_id}:state
interview:{session_id}:meta
interview:{session_id}:timeline
interview:{session_id}:lock
```

It stores the full state JSON, metadata, a chronological event timeline, TTL-based expiry, and a short lock for concurrent operations. Every graph checkpoint updates Redis. `POST /ai-interview/resume` verifies that the platform session owns the requested interview ID, marks it resuming, and allows the browser to reconnect.

### Final persistence

On `should_end` or `end_voice`, `_save_interview_result` copies the AI interview transcript, evaluations, scores, and final report into the related PostgreSQL platform session. It also writes compatible top-level technical and communication scores for existing dashboard/report code.

The client receives `interview_complete`, waits briefly for UI completion, calls the route's `onComplete`, marks the technical round complete locally, and navigates to `/report`.

## 11. Proctoring flow

The browser hook `useAssessmentProctoring` monitors permitted interview behavior, including webcam/face checks, fullscreen, tab changes, and configured integrity signals. It can operate gracefully with no camera, retaining non-camera checks.

It reports events by REST (`POST /ai-interview/{id}/proctoring/event`) and supports a dedicated `ws/proctoring` channel. The backend:

1. writes each event to PostgreSQL proctoring data;
2. records it in the Redis interview timeline;
3. reduces integrity score by severity;
4. sends warnings at configured thresholds;
5. marks the session terminated at zero integrity or after three critical violations.

On termination, the browser stops recording/recognition and closes the interview socket.

## 12. Useful source map

| Area | Primary files |
| --- | --- |
| React routes and application state | `frontend/src/App.jsx`, `frontend/src/api.js` |
| Live interview UI/WebSocket/voice control | `frontend/src/components/AIInterviewer.jsx` |
| Live coding UI | `frontend/src/components/aiInterviewer/CodingPanel.jsx`, `CodingEditor.jsx`, `frontend/src/components/CodeEditor.jsx` |
| Standard assessment rounds | `frontend/src/components/RoundPage.jsx`, `backend/app/session_routes.py` |
| FastAPI bootstrap | `backend/app/main.py`, `backend/app/config.py` |
| AI interview REST/WS protocol | `backend/app/ai_interviewer/router.py` |
| Interview state and runner | `backend/app/ai_interviewer/state.py`, `graph.py` |
| AI nodes/prompts/providers | `backend/app/ai_interviewer/nodes.py`, `prompts.py`, `llm_providers.py` |
| Voice/STT/TTS | `backend/app/ai_interviewer/voice.py` |
| State persistence | `backend/app/ai_interviewer/state_store.py` |
| Code execution and judging | `backend/app/code_executor.py`, `backend/app/ai_interviewer/coding_judge.py` |
| Resume parsing | `backend/app/resume_parser.py` |
| Deployment/local stack | `Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml`, `nginx.conf` |
