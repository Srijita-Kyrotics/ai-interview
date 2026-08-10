import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Mic, Target, Building2, ListChecks, Clock, AlertTriangle,
  ArrowRight, Send, ChevronRight, Zap, Sparkles, TrendingUp,
  MessageSquare, Code2, CheckCircle2, XCircle, Volume2, Loader2, Play,
  Settings2, RefreshCcw,
} from 'lucide-react';
import { useAssessmentProctoring } from '../proctoring/useAssessmentProctoring';
import { ProctoringModal, ProctoringPanel } from '../proctoring/ProctoringUI';
import { CodeEditor } from './CodeEditor';
import ObiAvatar from './ObiAvatar';
import { clearStoredUser } from '../api';

// ─────────────────────────────────────────────────────────────────────────────
// AI INTERVIEWER COMPONENT
// Production-grade voice + text interview interface
// ─────────────────────────────────────────────────────────────────────────────

const API_BASE = import.meta.env.VITE_API_URL || '/api';
const getWsBase = () =>
  import.meta.env.VITE_WS_URL ||
  `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api`;

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


const renderInline = (text) => {
  const nodes = [];
  const regex = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let lastIndex = 0;
  let match;
  let key = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(<React.Fragment key={key++}>{text.slice(lastIndex, match.index)}</React.Fragment>);
    }
    const token = match[0];
    if (token.startsWith('**')) {
      nodes.push(<strong key={key++}>{token.slice(2, -2)}</strong>);
    } else {
      nodes.push(<code key={key++} className="aii-inline-code">{token.slice(1, -1)}</code>);
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    nodes.push(<React.Fragment key={key++}>{text.slice(lastIndex)}</React.Fragment>);
  }
  return nodes;
};

