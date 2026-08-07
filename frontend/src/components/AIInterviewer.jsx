import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Mic, Target, Building2, ListChecks, Clock, AlertTriangle, ShieldCheck,
  ArrowRight, Send, ChevronRight, Zap, TrendingUp, Volume2, Code2,
  CheckCircle2, XCircle, Loader2, Play, Settings2, RefreshCcw, MessageSquare,
  Wifi, Headphones, Lightbulb, Sparkles, PanelRightClose,
  PanelRightOpen, User, Bot, CircleCheck, VolumeX,
} from 'lucide-react';
import { useAssessmentProctoring } from '../proctoring/useAssessmentProctoring';
import { ProctoringModal } from '../proctoring/ProctoringUI';
import { CodeEditor } from './CodeEditor';
import { clearStoredUser } from '../api';
import ObiAvatar from './ObiAvatar';
import InterviewStatus from './InterviewStatus';

const API_BASE = import.meta.env.VITE_API_URL || '/api';
const getWsBase = () =>
  import.meta.env.VITE_WS_URL ||
  `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api`;

const LANGUAGE_OPTIONS = [
  { key: 'python', label: 'Python' },
  { key: 'javascript', label: 'JavaScript' },
  { key: 'java', label: 'Java' },
  { key: 'cpp', label: 'C++' },
];

const OPENING_INTRO =
  "Hi, I'm Obi, your AI interviewer. I've reviewed your resume, and today we'll discuss your experience, projects, and technical skills. Let's get started.";

// ─────────────────────────────────────────────────────────────────────────────
// RICH TEXT RENDERING
// ─────────────────────────────────────────────────────────────────────────────

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
      nodes.push(<code key={key++} className="oiv-inline-code">{token.slice(1, -1)}</code>);
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
      <div key={key++} className="oiv-code-block">
        {lang && <div className="oiv-code-block__lang">{lang}</div>}
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

// ─────────────────────────────────────────────────────────────────────────────
// LIVE SUBTITLES — word-by-word reveal while Obi speaks
// ─────────────────────────────────────────────────────────────────────────────

function useLiveSubtitle(text, isSpeaking) {
  const [visible, setVisible] = useState(text || '');

  useEffect(() => {
    if (!isSpeaking || !text) {
      setVisible(text || '');
      return undefined;
    }
    const words = text.split(' ');
    let idx = 0;
    setVisible('');
    const wpm = 165;
    const stepMs = Math.max(45, Math.round(60000 / wpm));
    const interval = setInterval(() => {
      idx += 1;
      setVisible(words.slice(0, idx).join(' '));
      if (idx >= words.length) {
        clearInterval(interval);
        setVisible(text);
      }
    }, stepMs);
    return () => clearInterval(interval);
  }, [text, isSpeaking]);

  return visible;
}

// ─────────────────────────────────────────────────────────────────────────────
// WAVEFORM VISUALIZER
// ─────────────────────────────────────────────────────────────────────────────

