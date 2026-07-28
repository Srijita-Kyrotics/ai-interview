"""
AI Interviewer Package
======================
Production-grade LangGraph-powered AI interviewer agent.

Modules:
  state       - InterviewState schema (TypedDict)
  nodes       - All LangGraph node implementations
  graph       - LangGraph graph assembly & compilation
  prompts     - All system / node-level prompt templates
  memory      - Interview memory manager
  voice       - Voice pipeline (STT/TTS bridge)
  report      - Final report generator
  router      - FastAPI router (REST + WebSocket)
"""