const RichText = ({ text }) => {
  const parts = [];
  const regex = /```(\w*)\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;
  let key = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={key++}>{renderInline(text.slice(lastIndex, match.index))}</span>);
    }
    const lang = match[1];
    const code = match[2].replace(/\n$/, '');
    parts.push(
      <div key={key++} className="aii-code-block">
        {lang && <div className="aii-code-block__lang">{lang}</div>}
        <pre><code>{code}</code></pre>
      </div>
    );
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push(<span key={key++}>{renderInline(text.slice(lastIndex))}</span>);
  }
  return <>{parts}</>;
};

const useCountUp = (target, duration = 1200) => {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (target === undefined || target === null) return;
    let raf;
    const start = performance.now();
    const from = 0;
    const tick = (now) => {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setValue(Math.round(from + (target - from) * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return value;
};

const ScoreGauge = ({ label, score, color }) => {
  const pct = Math.round(score || 0);
  const animated = useCountUp(pct);
  const circumference = 2 * Math.PI * 28;
  const dash = (animated / 100) * circumference;

  return (
    <div className="aii-score-gauge">
      <svg width="76" height="76" viewBox="0 0 72 72">
        <circle cx="36" cy="36" r="28" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="6" />
        <circle
          cx="36" cy="36" r="28" fill="none"
          stroke={color} strokeWidth="6"
          strokeDasharray={`${dash} ${circumference}`}
          strokeLinecap="round"
          transform="rotate(-90 36 36)"
          style={{ transition: 'stroke-dasharray 0.05s linear' }}
        />
        <text x="36" y="40" textAnchor="middle" fill="white" fontSize="13" fontWeight="800">{animated}</text>
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
        <div className="aii-bubble__avatar" aria-hidden="true">
          <span>O</span>
          <i className="aii-bubble__avatar-dot" />
        </div>
      )}
      <div className="aii-bubble__content">
        {(message.isFollowUp || message.isTransition) && (
          <div className="aii-bubble__badges">
            {message.isFollowUp && (
              <span className="aii-badge aii-badge--followup">
                <MessageSquare size="11" /> Follow-up
              </span>
            )}
            {message.isTransition && (
              <span className="aii-badge aii-badge--transition">
                <ChevronRight size="11" /> Next Topic
              </span>
            )}
          </div>
        )}
        <RichText text={message.text} />
        <span className="aii-bubble__time">
          {new Date(message.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
      {!isInterviewer && (
        <div className="aii-bubble__avatar aii-bubble__avatar--user" aria-hidden="true">
          <span>You</span>
        </div>
      )}
    </div>
  );
};


const ThinkingIndicator = () => (
  <div className="aii-thinking">
    <div className="aii-bubble__avatar"><span>O</span><i className="aii-bubble__avatar-dot" /></div>
    <div className="aii-thinking__dots">
      <span />
      <span />
      <span />
    </div>
  </div>
);


const LiveStatusPill = ({ isRecording, isSpeaking, isThinking, isProcessing, isConnecting }) => {
  let label = 'Connected';
  let tone = 'idle';
  if (isRecording) { label = 'Listening'; tone = 'live'; }
  else if (isProcessing) { label = 'Transcribing'; tone = 'processing'; }
  else if (isSpeaking) { label = 'Speaking'; tone = 'live'; }
  else if (isThinking) { label = 'Thinking'; tone = 'thinking'; }
  else if (isConnecting) { label = 'Connecting'; tone = 'thinking'; }

  return (
    <div className={`aii-status-pill aii-status-pill--${tone}`} title={label}>
      <span className="aii-status-pill__dot" />
      {label}
    </div>
  );
};


const FinalReportView = ({ finalReport, onComplete }) => {
  const scores = finalReport.scores || {};
  const rec = finalReport.recommendation || scores.recommendation;
  const recMap = {
    'Strong Hire': { color: '#10b981', bg: 'rgba(16,185,129,0.15)' },
    'Hire': { color: '#22c55e', bg: 'rgba(34,197,94,0.15)' },
    'Lean Hire': { color: '#eab308', bg: 'rgba(234,179,8,0.15)' },
    'Lean Reject': { color: '#f97316', bg: 'rgba(249,115,22,0.15)' },
    'Reject': { color: '#ef4444', bg: 'rgba(239,68,68,0.15)' },
  };
  const recStyle = recMap[rec] || { color: '#6b7280', bg: 'rgba(107,114,128,0.15)' };
  const overall = Math.round(scores.overall_score || 0);
  const animatedOverall = useCountUp(overall);

  const scoreItems = [
    { label: 'Technical', score: scores.technical_score || 0, color: '#6366f1' },
    { label: 'Communication', score: scores.communication_score || 0, color: '#8b5cf6' },
    { label: 'Confidence', score: scores.confidence_score || 0, color: '#06b6d4' },
    { label: 'Problem Solving', score: scores.problem_solving_score || 0, color: '#10b981' },
    { label: 'Behavioral', score: scores.behavioral_score || 0, color: '#f59e0b' },
  ];

  const sections = [
    { title: 'Strengths', icon: <TrendingUp size="15" />, items: finalReport.strengths, tone: 'aii-report__section--good' },
    { title: 'Areas for Improvement', icon: <Zap size="15" />, items: finalReport.areas_for_improvement, tone: 'aii-report__section--warn' },
  ];

  return (
    <div className="aii-container">
      <div className="aii-report">
        <div className="aii-report__header">
          <div className="aii-report__done"><CheckCircle2 size="22" /> Interview Complete</div>
          <p className="aii-report__candidate">{finalReport.candidate_name}</p>
          <div className="aii-report__overall">
            <span className="aii-report__overall-score">{animatedOverall}</span>
            <span className="aii-report__overall-label">Overall Score</span>
          </div>
        </div>

        <div className="aii-report__recommendation" style={{ background: recStyle.bg, borderColor: recStyle.color }}>
          <CheckCircle2 size="34" style={{ color: recStyle.color }} />
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

        {sections.map(s => (
          <div className={`aii-report__section ${s.tone}`} key={s.title}>
            <h3>{s.icon} {s.title}</h3>
            <ul>
              {(s.items || []).map((item, i) => <li key={i}>{item}</li>)}
            </ul>
          </div>
        ))}

        {finalReport.communication_summary && finalReport.communication_summary.analyzed_answers > 0 && (
          <div className="aii-report__section">
            <h3><MessageSquare size="15" /> Communication Analysis</h3>
            {(() => {
              const cs = finalReport.communication_summary;
              const dims = cs.dimension_averages || {};
              return (
                <div className="aii-report__comm">
                  <div className="aii-report__comm-dims">
                    {Object.entries(dims).map(([key, val]) => (
                      <div className="aii-report__comm-dim" key={key}>
                        <span className="aii-report__comm-dim-label">{key.replace(/_/g, ' ')}</span>
                        <div className="aii-report__comm-dim-bar">
                          <div
                            className="aii-report__comm-dim-fill"
                            style={{ width: `${Math.round(val * 10)}%` }}
                          />
                        </div>
                        <span className="aii-report__comm-dim-val">{val}/10</span>
                      </div>
                    ))}
                  </div>
                  {(cs.top_strengths || []).length > 0 && (
                    <ul className="aii-report__comm-list">
                      {(cs.top_strengths || []).map((s, i) => <li key={`s${i}`}>+ {s}</li>)}
                    </ul>
                  )}
                  {(cs.top_concerns || []).length > 0 && (
                    <ul className="aii-report__comm-list aii-report__comm-list--concern">
                      {(cs.top_concerns || []).map((s, i) => <li key={`c${i}`}>&minus; {s}</li>)}
                    </ul>
                  )}
                </div>
              );
            })()}
          </div>
        )}

        {finalReport.coding_summary && finalReport.coding_summary.problem && (
          <div className="aii-report__section">
            <h3><Code2 size="15" /> Live Coding Round</h3>
            {(() => {
              const cs = finalReport.coding_summary;
              const subs = cs.submissions || [];
              const last = subs[subs.length - 1];
              return (
                <div className="aii-report__coding">
                  <p>
                    <strong>{cs.problem.title}</strong>
                    <span className="aii-report__coding-diff"> {cs.problem.difficulty}</span>
                    {cs.problem.topic ? ` — ${cs.problem.topic}` : ''}
                  </p>
                  {last && (
                    <p>
                      Final submission quality: <strong>{last.quality}/10</strong>
                      {last.language ? ` (${last.language})` : ''}
                      {last.feedback ? ` — ${last.feedback}` : ''}
                    </p>
                  )}
                  {subs.length > 0 && <p>{subs.length} submission{subs.length > 1 ? 's' : ''} tracked</p>}
                </div>
              );
            })()}
          </div>
        )}

        {finalReport.detailed_summary && (
          <div className="aii-report__section">
            <h3><MessageSquare size="15" /> Interview Summary</h3>
            <p>{finalReport.detailed_summary}</p>
          </div>
        )}

        {finalReport.recommendation_rationale && (
          <div className="aii-report__section aii-report__rationale">
            <h3><Target size="15" /> Recommendation Rationale</h3>
            <p>{finalReport.recommendation_rationale}</p>
          </div>
        )}

        <div className="aii-report__meta">
          <span><Clock size="13" /> {Math.round((finalReport.interview_duration_seconds || 0) / 60)} minutes</span>
          <span><ListChecks size="13" /> {finalReport.question_records?.length || 0} questions asked</span>
        </div>

        <button className="aii-start-btn" onClick={() => onComplete && onComplete(finalReport)}>
          View Full Dashboard
          <ArrowRight size="18" />
        </button>
      </div>
    </div>
  );
};


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

export default function AIInterviewer({ sessionId, token, role, company, resume, onComplete, proctoring, setProctoring }) {
  const navigate = useNavigate();

  // ── State ───────────────────────────────────────────────────────────
  const [phase, setPhase] = useState('idle');
  // idle → initializing → opening → interviewing → completing → completed | error

  const [messages, setMessages] = useState([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [micPermission, setMicPermission] = useState('unknown');
  const [statusMessage, setStatusMessage] = useState('Preparing your interview...');
  const [browserTtsFallback, setBrowserTtsFallback] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [lastSpeechText, setLastSpeechText] = useState('');
  const [audioAwaitingResponse, setAudioAwaitingResponse] = useState(false);
  const [answerRecorded, setAnswerRecorded] = useState(false);
  const [subtitleText, setSubtitleText] = useState('');
  const [lipLevel, setLipLevel] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const lipSyncIntervalRef = useRef(null);
  const audioMonitorRef = useRef(null);

  const openingIntro = "Hi, I'm Obi, your AI interviewer. I've reviewed your resume, and today we'll discuss your experience, projects, and technical skills. Let's get started.";

  const voiceMode = true;

  const [interviewSessionId, setInterviewSessionId] = useState(null);
  const [progress, setProgress] = useState({ current: 0, total: 12 });
  const [currentStage, setCurrentStage] = useState('');
  const [finalReport, setFinalReport] = useState(null);
  const [error, setError] = useState(null);
  const [latency, setLatency] = useState(null);
  const [resumableSession, setResumableSession] = useState(null);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [lastCandidateAnswer, setLastCandidateAnswer] = useState('');
  const [resumeSummaryOpen, setResumeSummaryOpen] = useState(false);
  const [resumeText, setResumeText] = useState('');

  const startedRef = useRef(false);
  const fallbackAudioTimerRef = useRef(null);
  const answerRecordedTimerRef = useRef(null);
  const lastAudioTextRef = useRef('');
  const lastAudioPlayedRef = useRef(false);

  // ── Code Editor State ──────────────────────────────────────────────
  const [code, setCode] = useState('');
  const [language, setLanguage] = useState('python');
  const [activeTab, setActiveTab] = useState('chat');
  const [stdin, setStdin] = useState('');
  const [runOutput, setRunOutput] = useState('');
  const [runStatus, setRunStatus] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [codingProblem, setCodingProblem] = useState(null); // Feature 9: live coding round
  const languageRef = useRef('python');
  useEffect(() => { languageRef.current = language; }, [language]);
  const codeRef = useRef('');
  useEffect(() => { codeRef.current = code; }, [code]);

  const formatElapsed = (sec) => {
    const m = Math.floor(sec / 60).toString().padStart(2, '0');
    const s = (sec % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  // Elapsed timer while interviewing
  useEffect(() => {
    if (phase !== 'interviewing') return;
    setElapsedSec(0);
    const t = setInterval(() => setElapsedSec(s => s + 1), 1000);
    return () => clearInterval(t);
  }, [phase]);

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

  // Video proctoring is DISABLED for now (we only want to validate voice +
  // interview flow). To re-enable later: set to `true`, request camera +
  // screen streams, and assign them to `webcamStream`/`screenStream` below.
  const proctoringEnabled = false;

  const proctor = useAssessmentProctoring({
    active: proctoringEnabled && (
      phase === 'interviewing' || phase === 'opening' || phase === 'initializing'
    ),
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
  const proctorError = proctor.status.assessmentStatus === 'Terminated Due To Malpractice'
    ? proctor.status.terminatedReason || 'Assessment terminated due to malpractice.'
    : '';

  const phaseRef = useRef(phase);
  const reconnectAttemptsRef = useRef(reconnectAttempts);
  const audioAwaitingRef = useRef(false);
  const fallbackTtsTimeoutRef = useRef(null);
  const lastAiMessageRef = useRef('');
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const tokenRefreshRef = useRef(null);
  const messagesEndRef = useRef(null);
  const textInputRef = useRef(null);
  const speechRecognitionRef = useRef(null);
  const browserTranscriptRef = useRef('');
  const pendingAudioRef = useRef(null);
  const audioEndSentRef = useRef(false);
  const audioEndTimerRef = useRef(null);

  useEffect(() => { phaseRef.current = phase }, [phase]);
  useEffect(() => { reconnectAttemptsRef.current = reconnectAttempts }, [reconnectAttempts]);

  const requestMicPermission = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setMicPermission('unsupported');
      return false;
    }

    try {
      await navigator.mediaDevices.getUserMedia({ audio: true });
      setMicPermission('granted');
      return true;
    } catch (err) {
      setMicPermission('denied');
      setError('Microphone access is required to continue. Please enable microphone permissions and refresh the page.');
      setPhase('error');
      return false;
    }
  }, []);

  const clearAudioFallbackTimer = useCallback(() => {
    if (fallbackTtsTimeoutRef.current) {
      clearTimeout(fallbackTtsTimeoutRef.current);
      fallbackTtsTimeoutRef.current = null;
    }
  }, []);

  const clearLipSync = useCallback(() => {
    if (lipSyncIntervalRef.current) {
      clearInterval(lipSyncIntervalRef.current);
      lipSyncIntervalRef.current = null;
    }
    setLipLevel(0);
  }, []);

  const startLipSync = useCallback(() => {
    clearLipSync();
    setLipLevel(0.3);
    lipSyncIntervalRef.current = setInterval(() => {
      setLipLevel(0.25 + Math.random() * 0.5);
    }, 70);
  }, [clearLipSync]);

  // ── Real-audio level monitor ──────────────────────────────────────────
  // When the backend sends TTS audio we attach an AnalyserNode so the
  // avatar mouth + waveform move with the actual audio being played
  // (this replaces the random lip-sync during real TTS playback).
  const stopAudioLevelMonitor = useCallback(() => {
    if (audioMonitorRef.current) {
      cancelAnimationFrame(audioMonitorRef.current);
      audioMonitorRef.current = null;
    }
    setAudioLevel(0);
  }, []);

  const startAudioLevelMonitor = useCallback((analyser) => {
    stopAudioLevelMonitor();
    const data = new Uint8Array(analyser.frequencyBinCount);
    let last = 0;
    const tick = () => {
      analyser.getByteFrequencyData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i += 1) sum += data[i];
      const avg = sum / data.length / 255;
      const smoothed = last + (avg - last) * 0.4;
      last = smoothed;
      setAudioLevel(smoothed);
      setLipLevel(0.18 + Math.min(smoothed * 3.2, 0.9));
      audioMonitorRef.current = requestAnimationFrame(tick);
    };
    tick();
  }, [stopAudioLevelMonitor]);

  useEffect(() => {
    const checkResumable = async () => {
      if (!sessionId || !token) return;
      try {
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

  // ── Finalize AI Response ──────────────────────────────────────────────
  const finishAiResponse = useCallback(() => {
    setIsThinking(false);
    setIsProcessing(false);
    setAudioAwaitingResponse(false);
    audioAwaitingRef.current = false;
  }, []);

  // ── Speech Synthesis Helper for Obi ─────────────────────────────────
  const speakText = useCallback((text) => {
    if (!('speechSynthesis' in window) || !text) return;
    try {
      window.speechSynthesis.cancel();
      const cleanText = text.replace(/[*#_`]/g, ''); // Strip markdown
      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      setSubtitleText(cleanText);
      setIsSpeaking(true);
      startLipSync();
      utterance.onend = () => {
        stopAudioLevelMonitor();
        setIsSpeaking(false);
        clearLipSync();
        finishAiResponse();
      };
      utterance.onerror = () => {
        stopAudioLevelMonitor();
        setIsSpeaking(false);
        clearLipSync();
        finishAiResponse();
      };
      window.speechSynthesis.speak(utterance);
    } catch {
      stopAudioLevelMonitor();
      setIsSpeaking(false);
      clearLipSync();
      finishAiResponse();
    }
  }, [finishAiResponse, startLipSync, clearLipSync, stopAudioLevelMonitor]);

  const queueAiMessage = useCallback((message, options = {}) => {
    stopAudioLevelMonitor();
    setIsThinking(false);
    setIsSpeaking(false);
    setIsProcessing(false);
    setStatusMessage(options.status || 'Obi is speaking...');
    setSubtitleText(message || '');
    setAudioAwaitingResponse(true);
    audioAwaitingRef.current = true;
    lastAiMessageRef.current = message || '';

    if (options.phase) {
      setPhase(options.phase);
    }
    addMessage({
      role: 'interviewer',
      text: message,
      ts: Date.now() / 1000,
      isFollowUp: options.isFollowUp,
      isTransition: options.isTransition,
    });

    clearAudioFallbackTimer();
    fallbackTtsTimeoutRef.current = setTimeout(() => {
      if (!audioAwaitingRef.current && browserTtsFallback) return;
      if ('speechSynthesis' in window && message) {
        speakText(message);
      }
    }, 800);
  }, [browserTtsFallback, clearAudioFallbackTimer, speakText, stopAudioLevelMonitor]);

  // ── WebSocket Message Handler ────────────────────────────────────────
  const handleWsMessage = useCallback((msg) => {
    const { type } = msg;

    switch (type) {
      case 'thinking':
        setIsThinking(true);
        setIsProcessing(false);
        break;

      case 'processing':
        setIsProcessing(true);
        setIsThinking(false);
        setIsSpeaking(false);
        setStatusMessage('Transcribing your response…');
        break;

      case 'status':
        if (msg.message) {
          setStatusMessage(msg.message);
        }
        break;

      case 'session_ready':
        setPhase('interviewing');
        setIsThinking(false);
        setIsProcessing(false);
        queueAiMessage(msg.opening_text || openingIntro, {
          status: 'Obi is joining the interview…',
          phase: 'interviewing',
          isTransition: true,
        });
        break;

      case 'session_restored': { // P2: Session restored from checkpoint
        setPhase('interviewing');
        setIsThinking(false);
        setProgress({ current: msg.questions_asked || 0, total: msg.max_questions || 12 });
        setCurrentStage(msg.current_stage || '');
        const restoreMsg = `Session restored. Continuing from question ${msg.questions_asked || 0}...`;
        queueAiMessage(restoreMsg, {
          status: 'Resuming your interview…',
          phase: 'interviewing',
          isTransition: true,
        });
        break;
      }

      case 'question':
        setIsThinking(false);
        setPhase('interviewing');
        setCurrentStage(msg.stage || '');
        if (msg.questions_asked !== undefined) {
          setProgress({ current: msg.questions_asked, total: msg.max_questions || 12 });
        }
        queueAiMessage(msg.text, {
          status: 'Obi is asking the next question…',
          phase: 'interviewing',
          isFollowUp: msg.is_follow_up,
          questionId: msg.question_id,
          stage: msg.stage,
        });
        break;

      case 'transition':
        setIsThinking(false);
        queueAiMessage(msg.text, {
          status: 'Obi is updating the interview…',
          phase: 'interviewing',
          isTransition: true,
        });
        break;

      case 'coding_problem': { // Feature 9: live coding round
        if (msg.problem) {
          setCodingProblem(msg.problem);
          setActiveTab('code');
          // Pre-fill starter code for the current language if the editor is empty
          const lang = languageRef.current;
          setCode(prev => {
            if (prev && prev.trim()) return prev;
            const starter = msg.problem.starter_code || {};
            return starter[lang] || '';
          });
        }
        break;
      }

      case 'interview_complete':
        setIsThinking(false);
        setPhase('completing');
        if (msg.closing_text) {
          addMessage({ role: 'interviewer', text: msg.closing_text, ts: Date.now() / 1000 });
          speakText(msg.closing_text);
        }
        setTimeout(() => {
          setPhase('completed');
          setFinalReport(msg.report || null);
          if (onComplete) onComplete(msg.report);
        }, 2000);
        break;

      case 'stt_result':
        setIsProcessing(false);
        if (msg.is_final && msg.text) {
          addMessage({ role: 'candidate', text: msg.text, ts: Date.now() / 1000 });
          setStatusMessage('Obi is thinking about your answer…');
        }
        break;

      case 'ai_response_text':
        queueAiMessage(msg.text, {
          status: 'Obi is speaking…',
          phase: 'interviewing',
        });
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
  }, [speakText]);

  // ── Audio Response Handler ────────────────────────────────────────────
  const handleAudioResponse = useCallback(async (arrayBuffer) => {
    clearAudioFallbackTimer();
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
    try {
      const audioCtx = audioContextRef.current || new (window.AudioContext || window.webkitAudioContext)();
      audioContextRef.current = audioCtx;
      const audioData = await audioCtx.decodeAudioData(arrayBuffer);
      const source = audioCtx.createBufferSource();
      source.buffer = audioData;
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyser.connect(audioCtx.destination);
      source.start(0);
      setIsSpeaking(true);
      setIsProcessing(false);
      startAudioLevelMonitor(analyser);
      source.onended = () => {
        stopAudioLevelMonitor();
        setIsSpeaking(false);
        clearLipSync();
        finishAiResponse();
      };
    } catch (err) {
      console.error('[AIInterviewer] Audio playback failed', err);
      stopAudioLevelMonitor();
      setIsSpeaking(false);
      clearLipSync();
      finishAiResponse();
    }
  }, [finishAiResponse, startLipSync, clearLipSync, clearAudioFallbackTimer, startAudioLevelMonitor, stopAudioLevelMonitor]);

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

    const wsUrl = `${getWsBase()}/ai-interview/ws/voice?token=${token}&interview_session_id=${interviewSessionId}&session_id=${sessionId}`;
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
      if (phaseRef.current !== 'completed' && phaseRef.current !== 'error') {
        reconnectTimerRef.current = setTimeout(reconnectWs, 2000 * (reconnectAttempts + 1));
      }
    };
  }, [interviewSessionId, token, sessionId, reconnectAttempts, handleWsMessage, handleAudioResponse]);

  // Cleanup reconnect timer
  useEffect(() => {
    return () => {
      clearTimeout(reconnectTimerRef.current);
      clearInterval(tokenRefreshRef.current);
    };
  }, []);

  // ── Start Interview ──────────────────────────────────────────────────
  const startInterview = useCallback(async (resumeExisting = true) => {
    setPhase('initializing');
    setStatusMessage('Preparing your interview...');
    setError(null);

    try {
      const shouldResume = resumeExisting && Boolean(resumableSession);
      let activeSessionId = sessionId;

      if (!shouldResume) {
        const pastedResume = resumeText.trim();
        if (pastedResume) {
          // Seed a fresh session with the pasted resume so Obi can
          // personalize questions to the candidate's actual background.
          const createRes = await fetch(`${API_BASE}/ai-interview/create-session`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ resume_text: pastedResume }),
          });
          if (!createRes.ok) {
            throw new Error('Failed to create interview session');
          }
          const createData = await createRes.json();
          activeSessionId = createData.session_id;
        }
      }

      const endpoint = shouldResume ? '/ai-interview/resume' : '/ai-interview/start';
      const url = `${API_BASE}${endpoint}`;
      const body = shouldResume
        ? JSON.stringify({ interview_session_id: resumableSession, session_id: activeSessionId })
        : JSON.stringify({
            session_id: activeSessionId,
            role: role || 'Software Engineer',
            company: company || 'the company',
            max_questions: 12,
            voice_enabled: voiceMode,
          });
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body,
      });

      if (!res.ok) {
        if (res.status === 401) clearStoredUser();
        throw new Error(`Failed to initialize interview: ${res.statusText}`);
      }

      const data = await res.json();
      const ivSessionId = data.interview_session_id;
      setInterviewSessionId(ivSessionId);
      if (data.status === 'resumable' && !resumableSession) {
        setResumableSession(ivSessionId);
      }

      const wsUrl = `${getWsBase()}/ai-interview/ws/voice?token=${token}&interview_session_id=${ivSessionId}&session_id=${activeSessionId}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.binaryType = 'arraybuffer';

        ws.onopen = () => {
        console.log('[AIInterviewer] WebSocket connected');
        setPhase('opening');
        setStatusMessage('Connecting to Obi...');
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
        if (phaseRef.current !== 'completed' && phaseRef.current !== 'error') {
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
  }, [sessionId, token, role, company, voiceMode, resumeText, resumableSession]);

  // ── Explicit start (Begin button) ────────────────────────────────────
  // The interview only starts on user action — no surprise mic/camera
  // requests on page load.
  const beginInterview = useCallback(async (resumeExisting = true) => {
    const allowed = await requestMicPermission();
    if (!allowed) {
      setError('Microphone permission is required to start the voice interview.');
      setPhase('idle');
      return;
    }
    startInterview(resumeExisting);
  }, [requestMicPermission, startInterview]);

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

  // ── Run Code ───────────────────────────────────────────────────────
  const runCode = useCallback(async () => {
    if (!code.trim() || isRunning) return;
    setIsRunning(true);
    setRunStatus('Running…');
    setRunOutput('');
    try {
      const res = await fetch(`${API_BASE}/ai-interview/run-code`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ language, code, stdin }),
      });
      const data = await res.json();
      if (!res.ok) {
        setRunStatus(data.detail || data.message || `Run failed (${res.status})`);
        setRunOutput(data.error || '');
        return;
      }
      if (!data.ok) {
        setRunStatus(data.error || 'Could not run code.');
        return;
      }
      setRunStatus(data.timed_out ? 'Execution timed out.' : 'Ran successfully.');
      const out = [data.stdout, data.stderr].filter(Boolean).join('\n');
      setRunOutput(out || '(no output)');
    } catch (err) {
      setRunStatus('Could not contact run service.');
      setRunOutput(err.message || '');
    } finally {
      setIsRunning(false);
    }
  }, [code, language, stdin, token, isRunning]);

  // ── Voice Recording ──────────────────────────────────────────────────
  // Sends `audio_end` with the browser-transcribed text when available, so
  // the backend can skip cloud STT (no API key required). If the browser
  // SpeechRecognition API is unavailable or returns nothing, the raw audio
  // bytes are still sent for the configured STT provider.
  const sendAudioEnd = useCallback((transcript) => {
    if (audioEndSentRef.current) return;
    audioEndSentRef.current = true;
    clearTimeout(audioEndTimerRef.current);
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (pendingAudioRef.current) ws.send(pendingAudioRef.current);
    ws.send(JSON.stringify({
      type: 'audio_end',
      code: codeRef.current || undefined,
      language: codeRef.current ? languageRef.current : undefined,
      transcript: (transcript || browserTranscriptRef.current || '').trim(),
    }));
    setIsThinking(true);
  }, []);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      mediaRecorderRef.current = recorder;
      audioChunksRef.current = [];
      browserTranscriptRef.current = '';
      audioEndSentRef.current = false;
      pendingAudioRef.current = null;

      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SR) {
        const recognition = new SR();
        speechRecognitionRef.current = recognition;
        recognition.lang = 'en-US';
        recognition.continuous = true;
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;
        recognition.onresult = (event) => {
          const parts = [];
          for (let i = 0; i < event.results.length; i += 1) {
            if (event.results[i].isFinal) parts.push(event.results[i][0].transcript);
          }
          if (parts.length) browserTranscriptRef.current = parts.join(' ').trim();
        };
        recognition.onerror = (event) => {
          console.warn('[AIInterviewer] Browser STT error:', event.error);
        };
        recognition.onend = () => {
          // Only fire once the mic has actually been released.
          if (!audioEndSentRef.current && mediaRecorderRef.current?.state !== 'recording') {
            sendAudioEnd();
          }
        };
      }

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        pendingAudioRef.current = await blob.arrayBuffer();
        const sr = speechRecognitionRef.current;
        if (sr) {
          try { sr.stop(); } catch (err) { /* already stopped */ }
          // Safety net: never block the answer on the browser STT.
          audioEndTimerRef.current = setTimeout(() => {
            if (!audioEndSentRef.current) sendAudioEnd();
          }, 3000);
        } else {
          sendAudioEnd();
        }
        stream.getTracks().forEach(t => t.stop());
      };

      recorder.start(250); // collect data every 250ms
      if (speechRecognitionRef.current) {
        try { speechRecognitionRef.current.start(); } catch (err) { /* already started */ }
      }
      setIsRecording(true);
    } catch (err) {
      console.error('[AIInterviewer] Microphone access failed', err);
      setError('Microphone access denied. Please allow mic access and try again.');
    }
  }, [sendAudioEnd]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  }, []);

  // ── End Interview ────────────────────────────────────────────────────
  const endInterview = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'end_voice' }));
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
      clearTimeout(fallbackTtsTimeoutRef.current);
      clearTimeout(audioEndTimerRef.current);
      clearInterval(tokenRefreshRef.current);
      try { speechRecognitionRef.current?.stop(); } catch (err) { /* ignore */ }
    };
  }, []);

  // ─────────────────────────────────────────────────────────────────────
  // RENDER
  // ─────────────────────────────────────────────────────────────────────

  // ── Idle / Start Screen ───────────────────────────────────────────────
  if (phase === 'idle') {
    return (
      <div className="aii-container">
        <div className="aii-start-card">
          <div className="aii-start-card__brand">
            <div className="aii-start-avatar">
              <span>O</span>
              <i />
            </div>
            <span className="aii-start-card__tag">AI Interview · Voice Enabled</span>
          </div>
          <h2 className="aii-start-card__title">Technical Interview with Obi</h2>
          <p className="aii-start-card__sub">
            You'll be interviewed by <strong>Obi</strong>, our AI Senior Engineer.
            Obi has read your resume and will ask targeted technical questions —
            then dig deeper based on your answers.
          </p>

          <div className="aii-start-card__details">
            <div className="aii-detail-item">
              <span className="aii-detail-item__icon"><Target size="18" /></span>
              <div>
                <strong>Role</strong>
                <p>{role || 'Software Engineer'}</p>
              </div>
            </div>
            <div className="aii-detail-item">
              <span className="aii-detail-item__icon"><Building2 size="18" /></span>
              <div>
                <strong>Company</strong>
                <p>{company || 'the company'}</p>
              </div>
            </div>
            <div className="aii-detail-item">
              <span className="aii-detail-item__icon"><ListChecks size="18" /></span>
              <div>
                <strong>Questions</strong>
                <p>~12 adaptive questions</p>
              </div>
            </div>
            <div className="aii-detail-item">
              <span className="aii-detail-item__icon"><Clock size="18" /></span>
              <div>
                <strong>Duration</strong>
                <p>~30–45 minutes</p>
              </div>
            </div>
          </div>

          <div className="aii-start-card__tips">
            <div className="aii-start-card__tips-title"><Sparkles size="14" /> Before you begin</div>
            <ul>
              <li>Speak clearly and be specific — vague answers get follow-up questions</li>
              <li>Explain your reasoning, not just the outcome</li>
              <li>It's okay to think before answering</li>
            </ul>
          </div>

          {resume && (
            <div className="aii-resume-preview">
              <div className="aii-resume-preview__header">
                <span>Resume snapshot</span>
                <button type="button" className="aii-link-button" onClick={() => setResumeSummaryOpen((open) => !open)}>
                  {resumeSummaryOpen ? 'Hide' : 'Show'} summary
                </button>
              </div>
              {resumeSummaryOpen && (
                <div className="aii-resume-preview__content">
                  {resume.parsed?.experience?.slice(0, 3).map((item, index) => (
                    <div key={index} className="aii-resume-preview__item">
                      <strong>{item.position || item.title}</strong>
                      <span>{item.company || item.organization}</span>
                    </div>
                  ))}
                  <p className="aii-resume-preview__note">Obi will use your resume to personalize questions.</p>
                </div>
              )}
            </div>
          )}

          <div className="aii-start-card__resume">
            <label htmlFor="aii-resume-text">Paste your resume (optional)</label>
            <textarea
              id="aii-resume-text"
              value={resumeText}
              onChange={(e) => setResumeText(e.target.value)}
              placeholder="Paste your resume text here so Obi can personalize questions to your background…"
              rows={5}
            />
          </div>

          {resumableSession && (
            <button
              className="aii-start-btn aii-start-btn--ghost"
              onClick={() => beginInterview(true)}
            >
              <span>Resume Interview</span>
              <ArrowRight size="18" />
            </button>
          )}

          <button className="aii-start-btn" onClick={() => beginInterview(false)}>
            <Mic size="18" />
            <span>{resumableSession ? 'Start New Interview' : 'Begin Interview'}</span>
            <ArrowRight size="18" />
          </button>
          <p className="aii-start-card__footnote">Make sure your microphone is allowed in the browser.</p>
        </div>
      </div>
    );
  }

  // ── Error Screen ──────────────────────────────────────────────────────
  if (phase === 'error') {
    return (
      <div className="aii-container">
        <div className="aii-error-card">
          <div className="aii-error-card__icon"><AlertTriangle size="48" /></div>
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
    return <FinalReportView finalReport={finalReport} onComplete={onComplete} />;
  }

  // ── Interview Room ────────────────────────────────────────────────────
  const avatarState = isSpeaking
    ? 'speaking'
    : isThinking || isProcessing
      ? 'thinking'
      : isRecording
        ? 'listening'
        : reconnectAttempts > 0
          ? 'error'
          : phase === 'opening' || phase === 'initializing'
            ? 'connecting'
            : 'idle';

  const stageStatusText =
    phase === 'initializing' || phase === 'opening' ? statusMessage : '';

  return (
    <div className="aii-container aii-container--active aii-room">
      <ProctoringModal modal={proctor.modal} onClose={proctor.dismissModal} />
      {/* Header */}
      <div className="aii-header aii-room__header">
        <div className="aii-header__interviewer">
          <ObiAvatar compact state={avatarState} lipLevel={lipLevel} audioLevel={audioLevel} />
          <div>
            <div className="aii-header__name">Obi</div>
            <div className="aii-header__subrow">
              <span className="aii-header__title">AI Technical Interviewer</span>
              <LiveStatusPill
                isRecording={isRecording}
                isSpeaking={isSpeaking}
                isThinking={isThinking}
                isProcessing={isProcessing}
                isConnecting={phase === 'opening' || phase === 'initializing'}
              />
            </div>
          </div>
        </div>

        <div className="aii-header__controls">
          <div className="aii-header__stats">
            <div className="aii-stat">
              <Clock size="14" />
              <span>Interview · {formatElapsed(elapsedSec)}</span>
            </div>
            <div className="aii-stat">
              <ListChecks size="14" />
              <span>{progress.current}/{progress.total}</span>
            </div>
          </div>
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
            <XCircle size="14" /> End Interview
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

      {/* Interview Room Stage — Obi is the main visual focus */}
      <div className="aii-room__stage">
        <ObiAvatar state={avatarState} lipLevel={lipLevel} audioLevel={audioLevel} statusText={stageStatusText} />
        <div className="aii-subtitle-card">
          <div className="aii-subtitle-card__label"><Volume2 size="12" /> Live subtitle</div>
          <p className="aii-subtitle-card__text">{subtitleText || 'Obi will speak here once the interview begins.'}</p>
        </div>
      </div>

      {/* Session Panel: tabs + chat + code */}
      <div className="aii-room__panel">
        <div className="aii-tabs" role="tablist">
          <button
            role="tab"
            aria-selected={activeTab === 'chat'}
            className={`aii-tab-btn ${activeTab === 'chat' ? 'aii-tab-btn--active' : ''}`}
            onClick={() => setActiveTab('chat')}
          >
            <MessageSquare size="14" />
            Chat
          </button>
          <button
            role="tab"
            aria-selected={activeTab === 'code'}
            className={`aii-tab-btn ${activeTab === 'code' ? 'aii-tab-btn--active' : ''}`}
            onClick={() => setActiveTab('code')}
          >
            <Code2 size="14" />
            Code
          </button>
        </div>

        {phase === 'initializing' && (
          <div className="aii-init-message">
            <ObiAvatar compact state="connecting" />
            <div className="aii-spinner aii-spinner--sm" />
            <p>{statusMessage || 'Obi is reading your resume and preparing your interview…'}</p>
          </div>
        )}

        <div className={`aii-chat ${activeTab !== 'chat' ? 'aii-chat--hidden' : ''}`}>
          {messages.map((msg) => (
            <MessageBubble key={msg.id || `${msg.role}-${msg.ts}`} message={msg} />
          ))}

          {isThinking && <ThinkingIndicator />}

          <div ref={messagesEndRef} />
        </div>

        {activeTab === 'code' && (
          <div className="aii-code-area">
            {codingProblem && (
              <div className="aii-problem">
                <div className="aii-problem__header">
                  <span className={`aii-problem__diff aii-problem__diff--${codingProblem.difficulty || 'medium'}`}>
                    {codingProblem.difficulty || 'medium'}
                  </span>
                  <h3>{codingProblem.title || 'Coding Challenge'}</h3>
                  {codingProblem.topic && <span className="aii-problem__topic">{codingProblem.topic}</span>}
                </div>
                <p className="aii-problem__desc">{codingProblem.description}</p>
                {(codingProblem.examples || []).length > 0 && (
                  <div className="aii-problem__examples">
                    {(codingProblem.examples || []).map((ex, i) => (
                      <div className="aii-problem__example" key={i}>
                        {ex.input && <pre>Input:    {ex.input}</pre>}
                        {ex.output && <pre>Output:   {ex.output}</pre>}
                        {ex.explanation && <pre>Explain:  {ex.explanation}</pre>}
                      </div>
                    ))}
                  </div>
                )}
                {(codingProblem.constraints || []).length > 0 && (
                  <div className="aii-problem__constraints">
                    {(codingProblem.constraints || []).map((c, i) => (
                      <span key={i}>{c}</span>
                    ))}
                  </div>
                )}
              </div>
            )}
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
              <button
                className="aii-run-btn"
                onClick={runCode}
                disabled={isRunning || !code.trim()}
                title="Run code and see output"
              >
                {isRunning ? <><Loader2 size="14" className="aii-spin" /> Running…</> : <><Play size="14" /> Run Code</>}
              </button>
              <button
                className="aii-submit-code-btn"
                onClick={() => {
                  const submission = `Here is my code solution in ${language}:\n\`\`\`${language}\n${code}\n\`\`\`\nExecution Output:\n${runOutput || '(Code executed)'}`;
                  sendAnswer(submission);
                  setActiveTab('chat');
                }}
                disabled={isThinking || !code.trim()}
                title="Send this solution to Obi for evaluation"
              >
                <Send size="14" /> Submit to Obi
              </button>
            </div>
            <div className="aii-code-editor-wrap">
              <CodeEditor
                value={code}
                onChange={setCode}
                language={language}
                questionTitle="Live Code"
              />
            </div>
            <div className="aii-run-panel">
              <div className="aii-run-panel__row">
                <input
                  className="aii-stdin-input"
                  placeholder="Optional stdin — e.g. 1 2 3"
                  value={stdin}
                  onChange={(e) => setStdin(e.target.value)}
                  disabled={isRunning}
                />
                {runStatus && (
                  <span
                    className={`aii-run-status aii-run-status--${runStatus.toLowerCase().includes('successfully') ? 'good' : 'bad'}`}
                  >
                    {runStatus.toLowerCase().includes('successfully')
                      ? <><CheckCircle2 size="13" /> {runStatus}</>
                      : <><AlertTriangle size="13" /> {runStatus}</>}
                  </span>
                )}
              </div>
              {runOutput && (
                <pre className="aii-run-output">{runOutput}</pre>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Input Area */}
      {phase === 'interviewing' && (
        <div className="aii-input-area aii-room__controls">
          <div className="aii-voice-controls">
            <div className="aii-voice-row">
              <div className="aii-mic-wrap">
                <button
                  className={`aii-mic-btn ${isRecording ? 'aii-mic-btn--recording' : ''}`}
                  onMouseDown={startRecording}
                  onMouseUp={stopRecording}
                  onTouchStart={startRecording}
                  onTouchEnd={stopRecording}
                  onMouseLeave={stopRecording}
                  onContextMenu={(e) => e.preventDefault()}
                  disabled={isThinking || isSpeaking}
                  title={isRecording ? 'Release to send voice' : 'Hold to speak to Obi'}
                  aria-label={isRecording ? 'Release to send voice' : 'Hold to speak to Obi'}
                >
                  <Mic size="26" />
                </button>
                <span className="aii-mic-label">{isRecording ? 'Release to send' : 'Hold to talk'}</span>
              </div>

              <div className="aii-voice-meta">
                <WaveformVisualizer isActive={isRecording || isSpeaking} color={isRecording ? '#f87171' : '#818cf8'} />
                <div className={`aii-voice-status aii-voice-status--${isRecording ? 'rec' : isSpeaking ? 'speak' : isThinking ? 'think' : 'idle'}`}>
                  {isRecording
                    ? <><span className="aii-voice-status__dot" /> Recording — release to send</>
                    : isSpeaking
                      ? <><Volume2 size="15" /> Obi is speaking</>
                      : isThinking
                        ? <><Loader2 size="15" className="aii-spin" /> Obi is thinking…</>
                        : <><Mic size="15" /> Ready — hold the mic button to answer</>}
                </div>
              </div>
            </div>

            {/* Hidden Video Feed for Proctoring */}
            <video ref={videoRef} autoPlay muted playsInline style={{ display: 'none' }} />

            <div className="aii-text-row">
              <input
                ref={textInputRef}
                type="text"
                className="aii-text-input"
                placeholder="Or type your response to Obi…"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && e.target.value.trim() && !isThinking) {
                    sendAnswer(e.target.value.trim());
                    e.target.value = '';
                  }
                }}
                disabled={isThinking || isSpeaking}
                aria-label="Type your response"
              />
              <button
                className="aii-send-btn"
                onClick={() => {
                  const input = textInputRef.current;
                  if (input && input.value.trim() && !isThinking) {
                    sendAnswer(input.value.trim());
                    input.value = '';
                  }
                }}
                disabled={isThinking || isSpeaking}
                title="Send message"
                aria-label="Send message"
              >
                <Send size="18" />
              </button>
            </div>
          </div>
        </div>
      )}

      {phase === 'completing' && (
        <div className="aii-completing">
          <ObiAvatar compact state="thinking" />
          <div className="aii-spinner aii-spinner--sm" />
          <p>Generating your interview report…</p>
        </div>
      )}
    </div>
  );
}