const WaveformVisualizer = ({ isActive, color = '#818cf8' }) => {
  const canvasRef = useRef(null);
  const animRef = useRef(null);
  const frameRef = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const bars = 44;
    const barWidth = width / bars - 2;

    const animate = () => {
      ctx.clearRect(0, 0, width, height);
      for (let i = 0; i < bars; i++) {
        const t = frameRef.current / 20 + i * 0.3;
        const amp = isActive ? (Math.sin(t) * 0.5 + 0.5) * 0.8 + 0.1 : 0.05;
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

  return <canvas ref={canvasRef} width={220} height={40} style={{ display: 'block' }} />;
};

// ─────────────────────────────────────────────────────────────────────────────
// CHAT BUILDING BLOCKS
// ─────────────────────────────────────────────────────────────────────────────

const MessageBubble = ({ message }) => {
  const isInterviewer = message.role === 'interviewer';
  return (
    <div className={`oiv-bubble ${isInterviewer ? 'oiv-bubble--ai' : 'oiv-bubble--user'}`}>
      {isInterviewer && (
        <div className="oiv-bubble__avatar" aria-hidden="true">
          <Bot size={15} />
          <i className="oiv-bubble__avatar-dot" />
        </div>
      )}
      <div className="oiv-bubble__content">
        {(message.isFollowUp || message.isTransition) && (
          <div className="oiv-bubble__badges">
            {message.isFollowUp && (
              <span className="oiv-badge oiv-badge--followup">
                <MessageSquare size="11" /> Follow-up
              </span>
            )}
            {message.isTransition && (
              <span className="oiv-badge oiv-badge--transition">
                <ChevronRight size="11" /> Next Topic
              </span>
            )}
          </div>
        )}
        <RichText text={message.text} />
        <span className="oiv-bubble__time">
          {new Date(message.ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
      {!isInterviewer && (
        <div className="oiv-bubble__avatar oiv-bubble__avatar--user" aria-hidden="true">
          <User size={14} />
        </div>
      )}
    </div>
  );
};

const ThinkingIndicator = () => (
  <div className="oiv-thinking">
    <div className="oiv-bubble__avatar"><Bot size={15} /><i className="oiv-bubble__avatar-dot" /></div>
    <div className="oiv-thinking__dots"><span /><span /><span /></div>
  </div>
);

// ─────────────────────────────────────────────────────────────────────────────
// SCORE GAUGES (report)
// ─────────────────────────────────────────────────────────────────────────────

const useCountUp = (target, duration = 1200) => {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (target === undefined || target === null) return undefined;
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
    <div className="oiv-gauge">
      <svg width="80" height="80" viewBox="0 0 72 72">
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
      <span className="oiv-gauge__label">{label}</span>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// FINAL REPORT
// ─────────────────────────────────────────────────────────────────────────────

const FinalReportView = ({ finalReport, onComplete }) => {
  const scores = finalReport.scores || {};
  const rec = finalReport.recommendation || scores.recommendation;
  const recMap = {
    'Strong Hire': { color: '#10b981' },
    'Hire': { color: '#22c55e' },
    'Lean Hire': { color: '#eab308' },
    'Lean Reject': { color: '#f97316' },
    'Reject': { color: '#ef4444' },
  };
  const recStyle = recMap[rec] || { color: '#6b7280' };
  const overall = Math.round(scores.overall_score || 0);
  const animatedOverall = useCountUp(overall);

  const scoreItems = [
    { label: 'Technical', score: scores.technical_score || 0, color: '#818cf8' },
    { label: 'Communication', score: scores.communication_score || 0, color: '#c084fc' },
    { label: 'Confidence', score: scores.confidence_score || 0, color: '#22d3ee' },
    { label: 'Problem Solving', score: scores.problem_solving_score || 0, color: '#34d399' },
    { label: 'Behavioral', score: scores.behavioral_score || 0, color: '#fbbf24' },
  ];

  const sections = [
    { title: 'Strengths', icon: <TrendingUp size="15" />, items: finalReport.strengths, tone: 'oiv-report__section--good' },
    { title: 'Areas for Improvement', icon: <Zap size="15" />, items: finalReport.areas_for_improvement, tone: 'oiv-report__section--warn' },
  ];

  return (
    <div className="oiv-shell oiv-shell--scroll">
      <div className="oiv-report">
        <div className="oiv-report__hero">
          <ObiAvatar mode="idle" size="med" />
          <div className="oiv-report__done"><CircleCheck size="20" /> Interview Complete</div>
          <p className="oiv-report__candidate">{finalReport.candidate_name}</p>
          <div className="oiv-report__overall">
            <span className="oiv-report__overall-score">{animatedOverall}</span>
            <span className="oiv-report__overall-label">Overall Score</span>
          </div>
        </div>

        <div className="oiv-report__recommendation" style={{ borderColor: recStyle.color }}>
          <CheckCircle2 size="30" style={{ color: recStyle.color }} />
          <div>
            <div className="oiv-report__rec-label">Recommendation</div>
            <div className="oiv-report__rec-value" style={{ color: recStyle.color }}>{rec}</div>
          </div>
        </div>

        <div className="oiv-report__scores">
          {scoreItems.map((s) => (
            <ScoreGauge key={s.label} label={s.label} score={s.score} color={s.color} />
          ))}
        </div>

        {sections.map((s) => (
          <div className={`oiv-report__section ${s.tone}`} key={s.title}>
            <h3>{s.icon} {s.title}</h3>
            <ul>
              {(s.items || []).map((item, i) => <li key={i}>{item}</li>)}
            </ul>
          </div>
        ))}

        {finalReport.communication_summary && finalReport.communication_summary.analyzed_answers > 0 && (
          <div className="oiv-report__section">
            <h3><MessageSquare size="15" /> Communication Analysis</h3>
            {(() => {
              const cs = finalReport.communication_summary;
              const dims = cs.dimension_averages || {};
              return (
                <div className="oiv-report__comm">
                  <div className="oiv-report__comm-dims">
                    {Object.entries(dims).map(([key, val]) => (
                      <div className="oiv-report__comm-dim" key={key}>
                        <span className="oiv-report__comm-dim-label">{key.replace(/_/g, ' ')}</span>
                        <div className="oiv-report__comm-dim-bar">
                          <div className="oiv-report__comm-dim-fill" style={{ width: `${Math.round(val * 10)}%` }} />
                        </div>
                        <span className="oiv-report__comm-dim-val">{val}/10</span>
                      </div>
                    ))}
                  </div>
                  {(cs.top_strengths || []).length > 0 && (
                    <ul className="oiv-report__comm-list">
                      {(cs.top_strengths || []).map((s, i) => <li key={`s${i}`}>+ {s}</li>)}
                    </ul>
                  )}
                  {(cs.top_concerns || []).length > 0 && (
                    <ul className="oiv-report__comm-list oiv-report__comm-list--concern">
                      {(cs.top_concerns || []).map((s, i) => <li key={`c${i}`}>&minus; {s}</li>)}
                    </ul>
                  )}
                </div>
              );
            })()}
          </div>
        )}

        {finalReport.coding_summary && finalReport.coding_summary.problem && (
          <div className="oiv-report__section">
            <h3><Code2 size="15" /> Live Coding Round</h3>
            {(() => {
              const cs = finalReport.coding_summary;
              const subs = cs.submissions || [];
              const last = subs[subs.length - 1];
              return (
                <div className="oiv-report__coding">
                  <p><strong>{cs.problem.title}</strong><span className="oiv-report__coding-diff"> {cs.problem.difficulty}</span>{cs.problem.topic ? ` — ${cs.problem.topic}` : ''}</p>
                  {last && (
                    <p>Final submission quality: <strong>{last.quality}/10</strong>{last.language ? ` (${last.language})` : ''}{last.feedback ? ` — ${last.feedback}` : ''}</p>
                  )}
                  {subs.length > 0 && <p>{subs.length} submission{subs.length > 1 ? 's' : ''} tracked</p>}
                </div>
              );
            })()}
          </div>
        )}

        {finalReport.detailed_summary && (
          <div className="oiv-report__section">
            <h3><MessageSquare size="15" /> Interview Summary</h3>
            <p>{finalReport.detailed_summary}</p>
          </div>
        )}

        {finalReport.recommendation_rationale && (
          <div className="oiv-report__section oiv-report__rationale">
            <h3><Target size="15" /> Recommendation Rationale</h3>
            <p>{finalReport.recommendation_rationale}</p>
          </div>
        )}

        <div className="oiv-report__meta">
          <span><Clock size="13" /> {Math.round((finalReport.interview_duration_seconds || 0) / 60)} minutes</span>
          <span><ListChecks size="13" /> {finalReport.question_records?.length || 0} questions asked</span>
        </div>

        <button className="oiv-btn oiv-btn--primary oiv-btn--block" onClick={() => onComplete && onComplete(finalReport)}>
          View Full Dashboard <ArrowRight size="18" />
        </button>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// ONBOARDING WIZARD
// ─────────────────────────────────────────────────────────────────────────────

function MicMeter({ active }) {
  const [level, setLevel] = useState(0);
  const animRef = useRef(null);
  const streamRef = useRef(null);
  const ctxRef = useRef(null);

  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        ctxRef.current = ctx;
        const src = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 1024;
        src.connect(analyser);
        const data = new Uint8Array(analyser.fftSize);
        const loop = () => {
          if (cancelled) return;
          analyser.getByteTimeDomainData(data);
          let sum = 0;
          for (let i = 0; i < data.length; i++) { const v = (data[i] - 128) / 128; sum += v * v; }
          const rms = Math.sqrt(sum / data.length);
          setLevel(Math.min(1, rms * 4));
          animRef.current = requestAnimationFrame(loop);
        };
        loop();
      } catch { /* handled by parent */ }
    })();
    return () => {
      cancelled = true;
      cancelAnimationFrame(animRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
      if (ctxRef.current) { try { ctxRef.current.close(); } catch { /* noop */ } }
    };
  }, [active]);

  const bars = 28;
  return (
    <div className="oiv-micmeter" aria-hidden="true">
      {Array.from({ length: bars }).map((_, i) => {
        const center = Math.abs(i - bars / 2) / (bars / 2);
        const h = active ? Math.max(6, level * 100 * (1 - center * 0.5)) : 6;
        return <span key={i} style={{ height: `${h}%` }} />;
      })}
    </div>
  );
}

const ENV_CHECKS = [
  { icon: <VolumeX size="16" />, title: 'Quiet environment', desc: 'Minimize background noise so Obi can hear you clearly.' },
  { icon: <Lightbulb size="16" />, title: 'Good lighting', desc: 'Keep your face visible for the AI proctoring system.' },
  { icon: <Wifi size="16" />, title: 'Stable internet', desc: 'A reliable connection keeps the live interview smooth.' },
  { icon: <Headphones size="16" />, title: 'Headphones (optional)', desc: 'Helps you hear Obi clearly and avoids echo.' },
];

const OnboardingWizard = ({
  step, setStep,
  micPermission, micLevelActive, setMicLevelActive, setMicPermission,
  role, company, resume, resumableSession, startInterview, error,
}) => {
  const [checks, setChecks] = useState([]);
  const [micTest, setMicTest] = useState({ status: 'idle', duration: 0, error: '' });
  const micTestRecorderRef = useRef(null);
  const micTestStreamRef = useRef(null);
  const micTestUrlRef = useRef(null);
  const micTestTimerRef = useRef(null);
  const micTestStopTimerRef = useRef(null);
  const micTestAudioRef = useRef(null);

  const micErrorLabel = (err) => {
    if (!err) return 'Microphone access was denied. Allow it in your browser settings, then try again.';
    const name = err?.name || '';
    if (name === 'NotAllowedError') return 'Microphone permission was denied. Allow access in your browser settings and retry.';
    if (name === 'NotFoundError') return 'No microphone was found. Connect a microphone and try again.';
    if (name === 'NotReadableError') return 'Your microphone is busy or not accessible. Close other apps using it and retry.';
    if (name === 'OverconstrainedError') return 'No microphone matched the required settings. Choose another device.';
    if (name === 'SecurityError') return 'Microphone access is blocked by your browser or system security settings.';
    if (name === 'AbortError') return 'Microphone setup was interrupted. Try again.';
    return `Microphone could not be started: ${err?.message || name || 'unknown error'}`;
  };

  const stopMicTestRecording = useCallback(() => {
    if (micTestStopTimerRef.current) { clearTimeout(micTestStopTimerRef.current); micTestStopTimerRef.current = null; }
    if (micTestTimerRef.current) { clearInterval(micTestTimerRef.current); micTestTimerRef.current = null; }
    if (micTestRecorderRef.current && micTestRecorderRef.current.state === 'recording') {
      micTestRecorderRef.current.stop();
    }
  }, []);

  const playMicTest = useCallback(() => {
    const url = micTestUrlRef.current;
    if (!url) return;
    const audio = new Audio(url);
    micTestAudioRef.current?.pause();
    micTestAudioRef.current = audio;
    audio.onplay = () => setMicTest((t) => ({ ...t, status: 'playing' }));
    audio.onended = () => setMicTest((t) => ({ ...t, status: 'recorded' }));
    audio.onerror = () => setMicTest((t) => ({ ...t, status: 'error', error: 'Playback failed. Your browser may be blocking audio output.' }));
    const playPromise = audio.play();
    if (playPromise) {
      playPromise.catch(() => setMicTest((t) => ({ ...t, status: 'error', error: 'Playback was blocked by your browser. Click replay to try again.' })));
    }
  }, []);

  const runMicTest = useCallback(async () => {
    setMicTest({ status: 'recording', duration: 0, error: '' });
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        setMicPermission('unsupported');
        setMicTest({ status: 'error', duration: 0, error: 'Microphones are not supported in this browser.' });
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micTestStreamRef.current = stream;
      setMicPermission('granted');
      setMicLevelActive(true);

      let mime = 'audio/webm;codecs=opus';
      if (typeof MediaRecorder !== 'undefined' && !MediaRecorder.isTypeSupported(mime)) {
        mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '';
      }
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      micTestRecorderRef.current = recorder;
      const chunks = [];
      recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: chunks[0]?.type || 'audio/webm' });
        if (micTestUrlRef.current) URL.revokeObjectURL(micTestUrlRef.current);
        micTestUrlRef.current = URL.createObjectURL(blob);
        stream.getTracks().forEach((t) => t.stop());
        micTestStreamRef.current = null;
        setMicTest((t) => ({ status: 'recorded', duration: t.duration || 1, error: '' }));
        playMicTest();
      };
      recorder.start(250);

      const startedAt = Date.now();
      micTestTimerRef.current = setInterval(() => {
        const sec = Math.min(5, Math.round((Date.now() - startedAt) / 1000));
        setMicTest((t) => ({ ...t, duration: sec }));
      }, 500);
      micTestStopTimerRef.current = setTimeout(() => stopMicTestRecording(), 5000);
    } catch (err) {
      setMicPermission('denied');
      setMicTest({ status: 'error', duration: 0, error: micErrorLabel(err) });
    }
  }, [playMicTest, setMicLevelActive, setMicPermission, stopMicTestRecording]);

  useEffect(() => () => {
    stopMicTestRecording();
    micTestStreamRef.current?.getTracks().forEach((t) => t.stop());
    if (micTestUrlRef.current) URL.revokeObjectURL(micTestUrlRef.current);
    micTestAudioRef.current?.pause();
  }, [stopMicTestRecording]);
  const steps = [
    { key: 'meet', label: 'Meet Obi' },
    { key: 'setup', label: 'Setup Check' },
    { key: 'ready', label: "You're Ready" },
  ];
  const stepIndex = { meet: 0, setup: 1, ready: 2 }[step] ?? 0;

  const toggleCheck = (title) => {
    setChecks((prev) => (prev.includes(title) ? prev.filter((t) => t !== title) : [...prev, title]));
  };

  const details = [
    { icon: <Target size="17" />, label: 'Role', value: role || 'Software Engineer' },
    { icon: <Building2 size="17" />, label: 'Company', value: company || 'the company' },
    { icon: <ListChecks size="17" />, label: 'Questions', value: '~12 adaptive' },
    { icon: <Clock size="17" />, label: 'Duration', value: '30–45 minutes' },
    { icon: <Volume2 size="17" />, label: 'Format', value: 'Voice + optional code' },
    { icon: <ShieldCheck size="17" />, label: 'Proctoring', value: 'AI monitored' },
  ];

  return (
    <div className="oiv-shell oiv-shell--onboarding">
      <header className="oiv-onboard-header">
        <div className="oiv-mark">
          <ObiAvatar mode="idle" size="mini" />
        </div>
        <span className="oiv-onboard-header__wordmark">AI Interview Coach</span>
        <span className="oiv-onboard-header__step">Step {stepIndex + 1} of 3</span>
      </header>

      <div className="oiv-onboard">
        <aside className="oiv-onboard__rail">
          {steps.map((s, i) => (
            <button
              key={s.key}
              type="button"
              className={`oiv-rail-step ${i === stepIndex ? 'oiv-rail-step--active' : ''} ${i < stepIndex ? 'oiv-rail-step--done' : ''}`}
              onClick={() => setStep(s.key)}
            >
              <span className="oiv-rail-step__num">
                {i < stepIndex ? <CheckCircle2 size="14" /> : i + 1}
              </span>
              <span className="oiv-rail-step__label">{s.label}</span>
              <span className="oiv-rail-step__line" />
            </button>
          ))}
          <div className="oiv-onboard__rail-note">
            <Sparkles size="15" />
            <p>Your interview is fully automated. Obi adapts each question to your answers in real time.</p>
          </div>
        </aside>

        <section className="oiv-onboard__panel" key={step}>
          {/* ── STEP 1: MEET OBI ─────────────────────────────── */}
          {step === 'meet' && (
            <div className="oiv-onboard__content">
              <div className="oiv-onboard__avatar-wrap">
                <ObiAvatar mode="idle" size="hero" />
              </div>
              <h1>Meet Obi, your AI interviewer</h1>
              <p className="oiv-onboard__lead">
                Obi has already reviewed your resume. You'll be interviewed as a
                {' '}<strong>{role || 'Software Engineer'}</strong> for <strong>{company || 'the company'}</strong> —
                with live voice, adaptive follow-ups, and optional coding rounds.
              </p>

              <div className="oiv-detail-grid">
                {details.map((d) => (
                  <div className="oiv-detail-tile" key={d.label}>
                    <span className="oiv-detail-tile__icon">{d.icon}</span>
                    <div>
                      <span className="oiv-detail-tile__label">{d.label}</span>
                      <strong>{d.value}</strong>
                    </div>
                  </div>
                ))}
              </div>

              {resume?.parsed && (
                <div className="oiv-resume-chip">
                  <CheckCircle2 size="16" />
                  <span><strong>Resume detected</strong> · {resume.parsed.skills?.length || 0} skills, {resume.parsed.experience?.length || 0} roles parsed for personalization</span>
                </div>
              )}

              <div className="oiv-onboard__actions">
                <button className="oiv-btn oiv-btn--primary" onClick={() => setStep('setup')}>
                  Continue <ArrowRight size="16" />
                </button>
              </div>
            </div>
          )}

          {/* ── STEP 2: SETUP CHECK ──────────────────────────── */}
          {step === 'setup' && (
            <div className="oiv-onboard__content">
              <h1>Quick setup check</h1>
              <p className="oiv-onboard__lead">
                Make sure your microphone works and you're in a good spot. This takes about 20 seconds.
              </p>

              <div className="oiv-mic-card">
                <div className="oiv-mic-card__top">
                  <div className={`oiv-mic-pill oiv-mic-pill--${micPermission}`}>
                    <span className="oiv-mic-pill__dot" />
                    {micPermission === 'granted' && 'Microphone ready'}
                    {micPermission === 'denied' && 'Microphone blocked'}
                    {micPermission === 'unsupported' && 'Mic unsupported'}
                    {micPermission === 'unknown' && 'Microphone not checked'}
                  </div>
                  <button
                    type="button"
                    className="oiv-btn oiv-btn--ghost oiv-btn--sm"
                    onClick={runMicTest}
                    disabled={micTest.status === 'recording'}
                  >
                    {micTest.status === 'recording' ? <Loader2 size="15" className="oiv-spin" /> : <Mic size="15" />}
                    {micTest.status === 'recording' ? 'Recording…' : micPermission === 'granted' ? 'Retest microphone' : 'Test microphone'}
                  </button>
                </div>
                <MicMeter active={micLevelActive} />

                {micTest.status === 'recording' && (
                  <div className="oiv-mictest">
                    <div className="oiv-mictest__row">
                      <span className="oiv-mictest__dot" />
                      <span>Recording — speak now…</span>
                      <strong>{micTest.duration}s</strong>
                    </div>
                    <WaveformVisualizer isActive color="#10b981" />
                  </div>
                )}

                {micTest.status === 'playing' && (
                  <div className="oiv-mictest">
                    <div className="oiv-mictest__row">
                      <Volume2 size="15" />
                      <span>Playing back your recording…</span>
                      <strong>{micTest.duration}s</strong>
                    </div>
                    <WaveformVisualizer isActive color="#10b981" />
                  </div>
                )}

                {micTest.status === 'recorded' && (
                  <div className="oiv-mictest oiv-mictest--done">
                    <div className="oiv-mictest__row">
                      <CheckCircle2 size="15" />
                      <span>Played back your recording</span>
                      <strong>{micTest.duration}s</strong>
                    </div>
                    <button type="button" className="oiv-btn oiv-btn--ghost oiv-btn--sm" onClick={playMicTest}>
                      <Play size="14" /> Replay
                    </button>
                  </div>
                )}

                {micTest.status === 'error' && (
                  <div className="oiv-mictest oiv-mictest--error">
                    <AlertTriangle size="15" />
                    <span>{micTest.error}</span>
                  </div>
                )}

                <p className="oiv-mic-card__hint">
                  {micTest.status === 'error'
                    ? 'You can still continue and type your answers.'
                    : micPermission === 'granted'
                      ? 'Speak for a few seconds — we will play it back so you can confirm your mic works.'
                      : 'We only access your mic inside the interview. Nothing is recorded or stored.'}
                </p>
              </div>

              <div className="oiv-env-grid">
                {ENV_CHECKS.map((c) => {
                  const on = checks.includes(c.title);
                  return (
                    <button
                      type="button"
                      key={c.title}
                      className={`oiv-env-item ${on ? 'oiv-env-item--on' : ''}`}
                      onClick={() => toggleCheck(c.title)}
                      aria-pressed={on}
                    >
                      <span className="oiv-env-item__icon">{on ? <CircleCheck size="16" /> : c.icon}</span>
                      <span>
                        <strong>{c.title}</strong>
                        <small>{c.desc}</small>
                      </span>
                    </button>
                  );
                })}
              </div>

              <div className="oiv-onboard__actions">
                <button className="oiv-btn oiv-btn--ghost" onClick={() => setStep('meet')}><ChevronRight size="16" className="oiv-flip-x" /> Back</button>
                <button className="oiv-btn oiv-btn--primary" onClick={() => setStep('ready')}>
                  Continue <ArrowRight size="16" />
                </button>
              </div>
            </div>
          )}

          {/* ── STEP 3: READY ────────────────────────────────── */}
          {step === 'ready' && (
            <div className="oiv-onboard__content oiv-onboard__content--center">
              <div className="oiv-onboard__avatar-wrap oiv-onboard__avatar-wrap--ready">
                <ObiAvatar mode="speaking" lipLevel={0.4} size="hero" />
              </div>
              <h1>Ready when you are</h1>
              <p className="oiv-onboard__lead">
                Obi will greet you and begin the interview. Speak clearly, explain your reasoning, and take your time.
              </p>

              <div className="oiv-ready-card">
                <div className="oiv-ready-card__row">
                  <span><Target size="15" /> Role</span><strong>{role || 'Software Engineer'}</strong>
                </div>
                <div className="oiv-ready-card__row">
                  <span><Building2 size="15" /> Company</span><strong>{company || 'the company'}</strong>
                </div>
                <div className="oiv-ready-card__row">
                  <span><ListChecks size="15" /> Questions</span><strong>~12 adaptive</strong>
                </div>
                <div className="oiv-ready-card__row">
                  <span><Mic size="15" /> Microphone</span>
                  <strong className={micPermission === 'granted' ? 'oiv-text-success' : 'oiv-text-warn'}>
                    {micPermission === 'granted' ? 'Ready' : 'Typing mode'}
                  </strong>
                </div>
              </div>

              {resumableSession && (
                <button className="oiv-btn oiv-btn--ghost oiv-btn--block" onClick={() => startInterview(true)}>
                  <RefreshCcw size="16" /> Resume previous interview
                </button>
              )}

              {error && <div className="oiv-alert oiv-alert--error"><AlertTriangle size="16" /> {error}</div>}

              <div className="oiv-onboard__actions oiv-onboard__actions--center">
                <button className="oiv-btn oiv-btn--ghost" onClick={() => setStep('setup')}><ChevronRight size="16" className="oiv-flip-x" /> Back</button>
                <button className="oiv-btn oiv-btn--primary oiv-btn--lg" onClick={() => startInterview(false)}>
                  <Sparkles size="18" /> Begin Interview
                </button>
              </div>
              <p className="oiv-onboard__footnote">Keep this tab focused and in fullscreen for the best experience.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// INTERVIEW ROOM BUILDING BLOCKS
// ─────────────────────────────────────────────────────────────────────────────

const ChatPanel = ({ messages, isThinking, phase, statusMessage, messagesEndRef }) => (
  <div className="oiv-chat">
    {phase === 'initializing' && (
      <div className="oiv-chat__init">
        <div className="oiv-chat__spinner" />
        <p>{statusMessage || 'Obi is reading your resume…'}</p>
      </div>
    )}
    {messages.map((msg) => (
      <MessageBubble key={msg.id || `${msg.role}-${msg.ts}`} message={msg} />
    ))}
    {isThinking && <ThinkingIndicator />}
    <div ref={messagesEndRef} />
  </div>
);

const CodePanel = ({
  codingProblem, language, setLanguage, code, setCode, runCode, isRunning, runStatus, runOutput,
  stdin, setStdin, isThinking, onSubmitCode,
}) => (
  <div className="oiv-code">
    {codingProblem && (
      <div className="oiv-problem">
        <div className="oiv-problem__header">
          <span className={`oiv-problem__diff oiv-problem__diff--${codingProblem.difficulty || 'medium'}`}>
            {codingProblem.difficulty || 'medium'}
          </span>
          <h3>{codingProblem.title || 'Coding Challenge'}</h3>
          {codingProblem.topic && <span className="oiv-problem__topic">{codingProblem.topic}</span>}
        </div>
        <p className="oiv-problem__desc">{codingProblem.description}</p>
        {(codingProblem.examples || []).length > 0 && (
          <div className="oiv-problem__examples">
            {(codingProblem.examples || []).map((ex, i) => (
              <div className="oiv-problem__example" key={i}>
                {ex.input && <pre>Input:    {ex.input}</pre>}
                {ex.output && <pre>Output:   {ex.output}</pre>}
                {ex.explanation && <pre>Explain:  {ex.explanation}</pre>}
              </div>
            ))}
          </div>
        )}
        {(codingProblem.constraints || []).length > 0 && (
          <div className="oiv-problem__constraints">
            {(codingProblem.constraints || []).map((c, i) => <span key={i}>{c}</span>)}
          </div>
        )}
      </div>
    )}

    <div className="oiv-code__toolbar">
      <div className="oiv-lang-selector">
        {LANGUAGE_OPTIONS.map((opt) => (
          <button
            key={opt.key}
            type="button"
            className={`oiv-lang-btn ${language === opt.key ? 'oiv-lang-btn--active' : ''}`}
            onClick={() => setLanguage(opt.key)}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <button
        type="button"
        className="oiv-btn oiv-btn--ghost oiv-btn--sm"
        onClick={runCode}
        disabled={isRunning || !code.trim()}
        title="Run code and see output"
      >
        {isRunning ? <Loader2 size="14" className="oiv-spin" /> : <Play size="14" />} Run
      </button>
      <button
        type="button"
        className="oiv-btn oiv-btn--submit oiv-btn--sm"
        onClick={onSubmitCode}
        disabled={isThinking || !code.trim()}
        title="Send this solution to Obi for evaluation"
      >
        <Send size="14" /> Submit to Obi
      </button>
    </div>

    <div className="oiv-code__editor">
      <CodeEditor value={code} onChange={setCode} language={language} questionTitle="Live Code" />
    </div>

    <div className="oiv-run">
      <div className="oiv-run__row">
        <input
          className="oiv-run__stdin"
          placeholder="Optional stdin — e.g. 1 2 3"
          value={stdin}
          onChange={(e) => setStdin(e.target.value)}
          disabled={isRunning}
        />
        {runStatus && (
          <span className={`oiv-run__status oiv-run__status--${runStatus.toLowerCase().includes('successfully') ? 'good' : 'bad'}`}>
            {runStatus.toLowerCase().includes('successfully')
              ? <><CheckCircle2 size="12" /> {runStatus}</>
              : <><AlertTriangle size="12" /> {runStatus}</>}
          </span>
        )}
      </div>
      {runOutput && <pre className="oiv-run__output">{runOutput}</pre>}
    </div>
  </div>
);

const InputDock = ({
  isRecording, startRecording, stopRecording, isThinking, isSpeaking,
  sendAnswer, textInputRef,
}) => (
  <div className="oiv-input-dock">
    <div className="oiv-input-dock__inner">
      <div className="oiv-mic-wrap">
        <button
          type="button"
          className={`oiv-mic-btn ${isRecording ? 'oiv-mic-btn--recording' : ''}`}
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
          <Mic size="24" />
          <span className="oiv-mic-btn__ripple" />
        </button>
        <span className="oiv-mic-label">{isRecording ? 'Release to send' : 'Hold to talk'}</span>
      </div>

      <div className="oiv-voice-meta">
        <WaveformVisualizer isActive={isRecording || isSpeaking} color={isRecording ? '#f87171' : '#818cf8'} />
        <div className={`oiv-voice-status oiv-voice-status--${isRecording ? 'rec' : isSpeaking ? 'speak' : isThinking ? 'think' : 'idle'}`}>
          {isRecording
            ? <><span className="oiv-voice-status__dot" /> Recording — release to send</>
            : isSpeaking
              ? <><Volume2 size="15" /> Obi is speaking</>
              : isThinking
                ? <><Loader2 size="15" className="oiv-spin" /> Obi is thinking…</>
                : <><Mic size="15" /> Ready — hold the mic to answer</>}
        </div>
      </div>

      <div className="oiv-text-row">
        <input
          ref={textInputRef}
          type="text"
          className="oiv-text-input"
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
          type="button"
          className="oiv-send-btn"
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
          <Send size="17" />
        </button>
      </div>
    </div>
  </div>
);

const SubtitleCard = ({ subtitleText, isSpeaking, isRecording, isThinking, isProcessing, isConnecting }) => {
  const visible = useLiveSubtitle(subtitleText, isSpeaking);
  let caption = null;
  let tone = 'idle';
  if (isConnecting) { caption = 'Connecting to Obi…'; tone = 'connecting'; }
  else if (isRecording) { caption = 'Listening — go ahead'; tone = 'listening'; }
  else if (isProcessing) { caption = 'Transcribing your answer…'; tone = 'processing'; }
  else if (isThinking) { caption = 'Obi is thinking…'; tone = 'thinking'; }
  else if (isSpeaking) { caption = 'Obi is speaking'; tone = 'speaking'; }

  return (
    <div className={`oiv-subtitle oiv-subtitle--${tone}`}>
      <span className="oiv-subtitle__label">{caption || 'Live transcript'}</span>
      <p className="oiv-subtitle__text">
        {visible || (caption || 'Obi will greet you here once the interview begins.')}
      </p>
    </div>
  );
};

const ErrorScreen = ({ error, onRetry }) => (
  <div className="oiv-shell">
    <div className="oiv-error">
      <div className="oiv-error__icon"><AlertTriangle size="40" /></div>
      <h3>Interview couldn't start</h3>
      <p>{error || 'An unexpected error occurred.'}</p>
      <button className="oiv-btn oiv-btn--primary" onClick={onRetry}>Try Again</button>
    </div>
  </div>
);

// ── DEV-ONLY DIAGNOSTICS PANEL ──────────────────────────────────────────────
// Shows live pipeline health (Session/Auth/WebSocket/Mic/Camera/STT/LLM/TTS/
// Audio/Resume/Memory/State). Only rendered when the app was built for
// development; never in production.

const DiagnosticsPanel = ({ status, phase, statusMessage, connected, micPermission, camActive, faceActive }) => {
  const rows = [
    { label: 'Interview Session', value: status.session },
    { label: 'Auth Token', value: status.auth },
    { label: 'WebSocket', value: connected ? 'ok' : status.ws },
    { label: 'Microphone', value: micPermission === 'granted' ? 'ok' : micPermission === 'denied' ? 'blocked' : 'idle' },
    { label: 'Camera', value: camActive ? 'ok' : 'idle' },
    { label: 'STT (Speech-to-text)', value: status.stt },
    { label: 'LLM (Obi brain)', value: status.llm },
    { label: 'TTS (Obi voice)', value: status.tts },
    { label: 'Audio Playback', value: status.audio },
    { label: 'Resume Loaded', value: status.resume },
    { label: 'Memory (Transcript)', value: status.memory },
    { label: 'Interview State', value: phase },
  ];
  const toneFor = (v) => (v === 'ok' ? 'ok' : v === 'processing' || v === 'thinking' || v === 'listening' ? 'busy' : v === 'idle' ? 'idle' : 'bad');
  return (
    <div className="oiv-diag">
      <div className="oiv-diag__head">
        <Settings2 size="13" /> Dev Diagnostics
        <span className="oiv-diag__msg">{statusMessage}</span>
      </div>
      <div className="oiv-diag__grid">
        {rows.map((r) => (
          <div className="oiv-diag__row" key={r.label}>
            <span className="oiv-diag__label">{r.label}</span>
            <span className={`oiv-diag__value oiv-diag__value--${toneFor(r.value)}`}>{r.value}</span>
          </div>
        ))}
      </div>
      {status.lastMessage && <div className="oiv-diag__last">last event: {status.lastMessage} · ws msgs: {status.wsMessages}</div>}
    </div>
  );
};

// ─────────────────────────────────────────────────────────────────────────────
// MAIN COMPONENT
// ─────────────────────────────────────────────────────────────────────────────

export default function AIInterviewer({ sessionId, token, role, company, resume, onComplete, proctoring, setProctoring }) {
  const navigate = useNavigate();

  const [phase, setPhase] = useState('onboarding');
  const [onboardingStep, setOnboardingStep] = useState('meet');
  const [messages, setMessages] = useState([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [micPermission, setMicPermission] = useState('unknown');
  const [micLevelActive, setMicLevelActive] = useState(false);
  const [statusMessage, setStatusMessage] = useState('Preparing your interview…');
  const [initStep, setInitStep] = useState(0);
  const [browserTtsFallback, setBrowserTtsFallback] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [showDiag, setShowDiag] = useState(false);
  const [subtitleText, setSubtitleText] = useState('');
  const [lipLevel, setLipLevel] = useState(0);
  const lipSyncIntervalRef = useRef(null);

  const voiceMode = true;

  const [interviewSessionId, setInterviewSessionId] = useState(null);
  const [progress, setProgress] = useState({ current: 0, total: 12 });
  const [currentStage, setCurrentStage] = useState('');
  const [finalReport, setFinalReport] = useState(null);
  const [error, setError] = useState(null);
  const [resumableSession, setResumableSession] = useState(null);
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [elapsedSec, setElapsedSec] = useState(0);

  const [code, setCode] = useState('');
  const [language, setLanguage] = useState('python');
  const [activeTab, setActiveTab] = useState('chat');
  const [drawerOpen, setDrawerOpen] = useState(() => typeof window !== 'undefined' && window.innerWidth >= 1280);
  const [stdin, setStdin] = useState('');
  const [runOutput, setRunOutput] = useState('');
  const [runStatus, setRunStatus] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [codingProblem, setCodingProblem] = useState(null);
  const languageRef = useRef('python');
  useEffect(() => { languageRef.current = language; }, [language]);

  const [diag, setDiag] = useState({ session: 'idle', auth: 'idle', mic: 'idle', cam: 'idle', stt: 'idle', llm: 'idle', tts: 'idle', audio: 'idle', ws: 'idle', face: 'idle', resume: 'idle', memory: 'idle', lastMessage: '', wsMessages: 0 });

  const phaseRef = useRef(phase);
  const reconnectAttemptsRef = useRef(reconnectAttempts);
  const audioAwaitingRef = useRef(false);
  const fallbackTtsTimeoutRef = useRef(null);
  const lastAiMessageRef = useRef('');
  const wsRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const initWatchdogRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioContextRef = useRef(null);
  const tokenRefreshRef = useRef(null);
  const messagesEndRef = useRef(null);
  const textInputRef = useRef(null);

  useEffect(() => { phaseRef.current = phase; }, [phase]);
  useEffect(() => { reconnectAttemptsRef.current = reconnectAttempts; }, [reconnectAttempts]);

  // ── Seed diagnostics from props ──────────────────────────────────────
  useEffect(() => {
    setDiag((d) => ({
      ...d,
      auth: token ? 'ok' : 'error',
      resume: resume && (resume.rawText || resume.text || resume.summary) ? 'ok' : 'warn',
      memory: 'empty',
    }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Elapsed timer while interviewing
  useEffect(() => {
    if (phase !== 'interviewing') return undefined;
    setElapsedSec(0);
    const t = setInterval(() => setElapsedSec((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [phase]);

  // ── Proctoring ─────────────────────────────────────────────────────
  const videoRef = useRef(null);
  const [userStream, setUserStream] = useState(null);
  const [screenStream, setScreenStream] = useState(null);
  const userStreamRef = useRef(null);
  const screenStreamRef = useRef(null);
  useEffect(() => { userStreamRef.current = userStream; }, [userStream]);
  useEffect(() => { screenStreamRef.current = screenStream; }, [screenStream]);

  const startProctoring = useCallback(async () => {
    try {
      const uMedia = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      const dMedia = await navigator.mediaDevices.getDisplayMedia({ video: true });
      setUserStream(uMedia);
      setScreenStream(dMedia);
      if (videoRef.current) videoRef.current.srcObject = uMedia;
      setDiag((d) => ({ ...d, mic: 'ok', cam: 'ok' }));
    } catch (err) {
      console.warn('[AIInterviewer] Proctoring capture denied or failed', err?.name || err);
      setDiag((d) => ({ ...d, cam: 'error' }));
    }
  }, []);

  const proctor = useAssessmentProctoring({
    active: phase === 'interviewing' || phase === 'opening' || phase === 'initializing',
    round: 'technical',
    sessionId,
    navigate,
    setState: () => {},
    proctoring,
    setProctoring,
    webcamVideoRef: videoRef,
    webcamStream: userStream,
    screenStream,
    voiceInterview: true,
  });
  const proctorError = proctor.status.assessmentStatus === 'Terminated Due To Malpractice'
    ? proctor.status.terminatedReason || 'Assessment terminated due to malpractice.'
    : '';

  // ── Mic permission ──────────────────────────────────────────────────
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

  // ── Resumable session check ────────────────────────────────────────
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
      } catch { /* Ignore — will start fresh */ }
    };
    checkResumable();
  }, [sessionId, token, role, company, voiceMode]);

  // ── Token refresh ──────────────────────────────────────────────────
  const refreshToken = useCallback(async () => {
    if (!interviewSessionId || !token) return;
    try {
      const res = await fetch(`${API_BASE}/ai-interview/refresh-token?interview_session_id=${interviewSessionId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ type: 'refresh_token', token: data.token }));
        }
      }
    } catch { /* Token refresh failed — will reconnect on next disconnect */ }
  }, [interviewSessionId, token]);

  useEffect(() => {
    if (phase === 'interviewing' || phase === 'opening') {
      tokenRefreshRef.current = setInterval(refreshToken, 20 * 60 * 1000);
      return () => clearInterval(tokenRefreshRef.current);
    }
    return undefined;
  }, [phase, refreshToken]);

  // ── Message list helper ─────────────────────────────────────────────
  const addMessage = useCallback((msg) => {
    setMessages((prev) => [...prev, { id: `${Date.now()}-${Math.random()}`, ...msg }]);
    setDiag((d) => ({ ...d, memory: 'active' }));
  }, []);

  const finishAiResponse = useCallback(() => {
    setIsThinking(false);
    setIsProcessing(false);
    audioAwaitingRef.current = false;
  }, []);

  // ── Speech synthesis fallback ───────────────────────────────────────
  const speakText = useCallback((text) => {
    if (!('speechSynthesis' in window) || !text) return;
    try {
      window.speechSynthesis.cancel();
      const cleanText = text.replace(/[*#_`]/g, '');
      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.rate = 1.0;
      utterance.pitch = 1.0;
      setSubtitleText(cleanText);
      setIsSpeaking(true);
      startLipSync();
      utterance.onend = () => {
        setIsSpeaking(false);
        clearLipSync();
        finishAiResponse();
      };
      utterance.onerror = () => {
        setIsSpeaking(false);
        clearLipSync();
        finishAiResponse();
      };
      window.speechSynthesis.speak(utterance);
    } catch {
      setIsSpeaking(false);
      clearLipSync();
      finishAiResponse();
    }
  }, [finishAiResponse, startLipSync, clearLipSync]);

  const queueAiMessage = useCallback((message, options = {}) => {
    setIsThinking(false);
    setIsSpeaking(false);
    setIsProcessing(false);
    setStatusMessage(options.status || 'Obi is speaking…');
    setSubtitleText(message || '');
    audioAwaitingRef.current = true;
    lastAiMessageRef.current = message || '';

    if (options.phase) setPhase(options.phase);

    addMessage({
      role: 'interviewer',
      text: message,
      ts: Date.now() / 1000,
      isFollowUp: options.isFollowUp,
      isTransition: options.isTransition,
    });

    clearAudioFallbackTimer();
    fallbackTtsTimeoutRef.current = setTimeout(() => {
      if (!browserTtsFallback) return;
      if ('speechSynthesis' in window && message) speakText(message);
    }, 2200);
  }, [browserTtsFallback, clearAudioFallbackTimer, speakText, addMessage]);

  // ── Watchdog: never let the user sit on an ambiguous "Connecting…" state.
  // If the init sequence (or report finalization) exceeds its budget, fail
  // loudly with an exact reason instead of hanging forever.
  const clearInitWatchdog = useCallback(() => {
    if (initWatchdogRef.current) {
      clearTimeout(initWatchdogRef.current);
      initWatchdogRef.current = null;
    }
  }, []);

  const armInitWatchdog = useCallback((seconds, message) => {
    clearInitWatchdog();
    initWatchdogRef.current = setTimeout(() => {
      if (phaseRef.current === 'initializing' || phaseRef.current === 'opening' || phaseRef.current === 'completing') {
        setError(message);
        setPhase('error');
      }
    }, seconds * 1000);
  }, [clearInitWatchdog]);

  // ── WebSocket handler ───────────────────────────────────────────────
  const handleWsMessage = useCallback((msg) => {
    const { type } = msg;

    switch (type) {
      case 'thinking':
        setIsThinking(true);
        setIsProcessing(false);
        setDiag((d) => ({ ...d, stt: 'ok', llm: 'processing', lastMessage: 'LLM thinking' }));
        break;

      case 'progress':
        setStatusMessage(msg.step || msg.message || 'Preparing…');
        if (/analyzing|preparing/i.test(msg.step || '')) setInitStep(3);
        break;

      case 'processing':
        setIsProcessing(true);
        setIsThinking(false);
        setIsSpeaking(false);
        setStatusMessage('Transcribing your response…');
        setDiag((d) => ({ ...d, stt: 'processing', lastMessage: 'STT processing' }));
        break;

      case 'session_ready':
        clearInitWatchdog();
        setPhase('interviewing');
        setIsThinking(false);
        setIsProcessing(false);
        setStatusMessage('Obi is greeting you…');
        queueAiMessage(msg.opening_text || OPENING_INTRO, {
          status: 'Obi is greeting you…',
          phase: 'interviewing',
          isTransition: true,
        });
        break;

      case 'session_restored':
        clearInitWatchdog();
        setPhase('interviewing');
        setIsThinking(false);
        setProgress({ current: msg.questions_asked || 0, total: msg.max_questions || 12 });
        setCurrentStage(msg.current_stage || '');
        queueAiMessage(`Session restored. Continuing from question ${msg.questions_asked || 0}...`, {
          status: 'Resuming your interview…',
          phase: 'interviewing',
          isTransition: true,
        });
        break;

      case 'question':
        clearInitWatchdog();
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

      case 'coding_problem':
        if (msg.problem) {
          setCodingProblem(msg.problem);
          setActiveTab('code');
          setDrawerOpen(true);
          const lang = languageRef.current;
          setCode((prev) => {
            if (prev && prev.trim()) return prev;
            const starter = msg.problem.starter_code || {};
            return starter[lang] || '';
          });
        }
        break;

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
          setSubtitleText(msg.text);
          setStatusMessage('Obi is thinking about your answer…');
          setDiag((d) => ({ ...d, stt: 'ok', lastMessage: 'STT transcript' }));
        }
        break;

      case 'ai_response_text':
        queueAiMessage(msg.text, {
          status: 'Obi is speaking…',
          phase: 'interviewing',
        });
        setDiag((d) => ({ ...d, llm: 'ok', lastMessage: 'LLM response' }));
        break;

      case 'error':
        clearInitWatchdog();
        setIsThinking(false);
        setIsSpeaking(false);
        setIsProcessing(false);
        setError(msg.message || 'An unexpected error occurred.');
        setPhase('error');
        setDiag((d) => ({ ...d, lastMessage: `error: ${msg.error_code || 'unknown'}` }));
        break;

      case 'pong':
        break;

      default:
        console.log('[AIInterviewer] Unknown message type:', type, msg);
    }
  }, [speakText, queueAiMessage, addMessage, onComplete, clearInitWatchdog]);

  // ── Audio playback ──────────────────────────────────────────────────
  const handleAudioResponse = useCallback(async (arrayBuffer) => {
    if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    try {
      const audioCtx = audioContextRef.current || new (window.AudioContext || window.webkitAudioContext)();
      audioContextRef.current = audioCtx;
      const audioData = await audioCtx.decodeAudioData(arrayBuffer);
      const source = audioCtx.createBufferSource();
      source.buffer = audioData;
      source.connect(audioCtx.destination);
      source.start(0);
      clearAudioFallbackTimer();
      setIsSpeaking(true);
      setIsProcessing(false);
      startLipSync();
      setDiag((d) => ({ ...d, tts: 'ok', audio: 'ok', lastMessage: 'TTS playback' }));
      source.onended = () => {
        setIsSpeaking(false);
        clearLipSync();
        finishAiResponse();
      };
    } catch (err) {
      console.error('[AIInterviewer] Audio playback failed', err);
      clearAudioFallbackTimer();
      setIsSpeaking(false);
      clearLipSync();
      finishAiResponse();
      setDiag((d) => ({ ...d, tts: 'error', audio: 'error', lastMessage: 'TTS playback failed' }));
      // Fall back to browser speech so the candidate still hears Obi.
      if (lastAiMessageRef.current && 'speechSynthesis' in window) speakText(lastAiMessageRef.current);
    }
  }, [finishAiResponse, startLipSync, clearLipSync, clearAudioFallbackTimer, speakText]);

  // ── Reconnect ───────────────────────────────────────────────────────
  const reconnectWs = useCallback(() => {
    if (!interviewSessionId || !token || !sessionId) return;
    if (reconnectAttemptsRef.current >= 5) {
      setError('Connection lost. Please refresh the page.');
      setPhase('error');
      return;
    }

    reconnectAttemptsRef.current += 1;
    setReconnectAttempts(reconnectAttemptsRef.current);
    setPhase('opening');
    setInitStep(2);
    setStatusMessage('Reconnecting to Obi…');
    armInitWatchdog(45, 'Obi is taking too long to reconnect. Please try again.');

    const wsUrl = `${getWsBase()}/ai-interview/ws/voice?token=${token}&interview_session_id=${interviewSessionId}&session_id=${sessionId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    ws.binaryType = 'arraybuffer';

    ws.onopen = () => {
      console.log('[AIInterviewer] WebSocket reconnected');
      setIsConnected(true);
      reconnectAttemptsRef.current = 0;
      setReconnectAttempts(0);
      setInitStep(2);
      setStatusMessage('Opening your voice channel…');
      setDiag((d) => ({ ...d, ws: 'ok' }));
    };

    ws.onmessage = (event) => {
      if (typeof event.data === 'string') {
        handleWsMessage(JSON.parse(event.data));
      } else {
        handleAudioResponse(event.data);
      }
      setDiag((d) => ({ ...d, wsMessages: d.wsMessages + 1 }));
    };

    ws.onerror = () => { /* Will trigger onclose */ };

    ws.onclose = () => {
      setIsConnected(false);
      setDiag((d) => ({ ...d, ws: 'error' }));
      if (phaseRef.current !== 'completed' && phaseRef.current !== 'error') {
        const attempt = reconnectAttemptsRef.current;
        reconnectTimerRef.current = setTimeout(reconnectWs, 2000 * (attempt + 1));
      }
    };
  }, [interviewSessionId, token, sessionId, handleWsMessage, handleAudioResponse, armInitWatchdog]);

  useEffect(() => () => {
    clearTimeout(reconnectTimerRef.current);
    clearTimeout(initWatchdogRef.current);
    clearInterval(tokenRefreshRef.current);
    userStreamRef.current?.getTracks().forEach((t) => t.stop());
    screenStreamRef.current?.getTracks().forEach((t) => t.stop());
  }, []);

  // ── Start interview ─────────────────────────────────────────────────
  const startInterview = useCallback(async (resumeExisting = true) => {
    setPhase('initializing');
    setInitStep(0);
    setStatusMessage('Creating your interview session…');
    setError(null);
    setSubtitleText('');
    clearInitWatchdog();
    armInitWatchdog(45, 'Obi is taking too long to connect. Please try again.');
    startProctoring();

    try {
      const shouldResume = resumeExisting && Boolean(resumableSession);
      const endpoint = shouldResume ? '/ai-interview/resume' : '/ai-interview/start';
      const url = `${API_BASE}${endpoint}`;
      const body = shouldResume
        ? JSON.stringify({ interview_session_id: resumableSession, session_id: sessionId })
        : JSON.stringify({
            session_id: sessionId,
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
        let detail = res.statusText;
        try {
          const errBody = await res.json();
          detail = errBody.detail || errBody.message || detail;
        } catch { /* keep statusText */ }
        throw new Error(`Failed to initialize interview: ${detail}`);
      }

      const data = await res.json();
      const ivSessionId = data.interview_session_id;
      setInterviewSessionId(ivSessionId);
      setInitStep(1);
      setStatusMessage('Connecting to Obi…');
      setDiag((d) => ({ ...d, session: 'ok' }));
      if (data.status === 'resumable' && !resumableSession) {
        setResumableSession(ivSessionId);
      }

      const wsUrl = `${getWsBase()}/ai-interview/ws/voice?token=${token}&interview_session_id=${ivSessionId}&session_id=${sessionId}`;
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        console.log('[AIInterviewer] WebSocket connected');
        setIsConnected(true);
        reconnectAttemptsRef.current = 0;
        setReconnectAttempts(0);
        setPhase('opening');
        setInitStep(2);
        setStatusMessage('Opening your voice channel…');
        setDiag((d) => ({ ...d, ws: 'ok' }));
      };

      ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          handleWsMessage(JSON.parse(event.data));
        } else {
          handleAudioResponse(event.data);
        }
        setDiag((d) => ({ ...d, wsMessages: d.wsMessages + 1 }));
      };

      ws.onerror = () => {
        console.error('[AIInterviewer] WebSocket error');
        setError('Connection error. Please refresh and try again.');
        setPhase('error');
      };

      ws.onclose = () => {
        console.log('[AIInterviewer] WebSocket closed');
        setIsConnected(false);
        setDiag((d) => ({ ...d, ws: 'error' }));
        if (phaseRef.current !== 'completed' && phaseRef.current !== 'error') {
          reconnectTimerRef.current = setTimeout(() => {
            if (wsRef.current === ws) reconnectWs();
          }, 2000);
        }
      };
    } catch (err) {
      console.error('[AIInterviewer] Start failed', err);
      setError(err.message);
      setPhase('error');
    }
  }, [sessionId, token, role, company, voiceMode, resumableSession, handleWsMessage, handleAudioResponse, reconnectWs, startProctoring, clearInitWatchdog, armInitWatchdog]);

  // ── Send text answer ────────────────────────────────────────────────
  const sendAnswer = useCallback((text) => {
    if (!text || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    addMessage({ role: 'candidate', text, ts: Date.now() / 1000 });
    setIsThinking(true);
    setSubtitleText(text);

    wsRef.current.send(JSON.stringify({
      type: 'answer',
      text,
      code: code || undefined,
      language: code ? language : undefined,
    }));
  }, [code, language, addMessage]);

  // ── Retry after an error ────────────────────────────────────────────
  const retryFromError = useCallback(() => {
    setError(null);
    setDiag((d) => ({ ...d, lastMessage: 'retrying' }));
    if (interviewSessionId && sessionId && token) {
      reconnectAttemptsRef.current = 0;
      setReconnectAttempts(0);
      setPhase('opening');
      setInitStep(2);
      setStatusMessage('Reconnecting to Obi…');
      reconnectWs();
    } else {
      setPhase('onboarding');
    }
  }, [interviewSessionId, sessionId, token, reconnectWs]);

  // ── Run code ────────────────────────────────────────────────────────
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

  // ── Voice recording ─────────────────────────────────────────────────
  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      let mime = 'audio/webm;codecs=opus';
      if (typeof MediaRecorder !== 'undefined' && !MediaRecorder.isTypeSupported(mime)) {
        mime = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : '';
      }
      const recorder = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
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
        stream.getTracks().forEach((t) => t.stop());
      };

      recorder.start(250);
      setIsRecording(true);
      setMicPermission('granted');
      setError(null);
    } catch (err) {
      console.error('[AIInterviewer] Microphone access failed', err);
      setMicPermission('denied');
      // Keep the interview alive — the candidate can fall back to typing.
      setError(
        err?.name === 'NotAllowedError'
          ? 'Microphone access was denied. You can still answer by typing below, or allow the mic and press the mic button again.'
          : 'Microphone unavailable. You can still answer by typing below.'
      );
    }
  }, [code, language]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  }, []);

  // ── End interview ───────────────────────────────────────────────────
  const endInterview = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'end_voice' }));
      setIsThinking(true);
      setPhase('completing');
      armInitWatchdog(150, 'Obi took too long to prepare your report. Please try again.');
    }
  }, [armInitWatchdog]);

  // ── Auto-scroll chat ────────────────────────────────────────────────
  useEffect(() => {
    if (activeTab === 'chat') {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [messages, isThinking, activeTab]);

  // ── Cleanup ─────────────────────────────────────────────────────────
  useEffect(() => () => {
    wsRef.current?.close();
    audioContextRef.current?.close();
    clearTimeout(reconnectTimerRef.current);
    clearTimeout(fallbackTtsTimeoutRef.current);
    clearInterval(tokenRefreshRef.current);
    clearInterval(lipSyncIntervalRef.current);
  }, []);

  // ── Derived render state ────────────────────────────────────────────
  const avatarMode = isRecording
    ? 'listening'
    : isSpeaking
      ? 'speaking'
      : isThinking
        ? 'thinking'
        : phase === 'initializing' || phase === 'opening'
          ? 'connecting'
          : 'idle';

  const isConnectingPhase = phase === 'initializing' || phase === 'opening';

  // ── RENDER ──────────────────────────────────────────────────────────
  if (phase === 'error') {
    return <ErrorScreen error={proctorError || error} onRetry={retryFromError} />;
  }

  if (phase === 'completed' && finalReport) {
    return <FinalReportView finalReport={finalReport} onComplete={onComplete} />;
  }

  if (phase === 'onboarding') {
    return (
      <OnboardingWizard
        step={onboardingStep}
        setStep={setOnboardingStep}
        micPermission={micPermission}
        micLevelActive={micLevelActive}
        setMicLevelActive={setMicLevelActive}
        setMicPermission={setMicPermission}
        role={role}
        company={company}
        resume={resume}
        resumableSession={resumableSession}
        startInterview={startInterview}
        error={error}
      />
    );
  }

  return (
    <div className="oiv-shell oiv-shell--room">
      <ProctoringModal modal={proctor.modal} onClose={proctor.dismissModal} />

      {/* Top bar */}
      <header className="oiv-topbar">
        <div className="oiv-topbar__left">
          <div className="oiv-mini">
            <ObiAvatar mode={avatarMode} size="mini" />
          </div>
          <div className="oiv-topbar__titles">
            <span className="oiv-topbar__name">Obi</span>
            <span className="oiv-topbar__role">Senior Engineer · AI Interviewer</span>
          </div>
        </div>

        <InterviewStatus
          isRecording={isRecording}
          isSpeaking={isSpeaking}
          isThinking={isThinking}
          isProcessing={isProcessing}
          isConnecting={isConnectingPhase}
          elapsedSec={elapsedSec}
          progress={progress}
          stage={currentStage}
          proctoring={proctoring}
          connected={isConnected}
        />

        <div className="oiv-topbar__right">
          <div className="oiv-settings" >
            <button
              type="button"
              className="oiv-icon-btn"
              onClick={() => setShowSettings((v) => !v)}
              title="Settings"
              aria-label="Settings"
            >
              <Settings2 size="17" />
            </button>
            {showSettings && (
              <div className="oiv-settings__pop">
                <label className="oiv-settings__row">
                  <Volume2 size="15" />
                  <span>Browser voice fallback</span>
                  <input
                    type="checkbox"
                    checked={browserTtsFallback}
                    onChange={(e) => setBrowserTtsFallback(e.target.checked)}
                  />
                </label>
                {import.meta.env.DEV && (
                  <label className="oiv-settings__row">
                    <Settings2 size="15" />
                    <span>Dev diagnostics</span>
                    <input
                      type="checkbox"
                      checked={showDiag}
                      onChange={(e) => setShowDiag(e.target.checked)}
                    />
                  </label>
                )}
              </div>
            )}
          </div>
          <button
            type="button"
            className="oiv-end-btn"
            onClick={endInterview}
            disabled={phase !== 'interviewing'}
            title="End Interview"
          >
            <XCircle size="14" /> End
          </button>
        </div>
      </header>

      {error && phase !== 'error' && (
        <div className="oiv-room-error">
          <AlertTriangle size="15" />
          <span>{error}</span>
        </div>
      )}

      {showDiag && import.meta.env.DEV && (
        <DiagnosticsPanel
          status={diag}
          phase={phase}
          statusMessage={statusMessage}
          connected={isConnected}
          micPermission={micPermission}
          camActive={Boolean(userStream?.getVideoTracks?.().some((t) => t.readyState === 'live'))}
          faceActive={Boolean(proctor.status?.faceDetectionActive)}
        />
      )}

      <div className="oiv-room__main">
        {/* Stage — the hero area */}
        <section className="oiv-stage">
          {isConnectingPhase && (
            <div className="oiv-connect-overlay">
              <ObiAvatar mode="connecting" size="med" />
              <div className="oiv-connect-overlay__text">
                <div className="oiv-chat__spinner" />
                <p className="oiv-connect-overlay__status">{statusMessage || 'Preparing your interview…'}</p>
                <ol className="oiv-init-steps">
                  {[
                    'Creating your session',
                    'Connecting to Obi',
                    'Opening your voice channel',
                  ].map((label, i) => (
                    <li
                      key={label}
                      className={i < initStep ? 'done' : i === initStep ? 'active' : 'pending'}
                    >
                      <span className="oiv-init-steps__dot" />
                      {label}
                    </li>
                  ))}
                </ol>
              </div>
            </div>
          )}

          {phase === 'completing' && (
            <div className="oiv-connect-overlay">
              <ObiAvatar mode="thinking" size="med" />
              <div className="oiv-connect-overlay__text">
                <div className="oiv-chat__spinner" />
                <p>Obi is preparing your interview report…</p>
              </div>
            </div>
          )}

          <div className="oiv-stage__scene">
            <ObiAvatar mode={avatarMode} lipLevel={lipLevel} size="hero" />

            <SubtitleCard
              subtitleText={subtitleText}
              isSpeaking={isSpeaking}
              isRecording={isRecording}
              isThinking={isThinking}
              isProcessing={isProcessing}
              isConnecting={isConnectingPhase}
            />

            {currentStage && (
              <span className="oiv-stage-badge">{currentStage}</span>
            )}
          </div>

          {phase === 'interviewing' && (
            <InputDock
              isRecording={isRecording}
              startRecording={startRecording}
              stopRecording={stopRecording}
              isThinking={isThinking}
              isSpeaking={isSpeaking}
              sendAnswer={sendAnswer}
              textInputRef={textInputRef}
            />
          )}
        </section>

        {/* Secondary drawer — chat / code */}
        <aside className={`oiv-drawer ${drawerOpen ? 'oiv-drawer--open' : ''}`}>
          <div className="oiv-drawer__head">
            <div className="oiv-drawer__tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'chat'}
                className={`oiv-tab-btn ${activeTab === 'chat' ? 'oiv-tab-btn--active' : ''}`}
                onClick={() => setActiveTab('chat')}
              >
                <MessageSquare size="14" /> Chat
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeTab === 'code'}
                className={`oiv-tab-btn ${activeTab === 'code' ? 'oiv-tab-btn--active' : ''}`}
                onClick={() => setActiveTab('code')}
              >
                <Code2 size="14" /> Code {codingProblem && <span className="oiv-tab-btn__dot" />}
              </button>
            </div>
            <button
              type="button"
              className="oiv-drawer__close"
              onClick={() => setDrawerOpen(false)}
              title="Collapse panel"
              aria-label="Collapse panel"
            >
              <PanelRightClose size="16" />
            </button>
          </div>

          <div className="oiv-drawer__body">
            {activeTab === 'chat' ? (
              <ChatPanel
                messages={messages}
                isThinking={isThinking}
                phase={phase}
                statusMessage={statusMessage}
                messagesEndRef={messagesEndRef}
              />
            ) : (
              <CodePanel
                codingProblem={codingProblem}
                language={language}
                setLanguage={setLanguage}
                code={code}
                setCode={setCode}
                runCode={runCode}
                isRunning={isRunning}
                runStatus={runStatus}
                runOutput={runOutput}
                stdin={stdin}
                setStdin={setStdin}
                isThinking={isThinking}
                onSubmitCode={() => {
                  const submission = `Here is my code solution in ${language}:\n\`\`\`${language}\n${code}\n\`\`\`\nExecution Output:\n${runOutput || '(Code executed)'}`;
                  sendAnswer(submission);
                  setActiveTab('chat');
                }}
              />
            )}
          </div>
        </aside>
      </div>

      {/* Floating drawer toggle */}
      {!drawerOpen && (
        <button
          type="button"
          className="oiv-drawer-toggle"
          onClick={() => setDrawerOpen(true)}
          title="Open transcript & code"
          aria-label="Open transcript and code panel"
        >
          <PanelRightOpen size="18" />
          <span>{activeTab === 'chat' ? 'Chat' : 'Code'}</span>
        </button>
      )}

      {/* Hidden webcam feed for proctoring */}
      <video ref={videoRef} autoPlay muted playsInline style={{ display: 'none' }} />
    </div>
  );
}
