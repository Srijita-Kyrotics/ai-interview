import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAssessmentProctoring } from '../proctoring/useAssessmentProctoring';
import { ProctoringModal, ProctoringPanel } from '../proctoring/ProctoringUI';
import { CodeEditor } from './CodeEditor';

// ─────────────────────────────────────────────────────────────────────────────
// AI INTERVIEWER COMPONENT
// Production-grade voice + text interview interface
// ─────────────────────────────────────────────────────────────────────────────

const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// ── Sub-components ────────────────────────────────────────────────────────────

const WaveformVisualizer = ({ isActive, color = '#6366f1' }) => {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const frameRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const bars = 40;
    const barWidth = width / bars - 2;

    const animate = () => {
      ctx.clearRect(0, 0, width, height);
      for (let i = 0; i < bars; i++) {
        const t = frameRef.current / 20 + i * 0.3;
        const amp = isActive
          ? (Math.sin(t) * 0.5 + 0.5) * 0.8 + 0.1
          : 0.05;
        const barH = amp * height;
        const x = i * (barWidth + 2);
        const y = (height - barH) / 2;
        ctx.fillStyle = color;
        ctx.globalAlpha = isActive ? 0.7 + amp * 0.3 : 0.3;
        ctx.beginPath();
        ctx.roundRect(x, y, barWidth, barH, 3);
        ctx.fill();
      }
      frameRef.current++;
      animRef.current = requestAnimationFrame(animate);
    };
    animate();
    return () => cancelAnimationFrame(animRef.current);
  }, [isActive, color]);

  return (
    <canvas
      ref={canvasRef}
      width={200}
      height={48}
      style={{ display: 'block' }}
    />
  );
};


const ScoreGauge = ({ label, score, color }) => {
  const pct = Math.round(score);
  const circumference = 2 * Math.PI * 28;
  const dash = (pct / 100) * circumference;

  return (
    <div className="aii-score-gauge">
      <svg width="72" height="72" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r="28" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="6" />
        <circle
          cx="36" cy="36" r="28" fill="none"
          stroke={color} strokeWidth="6"
          strokeDasharray={`${dash} ${circumference}`}
          strokeLinecap="round"
          transform="rotate(-90 36 36)"
          style={{ transition: 'stroke-dasharray 1s ease' }}
        />
        <text x="36" y="40" textAnchor="middle" fill="white" fontSize="13" fontWeight="700">{pct}</text>
      </svg>
      <span className="aii-score-label">{label}</span>
    </div>
  );
};


