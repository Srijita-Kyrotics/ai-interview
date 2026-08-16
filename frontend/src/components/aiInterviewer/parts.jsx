import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  Clock,
  Code2,
  ListChecks,
  MessageSquare,
  Target,
  TrendingUp,
  Zap,
} from 'lucide-react';

// ── Waveform visualizer (canvas) ─────────────────────────────────────────────
export const WaveformVisualizer = ({ isActive, color = '#6366f1' }) => {
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

// ── Rich text rendering (bold + inline code + fenced code blocks) ───────────
export const renderInline = (text) => {
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

export const RichText = ({ text }) => {
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

// ── Animated count-up hook for report scores ────────────────────────────────
export const useCountUp = (target, duration = 1200) => {
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

export const ScoreGauge = ({ label, score, color }) => {
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

// ── Chat bubbles ─────────────────────────────────────────────────────────────
export const MessageBubble = ({ message }) => {
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

export const ThinkingIndicator = () => (
  <div className="aii-thinking">
    <div className="aii-bubble__avatar"><span>O</span><i className="aii-bubble__avatar-dot" /></div>
    <div className="aii-thinking__dots">
      <span />
      <span />
      <span />
    </div>
  </div>
);

// ── Status pill (header) ─────────────────────────────────────────────────────
export const LiveStatusPill = ({ isRecording, isSpeaking, isThinking, isProcessing, isConnecting }) => {
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

// ── Stage progress bar ───────────────────────────────────────────────────────
export const ProgressBar = ({ current, total, stages }) => {
  const pct = total > 0 ? Math.min((current / total) * 100, 100) : 0;
  return (
    <div className="aii-progress">
      <div className="aii-progress__bar">
        <div className="aii-progress__fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="aii-progress__info">
        <span>Stage {current} of {total}</span>
        {stages?.currentStage && <span className="aii-progress__stage">{stages.currentStage}</span>}
      </div>
    </div>
  );
};

// ── Final report ─────────────────────────────────────────────────────────────
export const FinalReportView = ({ finalReport, onComplete }) => {
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
