import React from 'react';
import { Clock, ShieldCheck, ListChecks, Wifi, WifiOff } from 'lucide-react';

// ─────────────────────────────────────────────────────────────────────────────
// COMPACT INTERVIEW STATUS
// One-line, production-grade status cluster: live state pill + elapsed time +
// question progress + integrity chip. Replaces the old floating debug panels.
// ─────────────────────────────────────────────────────────────────────────────

function StatePill({ isRecording, isSpeaking, isThinking, isProcessing, isConnecting }) {
  let label = 'Connected';
  let tone = 'idle';
  if (isRecording) { label = 'Listening'; tone = 'listening'; }
  else if (isProcessing) { label = 'Transcribing'; tone = 'processing'; }
  else if (isSpeaking) { label = 'Speaking'; tone = 'speaking'; }
  else if (isThinking) { label = 'Thinking'; tone = 'thinking'; }
  else if (isConnecting) { label = 'Connecting'; tone = 'connecting'; }

  return (
    <span className={`oiv-status-pill oiv-status-pill--${tone}`} title={label}>
      <span className="oiv-status-pill__dot" />
      {label}
    </span>
  );
}

function IntegrityChip({ proctoring }) {
  const score = proctoring?.integrityScore ?? 100;
  const tone = score >= 90 ? 'good' : score >= 70 ? 'warn' : 'bad';
  const label = proctoring?.assessmentStatus === 'Terminated Due To Malpractice'
    ? 'Terminated'
    : `Integrity ${score}%`;

  return (
    <span
      className={`oiv-integrity oiv-integrity--${tone}`}
      title={proctoring?.violations?.length
        ? `${proctoring.violations.length} violation(s) recorded`
        : 'No proctoring violations'}
    >
      {tone === 'bad' ? <ShieldCheck size="13" /> : <ShieldCheck size="13" />}
      {label}
    </span>
  );
}

export default function InterviewStatus({
  isRecording,
  isSpeaking,
  isThinking,
  isProcessing,
  isConnecting,
  elapsedSec,
  progress,
  stage,
  proctoring,
  connected,
}) {
  const formatElapsed = (sec) => {
    const m = Math.floor(sec / 60).toString().padStart(2, '0');
    const s = (sec % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  return (
    <div className="oiv-status" aria-label="Interview status">
      <StatePill
        isRecording={isRecording}
        isSpeaking={isSpeaking}
        isThinking={isThinking}
        isProcessing={isProcessing}
        isConnecting={isConnecting}
      />

      <span className="oiv-status__chip" title="Elapsed time">
        <Clock size="13" />
        {formatElapsed(elapsedSec)}
      </span>

      <span className="oiv-status__chip" title="Questions answered">
        <ListChecks size="13" />
        {progress.current}/{progress.total}
      </span>

      {stage && <span className="oiv-status__stage">{stage}</span>}

      <span className={`oiv-status__conn ${connected ? 'oiv-status__conn--on' : 'oiv-status__conn--off'}`} title={connected ? 'Connected to Obi' : 'Reconnecting…'}>
        {connected ? <Wifi size="13" /> : <WifiOff size="13" />}
      </span>

      <IntegrityChip proctoring={proctoring} />
    </div>
  );
}