const MessageBubble = ({ message }) => {
  const isInterviewer = message.role === 'interviewer';
  return (
    <div className={`aii-bubble ${isInterviewer ? 'aii-bubble--ai' : 'aii-bubble--user'}`}>
      {isInterviewer && (
        <div className="aii-bubble__avatar">
          <span>O</span>
        </div>
      )}
      <div className="aii-bubble__content">
        {message.isFollowUp && (
          <span className="aii-badge aii-badge--followup">↳ Follow-up</span>
        )}
        {message.isTransition && (
          <span className="aii-badge aii-badge--transition">↔ Next Topic</span>
        )}
        <p>{message.text}</p>
        <span className="aii-bubble__time">
          {new Date(message.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
      {!isInterviewer && (
        <div className="aii-bubble__avatar aii-bubble__avatar--user">
          <span>You</span>
        </div>
      )}
    </div>
  );
};


const ThinkingIndicator = () => (
  <div className="aii-thinking">
    <div className="aii-bubble__avatar"><span>O</span></div>
    <div className="aii-thinking__dots">
      <span />
      <span />
      <span />
    </div>
  </div>
);


const ProgressBar = ({ current, total, stages }) => {
  const pct = total > 0 ? Math.min((current / total) * 100, 100) : 0;
  return (
    <div className="aii-progress">
      <div className="aii-progress__bar">
        <div className="aii-progress__fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="aii-progress__info">
        <span>Question {current} of {total}</span>
        {stages?.currentStage && <span className="aii-progress__stage">{stages.currentStage}</span>}
      </div>
    </div>
  );
};


// ── Main Component ──────────────────────────────────────────────────────────

export default function AIInterviewer({ sessionId, token, role, company, onComplete, proctoring, setProctoring }) {
  const navigate = useNavigate();

  // ── State ───────────────────────────────────────────────────────────
  const [phase, setPhase] = useState('idle');
  // idle → initializing → opening → interviewing → completing → completed | error

  const [messages, setMessages] = useState([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  
  // Force voice mode and disable text inputs
  const voiceMode = true; 
  
  const [interviewSessionId, setInterviewSessionId] = useState(null);
  const [progress, setProgress] = useState({ current: 0, total: 12 });
  const [currentStage, setCurrentStage] = useState('');
  const [finalReport, setFinalReport] = useState(null);
  const [error, setError] = useState(null);
  const [latency, setLatency] = useState(null);
  const [resumableSession, setResumableSession] = useState(null); // P2: Resume support
  const [reconnectAttempts, setReconnectAttempts] = useState(0); // P3: Reconnect tracking

  // ── Code Editor State ──────────────────────────────────────────────
  const [code, setCode] = useState('');
  const [language, setLanguage] = useState('python');
  const [activeTab, setActiveTab] = useState('chat');

  const LANGUAGE_OPTIONS = [
    { key: 'python', label: 'Python' },
    { key: 'javascript', label: 'JavaScript' },
    { key: 'java', label: 'Java' },
    { key: 'cpp', label: 'C++' },
  ];

  // ── Proctoring State ────────────────────────────────────────────────
  const videoRef = useRef(null);
  const [userStream, setUserStream] = useState(null);
  const [screenStream, setScreenStream] = useState(null);

  const [hasPermissions, isStarted, proctorError, warnings, infractions] = useAssessmentProctoring({
    active: phase === 'interviewing' || phase === 'opening' || phase === 'initializing',
    round: 'technical',
    sessionId,
    navigate,
    setState: () => {}, 
    proctoring,
    setProctoring,
    webcamVideoRef: videoRef,
    webcamStream: userStream,
    screenStream
  });

  // ── Refs ────────────────────────────────────────────────────────────
  const wsRef = useRef(null);
  const messagesEndRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const tokenRefreshRef = useRef(null); // P3: Token refresh timer
  const reconnectTimerRef = useRef(null); // P3: Reconnect timer

  // ── Auto-scroll ──────────────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  // ── P2: Check for resumable session on mount ──────────────────────────
  useEffect(() => {
    const checkResumable = async () => {
      if (!sessionId || !token) return;
      try {
        // Look for any active interview sessions for this platform session
        const res = await fetch(`${API_BASE}/ai-interview/start`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            session_id: sessionId,
            role: role || 'Software Engineer',
            company: company || 'the company',
            max_questions: 12,
            voice_enabled: voiceMode,
          }),
        });
        if (res.ok) {
          const data = await res.json();
          if (data.status === 'resumable') {
            setResumableSession(data.interview_session_id);
          }
        }
      } catch {
        // Ignore — will start fresh
      }
    };
    checkResumable();
  }, [sessionId, token, role, company, voiceMode]);

  // ── P3: Token Refresh ───────────────────────────────────────────────
  const refreshToken = useCallback(async () => {
    if (!interviewSessionId || !token) return;
    try {
      const res = await fetch(`${API_BASE}/ai-interview/refresh-token?interview_session_id=${interviewSessionId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        // Send new token to WebSocket
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({
            type: 'refresh_token',
            token: data.token,
          }));
        }
      }
    } catch {
      // Token refresh failed — will reconnect on next disconnect
    }
  }, [interviewSessionId, token]);

  // Start token refresh interval (every 20 minutes for 24h expiry)
  useEffect(() => {
    if (phase === 'interviewing' || phase === 'opening') {
      tokenRefreshRef.current = setInterval(refreshToken, 20 * 60 * 1000);
      return () => clearInterval(tokenRefreshRef.current);
    }
  }, [phase, refreshToken]);

  // ── P3: Auto-reconnect on disconnect ────────────────────────────────
  const reconnectWs = useCallback(() => {
    if (!interviewSessionId || !token || !sessionId) return;
    if (reconnectAttempts >= 5) {
      setError('Connection lost. Please refresh the page.');
      setPhase('error');
      return;
    }

    setReconnectAttempts(prev => prev + 1);
    setPhase('opening');

    const wsUrl = `${WS_BASE}/ai-interview/ws?token=${token}&interview_session_id=${interviewSessionId}&session_id=${sessionId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      console.log('[AIInterviewer] WebSocket reconnected');
      setReconnectAttempts(0);
    };

    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        handleWsMessage(JSON.parse(event.data));
      } else {
        handleAudioResponse(event.data);
      }
    };

    ws.onerror = () => {
      // Will trigger onclose
    };

    ws.onclose = () => {
      if (phase !== 'completed' && phase !== 'error') {
        // Auto-reconnect after delay
        reconnectTimerRef.current = setTimeout(reconnectWs, 2000 * (reconnectAttempts + 1));
      }
    };
  }, [interviewSessionId, token, sessionId, reconnectAttempts, phase, handleWsMessage, handleAudioResponse]);

  // Cleanup reconnect timer
  useEffect(() => {
    return () => {
      clearTimeout(reconnectTimerRef.current);
      clearInterval(tokenRefreshRef.current);
    };
  }, []);

  // ── Start Interview ──────────────────────────────────────────────────
  const startInterview = useCallback(async () => {
    setPhase('initializing');
    setError(null);

    try {
      // Step 1: Initialize the session via REST
      const res = await fetch(`${API_BASE}/ai-interview/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          session_id: sessionId,
          role: role || 'Software Engineer',
          company: company || 'the company',
          max_questions: 12,
          voice_enabled: voiceMode,
        }),
      });

      if (!res.ok) {
        throw new Error(`Failed to initialize interview: ${res.statusText}`);
      }

      const data = await res.json();
      const ivSessionId = data.interview_session_id;
      setInterviewSessionId(ivSessionId);

      // Step 2: Connect WebSocket
      const wsUrl = `${WS_BASE}/ai-interview/ws?token=${token}&interview_session_id=${ivSessionId}&session_id=${sessionId}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        console.log('[AIInterviewer] WebSocket connected');
        setPhase('opening');
      };

      ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          handleWsMessage(JSON.parse(event.data));
        } else {
          // Binary: TTS audio
          handleAudioResponse(event.data);
        }
      };

      ws.onerror = (e) => {
        console.error('[AIInterviewer] WebSocket error', e);
        setError('Connection error. Please refresh and try again.');
        setPhase('error');
      };

      ws.onclose = () => {
        console.log('[AIInterviewer] WebSocket closed');
        if (phase !== 'completed' && phase !== 'error') {
          // P3: Auto-reconnect after brief delay
          reconnectTimerRef.current = setTimeout(() => {
            if (wsRef.current === ws) {
              reconnectWs();
            }
          }, 2000);
        }
      };

    } catch (err) {
      console.error('[AIInterviewer] Start failed', err);
      setError(err.message);
      setPhase('error');
    }
  }, [sessionId, token, role, company, voiceMode]);

  // ── WebSocket Message Handler ────────────────────────────────────────
  const handleWsMessage = useCallback((msg) => {
    const { type } = msg;

    switch (type) {
      case 'thinking':
        setIsThinking(true);
        break;

      case 'session_ready':
        setPhase('interviewing');
        setIsThinking(false);
        if (msg.opening_text) {
          addMessage({ role: 'interviewer', text: msg.opening_text, ts: Date.now() / 1000 });
        }
        break;

      case 'session_restored': // P2: Session restored from checkpoint
        setPhase('interviewing');
        setIsThinking(false);
        setProgress({ current: msg.questions_asked || 0, total: msg.max_questions || 12 });
        setCurrentStage(msg.current_stage || '');
        addMessage({
          role: 'interviewer',
          text: `Session restored. Continuing from question ${msg.questions_asked || 0}...`,
          ts: Date.now() / 1000,
          isTransition: true,
        });
        break;

      case 'question':
        setIsThinking(false);
        setPhase('interviewing');
        addMessage({
          role: 'interviewer',
          text: msg.text,
          ts: msg.timestamp || Date.now() / 1000,
          isFollowUp: msg.is_follow_up,
          questionId: msg.question_id,
          stage: msg.stage,
        });
        setCurrentStage(msg.stage || '');
        if (msg.questions_asked !== undefined) {
          setProgress({ current: msg.questions_asked, total: msg.max_questions || 12 });
        }
        break;

      case 'transition':
        setIsThinking(false);
        addMessage({
          role: 'interviewer',
          text: msg.text,
          ts: msg.timestamp || Date.now() / 1000,
          isTransition: true,
        });
        break;

      case 'interview_complete':
        setIsThinking(false);
        setPhase('completing');
        if (msg.closing_text) {
          addMessage({ role: 'interviewer', text: msg.closing_text, ts: Date.now() / 1000 });
        }
        setTimeout(() => {
          setPhase('completed');
          setFinalReport(msg.report || null);
          if (onComplete) onComplete(msg.report);
        }, 2000);
        break;

      case 'stt_result':
        if (msg.is_final && msg.text) {
          addMessage({ role: 'candidate', text: msg.text, ts: Date.now() / 1000 });
        }
        break;

      case 'ai_response_text':
        // Show text before audio arrives
        setIsSpeaking(true);
        break;

      case 'error':
        setIsThinking(false);
        setError(msg.message);
        break;

      case 'pong':
        break;

      default:
        console.log('[AIInterviewer] Unknown message type:', type, msg);
    }
  }, []);

  // ── Audio Response Handler ────────────────────────────────────────────
  const handleAudioResponse = useCallback(async (arrayBuffer) => {
    try {
      const audioCtx = audioContextRef.current || new (window.AudioContext || window.webkitAudioContext)();
      audioContextRef.current = audioCtx;
      const audioData = await audioCtx.decodeAudioData(arrayBuffer);
      const source = audioCtx.createBufferSource();
      source.buffer = audioData;
      source.connect(audioCtx.destination);
      source.start(0);
      setIsSpeaking(true);
      source.onended = () => setIsSpeaking(false);
    } catch (err) {
      console.error('[AIInterviewer] Audio playback failed', err);
      setIsSpeaking(false);
    }
  }, []);

  // ── Add Message Helper ───────────────────────────────────────────────
  const addMessage = (msg) => {
    setMessages(prev => [...prev, { id: Date.now() + Math.random(), ...msg }]);
  };

  // ── Send Text Answer ─────────────────────────────────────────────────
  const sendAnswer = useCallback((text) => {
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    addMessage({ role: 'candidate', text, ts: Date.now() / 1000 });
    setIsThinking(true);

    wsRef.current.send(JSON.stringify({
      type: 'answer',
      text,
      code: code || undefined,
      language: code ? language : undefined,
    }));
  }, [code, language]);

  // ── Voice Recording ──────────────────────────────────────────────────
  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        const arrayBuffer = await blob.arrayBuffer();
        const ws = wsRef.current;
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(arrayBuffer);
          ws.send(JSON.stringify({
            type: 'audio_end',
            code: code || undefined,
            language: code ? language : undefined,
          }));
          setIsThinking(true);
        }
        stream.getTracks().forEach(t => t.stop());
      };

      recorder.start(250); // collect data every 250ms
      setIsRecording(true);
    } catch (err) {
      console.error('[AIInterviewer] Microphone access failed', err);
      setError('Microphone access denied. Please allow mic access and try again.');
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  }, []);

  // ── End Interview ────────────────────────────────────────────────────
  const endInterview = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'end' }));
      setIsThinking(true);
      setPhase('completing');
    }
  }, []);

  // ── Keyboard Handler ─────────────────────────────────────────────────
  const handleKeyDown = (e) => {
    // No-op for voice-only
  };

  // ── Cleanup ──────────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      wsRef.current?.close();
      audioContextRef.current?.close();
      clearTimeout(reconnectTimerRef.current);
      clearInterval(tokenRefreshRef.current);
    };
  }, []);

  // ── Recommendation styling ────────────────────────────────────────────
  const getRecommendationStyle = (rec) => {
    const map = {
      'Strong Hire': { color: '#10b981', bg: 'rgba(16,185,129,0.15)', emoji: '🚀' },
      'Hire': { color: '#22c55e', bg: 'rgba(34,197,94,0.15)', emoji: '✅' },
      'Lean Hire': { color: '#eab308', bg: 'rgba(234,179,8,0.15)', emoji: '🟡' },
      'Lean Reject': { color: '#f97316', bg: 'rgba(249,115,22,0.15)', emoji: '⚠️' },
      'Reject': { color: '#ef4444', bg: 'rgba(239,68,68,0.15)', emoji: '❌' },
    };
    return map[rec] || { color: '#6b7280', bg: 'rgba(107,114,128,0.15)', emoji: '📋' };
  };

  // ─────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────

  // ── Idle / Start Screen ───────────────────────────────────────────────
  if (phase === 'idle') {
    return (
      <div className="aii-container">
        <div className="aii-start-card">
          <div className="aii-start-card__icon">🤖</div>
          <h2 className="aii-start-card__title">AI Technical Interviewer</h2>
          <p className="aii-start-card__sub">
            You'll be interviewed by <strong>Obi</strong>, our AI Senior Engineer.
            Obi has read your resume and will ask you targeted technical questions —
            then dig deeper based on your answers.
          </p>

          <div className="aii-start-card__details">
            <div className="aii-detail-item">
              <span className="aii-detail-item__icon">🎯</span>
              <div>
                <strong>Role</strong>
                <p>{role || 'Software Engineer'}</p>
              </div>
            </div>
            <div className="aii-detail-item">
              <span className="aii-detail-item__icon">🏢</span>
              <div>
                <strong>Company</strong>
                <p>{company || 'the company'}</p>
              </div>
            </div>
            <div className="aii-detail-item">
              <span className="aii-detail-item__icon">❓</span>
              <div>
                <strong>Questions</strong>
                <p>~12 adaptive questions</p>
              </div>
            </div>
            <div className="aii-detail-item">
              <span className="aii-detail-item__icon">⏱</span>
              <div>
                <strong>Duration</strong>
                <p>~30–45 minutes</p>
              </div>
            </div>
          </div>

          <div className="aii-start-card__tips">
            <strong>Proctoring is Active:</strong>
            <ul>
              <li>Camera and Microphone access are required</li>
              <li>Do not switch tabs or look away from the screen</li>
            </ul>
          </div>

          <div className="aii-start-card__tips">
            <strong>Tips:</strong>
            <ul>
              <li>Speak clearly and be specific — vague answers get follow-up questions</li>
              <li>Explain your reasoning, not just the outcome</li>
              <li>It's okay to think before answering</li>
            </ul>
          </div>

          {error && <div className="aii-error">{error}</div>}
          {proctorError && <div className="aii-error">Proctoring Error: {proctorError}</div>}

          {/* P2: Resume Interview Button */}
          {resumableSession && (
            <button
              className="aii-start-btn"
              style={{ background: 'rgba(99,102,241,0.2)', borderColor: '#6366f1', marginBottom: '12px' }}
              onClick={startInterview}
            >
              <span>Resume Interview</span>
              <span className="aii-start-btn__arrow">→</span>
            </button>
          )}

          <button className="aii-start-btn" onClick={startInterview}>
            <span>{resumableSession ? 'Start New Interview' : 'Begin Interview'}</span>
            <span className="aii-start-btn__arrow">→</span>
          </button>
        </div>
      </div>
    );
  }

  // ── Error Screen ──────────────────────────────────────────────────────
  if (phase === 'error') {
    return (
      <div className="aii-container">
        <div className="aii-error-card">
          <div className="aii-error-card__icon">⚠️</div>
          <h3>Interview Error</h3>
          <p>{error || 'An unexpected error occurred.'}</p>
          <button className="aii-start-btn" onClick={() => { setPhase('idle'); setError(null); }}>
            Try Again
          </button>
        </div>
      </div>
    );
  }

  // ── Completed: Final Report ────────────────────────────────────────────
  if (phase === 'completed' && finalReport) {
    const scores = finalReport.scores || {};
    const rec = finalReport.recommendation || scores.recommendation;
    const recStyle = getRecommendationStyle(rec);

    const scoreItems = [
      { label: 'Technical', score: scores.technical_score || 0, color: '#6366f1' },
      { label: 'Communication', score: scores.communication_score || 0, color: '#8b5cf6' },
      { label: 'Confidence', score: scores.confidence_score || 0, color: '#06b6d4' },
      { label: 'Problem Solving', score: scores.problem_solving_score || 0, color: '#10b981' },
      { label: 'Behavioral', score: scores.behavioral_score || 0, color: '#f59e0b' },
    ];

    return (
      <div className="aii-container">
        <div className="aii-report">
          <div className="aii-report__header">
            <h2>Interview Complete</h2>
            <p className="aii-report__candidate">{finalReport.candidate_name}</p>
            <div className="aii-report__overall">
              <span className="aii-report__overall-score">{Math.round(scores.overall_score || 0)}</span>
              <span className="aii-report__overall-label">Overall Score</span>
            </div>
          </div>

          <div className="aii-report__recommendation" style={{ background: recStyle.bg, borderColor: recStyle.color }}>
            <span style={{ fontSize: '2rem' }}>{recStyle.emoji}</span>
            <div>
              <div className="aii-report__rec-label">Recommendation</div>
              <div className="aii-report__rec-value" style={{ color: recStyle.color }}>{rec}</div>
            </div>
          </div>

          <div className="aii-report__scores">
            {scoreItems.map(s => (
              <ScoreGauge key={s.label} label={s.label} score={s.score} color={s.color} />
            ))}
          </div>

          <div className="aii-report__section">
            <h3>💪 Strengths</h3>
            <ul>
              {(finalReport.strengths || []).map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>

          <div className="aii-report__section">
            <h3>⚡ Areas for Improvement</h3>
            <ul>
              {(finalReport.areas_for_improvement || []).map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          </div>

          {finalReport.detailed_summary && (
            <div className="aii-report__section">
              <h3>📝 Interview Summary</h3>
              <p>{finalReport.detailed_summary}</p>
            </div>
          )}

          {finalReport.recommendation_rationale && (
            <div className="aii-report__section aii-report__rationale">
              <h3>🎯 Recommendation Rationale</h3>
              <p>{finalReport.recommendation_rationale}</p>
            </div>
          )}

          <div className="aii-report__meta">
            <span>⏱ {Math.round((finalReport.interview_duration_seconds || 0) / 60)} minutes</span>
            <span>❓ {finalReport.question_records?.length || 0} questions asked</span>
          </div>

          <button className="aii-start-btn" onClick={() => onComplete && onComplete(finalReport)}>
            View Full Dashboard →
          </button>
        </div>
      </div>
    );
  }

  // ── Interview Room ────────────────────────────────────────────────────
  return (
    <div className="aii-container aii-container--active">
      {/* Header */}
      <div className="aii-header">
        <div className="aii-header__interviewer">
          <div className="aii-avatar">
            <span>O</span>
            {(phase === 'opening' || phase === 'initializing') && (
              <span className="aii-avatar__pulse" />
            )}
          </div>
          <div>
            <div className="aii-header__name">Obi</div>
            <div className="aii-header__title">Senior Engineer · AI Interviewer</div>
          </div>
        </div>

        <div className="aii-header__controls">
          {currentStage && (
            <div className="aii-stage-badge">{currentStage}</div>
          )}
          {proctoring && <ProctoringPanel proctoring={proctoring} />}
          <button
            className="aii-end-btn"
            onClick={endInterview}
            disabled={phase !== 'interviewing'}
            title="End Interview"
          >
            End
          </button>
        </div>
      </div>

      {/* Progress */}
      {phase === 'interviewing' && (
        <ProgressBar
          current={progress.current}
          total={progress.total}
          stages={{ currentStage }}
        />
      )}

      {/* Tab Bar */}
      <div className="aii-tabs">
        <button
          className={`aii-tab-btn ${activeTab === 'chat' ? 'aii-tab-btn--active' : ''}`}
          onClick={() => setActiveTab('chat')}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          Chat
        </button>
        <button
          className={`aii-tab-btn ${activeTab === 'code' ? 'aii-tab-btn--active' : ''}`}
          onClick={() => setActiveTab('code')}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
          Code
        </button>
      </div>

      {/* Chat Area */}
      <div className={`aii-chat ${activeTab !== 'chat' ? 'aii-chat--hidden' : ''}`}>
        {phase === 'initializing' && (
          <div className="aii-init-message">
            <div className="aii-spinner" />
            <p>Obi is reading your resume and preparing your interview…</p>
          </div>
        )}

        {messages.map(msg => (
          <MessageBubble key={msg.id} message={msg} />
        ))}

        {isThinking && <ThinkingIndicator />}

        <div ref={messagesEndRef} />
      </div>

      {/* Code Area */}
      {activeTab === 'code' && (
        <div className="aii-code-area">
          <div className="aii-code-toolbar">
            <div className="aii-lang-selector">
              {LANGUAGE_OPTIONS.map(opt => (
                <button
                  key={opt.key}
                  className={`aii-lang-btn ${language === opt.key ? 'aii-lang-btn--active' : ''}`}
                  onClick={() => setLanguage(opt.key)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <span className="aii-code-hint">
              Code written here is shared with Obi for evaluation
            </span>
          </div>
          <div className="aii-code-editor-wrap">
            <CodeEditor
              value={code}
              onChange={setCode}
              language={language}
              questionTitle="Live Code"
            />
          </div>
        </div>
      )}

      {/* Input Area */}
      {phase === 'interviewing' && (
        <div className="aii-input-area">
          <div className="aii-voice-controls">
            <div className="aii-voice-waveform">
              <WaveformVisualizer isActive={isRecording || isSpeaking} color={isRecording ? '#ef4444' : '#6366f1'} />
            </div>
            {/* Hidden Video Feed for Proctoring */}
            <video ref={videoRef} autoPlay muted playsInline style={{ display: 'none' }} />

              <div className="aii-voice-status">
                {isRecording ? '🔴 Recording…' : isSpeaking ? '🔊 Obi is speaking…' : isThinking ? '⏳ Processing…' : '🎙️ Ready'}
              </div>
              <button
                className={`aii-voice-btn ${isRecording ? 'aii-voice-btn--recording' : ''}`}
                onMouseDown={startRecording}
                onMouseUp={stopRecording}
                onTouchStart={startRecording}
                onTouchEnd={stopRecording}
                disabled={isThinking || isSpeaking}
              >
                {isRecording ? '■ Release to Send' : '🎙 Hold to Speak'}
              </button>
            </div>
        </div>
      )}

      {phase === 'completing' && (
        <div className="aii-completing">
          <div className="aii-spinner" />
          <p>Generating your interview report…</p>
        </div>
      )}
    </div>
  );
}
