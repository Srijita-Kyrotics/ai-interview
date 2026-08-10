import React, { useId } from 'react';

const WAVE_BARS = 26;

const STATE_LABELS = {
  connecting: 'Connecting to Obi…',
  idle: 'Obi is ready',
  listening: 'Listening…',
  thinking: 'Thinking…',
  speaking: 'Obi is speaking',
  error: 'Reconnecting…',
};

/**
 * ObiAvatar — the animated AI interviewer character.
 *
 * A pure-SVG humanoid robot with expressive glowing eyes, a moving mouth,
 * antenna, and small arms. It is fully driven by the interview pipeline:
 *
 *   state      → connecting | idle | listening | thinking | speaking | error
 *   lipLevel   → 0..1 mouth openness (fed by the live TTS analyser or the
 *                speechSynthesis lip-sync fallback)
 *   audioLevel → 0..1 real-time TTS loudness (drives the waveform bars)
 */
export default function ObiAvatar({ state = 'idle', lipLevel = 0, audioLevel = 0, statusText = '', compact = false }) {
  const uid = useId().replace(/[:]/g, '');
  const mouthScale = 0.3 + Math.min(Math.max(lipLevel, 0), 1) * 1.15;
  const dancing = state === 'speaking' && audioLevel <= 0.03;
  const label = (state === 'connecting' || state === 'error' || state === 'idle') && statusText
    ? statusText
    : STATE_LABELS[state] || 'Obi is ready';

  return (
    <div className={`obi-avatar${compact ? ' obi-avatar--compact' : ''}`} data-state={state}>
      <div className="obi-avatar__scene">
        <div className="obi-avatar__processing" aria-hidden="true" />
        <svg
          className="obi-avatar__svg"
          viewBox="0 0 220 250"
          role="img"
          aria-label="Obi, your AI technical interviewer"
        >
          <defs>
            <linearGradient id={`${uid}body`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3b4a82" />
              <stop offset="55%" stopColor="#232a4d" />
              <stop offset="100%" stopColor="#141a33" />
            </linearGradient>
            <linearGradient id={`${uid}body2`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2c3560" />
              <stop offset="100%" stopColor="#161c38" />
            </linearGradient>
            <linearGradient id={`${uid}eye`} x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="#a5f3fc" />
              <stop offset="45%" stopColor="#38bdf8" />
              <stop offset="100%" stopColor="#6366f1" />
            </linearGradient>
            <linearGradient id={`${uid}core`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#c4b5fd" />
              <stop offset="55%" stopColor="#818cf8" />
              <stop offset="100%" stopColor="#6366f1" />
            </linearGradient>
            <linearGradient id={`${uid}antenna`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#7dd3fc" />
              <stop offset="100%" stopColor="#38bdf8" />
            </linearGradient>
            <filter id={`${uid}glow`} x="-60%" y="-60%" width="220%" height="220%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id={`${uid}softGlow`} x="-80%" y="-80%" width="260%" height="260%">
              <feGaussianBlur stdDeviation="6" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          <g className="obi-avatar__float">
            <g className="obi-avatar__breathe">
              {/* Arms */}
              <path
                className="obi-avatar__arm"
                d="M66 146 Q40 152 34 176"
                fill="none"
                stroke={`url(#${uid}body2)`}
                strokeWidth="13"
                strokeLinecap="round"
              />
              <circle className="obi-avatar__hand" cx="33" cy="180" r="10" fill={`url(#${uid}body)`} stroke="#3d4a80" strokeWidth="1.5" />
              <path
                className="obi-avatar__arm"
                d="M154 146 Q180 152 186 176"
                fill="none"
                stroke={`url(#${uid}body2)`}
                strokeWidth="13"
                strokeLinecap="round"
              />
              <circle className="obi-avatar__hand" cx="187" cy="180" r="10" fill={`url(#${uid}body)`} stroke="#3d4a80" strokeWidth="1.5" />

              {/* Antenna */}
              <line x1="110" y1="36" x2="110" y2="16" stroke={`url(#${uid}antenna)`} strokeWidth="4" strokeLinecap="round" />
              <g className="obi-avatar__antenna-tip">
                <circle cx="110" cy="13" r="7" fill="#38bdf8" opacity="0.45" filter={`url(#${uid}softGlow)`} />
                <circle cx="110" cy="13" r="4.5" fill="#a5f3fc" filter={`url(#${uid}glow)`} />
                <circle cx="109" cy="11.5" r="1.6" fill="#ffffff" />
              </g>

              {/* Ears / side nodes */}
              <rect className="obi-avatar__ear" x="30" y="60" width="16" height="36" rx="8" fill={`url(#${uid}body2)`} stroke="#3d4a80" strokeWidth="1.5" />
              <rect className="obi-avatar__ear" x="174" y="60" width="16" height="36" rx="8" fill={`url(#${uid}body2)`} stroke="#3d4a80" strokeWidth="1.5" />

              {/* Head */}
              <g className="obi-avatar__head">
                <rect x="48" y="30" width="124" height="88" rx="36" fill={`url(#${uid}body)`} stroke="#49569a" strokeWidth="2" />
                <ellipse className="obi-avatar__head-shine" cx="80" cy="48" rx="30" ry="14" fill="#ffffff" opacity="0.06" />
                <rect x="52" y="34" width="116" height="10" rx="5" fill="#2a3259" opacity="0.85" />

                {/* Eyes */}
                <g className="obi-avatar__eyes">
                  <g className="obi-avatar__eye obi-avatar__eye--left">
                    <ellipse className="obi-avatar__socket" cx="82" cy="72" rx="14" ry="16" fill="#0b1026" />
                    <ellipse className="obi-avatar__eye-glow" cx="82" cy="72" rx="11" ry="13" fill={`url(#${uid}eye)`} filter={`url(#${uid}glow)`} />
                    <ellipse className="obi-avatar__iris" cx="82" cy="72" rx="4.5" ry="5.5" fill="#0c4a6e" />
                    <circle className="obi-avatar__eye-highlight" cx="78" cy="67" r="2.6" fill="#ffffff" />
                  </g>
                  <g className="obi-avatar__eye obi-avatar__eye--right">
                    <ellipse className="obi-avatar__socket" cx="138" cy="72" rx="14" ry="16" fill="#0b1026" />
                    <ellipse className="obi-avatar__eye-glow" cx="138" cy="72" rx="11" ry="13" fill={`url(#${uid}eye)`} filter={`url(#${uid}glow)`} />
                    <ellipse className="obi-avatar__iris" cx="138" cy="72" rx="4.5" ry="5.5" fill="#0c4a6e" />
                    <circle className="obi-avatar__eye-highlight" cx="134" cy="67" r="2.6" fill="#ffffff" />
                  </g>
                </g>

                {/* Mouth */}
                <g className="obi-avatar__mouth">
                  <rect x="87" y="96" width="46" height="14" rx="7" fill="#0b1026" />
                  <g className="obi-avatar__mouth-glow" style={{ transform: `scaleY(${mouthScale})` }}>
                    <rect x="91" y="97" width="38" height="12" rx="6" fill={`url(#${uid}eye)`} filter={`url(#${uid}glow)`} />
                    <rect x="95" y="99" width="30" height="8" rx="4" fill="#bae6fd" opacity="0.8" />
                  </g>
                </g>

                {/* Cheek accents */}
                <ellipse className="obi-avatar__cheek" cx="68" cy="94" rx="6" ry="3.4" fill="#818cf8" opacity="0.25" />
                <ellipse className="obi-avatar__cheek" cx="152" cy="94" rx="6" ry="3.4" fill="#818cf8" opacity="0.25" />
              </g>

              {/* Neck + Body */}
              <rect x="96" y="112" width="28" height="18" rx="6" fill="#1a2140" />
              <g className="obi-avatar__body">
                <path
                  d="M56 128 C56 108 164 108 164 128 L160 186 C160 206 60 206 60 186 Z"
                  fill={`url(#${uid}body)`}
                  stroke="#49569a"
                  strokeWidth="2"
                />
                <g className="obi-avatar__core">
                  <circle cx="110" cy="156" r="17" fill="#0b1026" />
                  <circle className="obi-avatar__core-glow" cx="110" cy="156" r="10.5" fill={`url(#${uid}core)`} filter={`url(#${uid}softGlow)`} />
                  <circle cx="110" cy="156" r="5.5" fill="#ede9fe" opacity="0.9" />
                  <circle cx="107.5" cy="153.5" r="2" fill="#ffffff" />
                </g>
                <rect x="72" y="176" width="76" height="4" rx="2" fill="#2c3560" opacity="0.8" />
                <rect x="72" y="182" width="54" height="4" rx="2" fill="#2c3560" opacity="0.5" />
              </g>
            </g>
          </g>

          <ellipse className="obi-avatar__shadow" cx="110" cy="236" rx="58" ry="8" fill="#000000" opacity="0.4" />
        </svg>
      </div>

      {/* Audio waveform */}
      {!compact && (
        <div className="obi-avatar__waveform" aria-hidden="true">
          {Array.from({ length: WAVE_BARS }).map((_, i) => {
            const live = state === 'speaking' && audioLevel > 0.03;
            const h = live
              ? Math.max(0.12, audioLevel * (0.4 + 0.6 * Math.abs(Math.sin(i * 0.55))) + 0.1)
              : state === 'speaking'
                ? 0.16
                : 0.07;
            return (
              <span
                key={i}
                className={dancing ? 'obi-avatar__wave-bar obi-avatar__wave-bar--dance' : 'obi-avatar__wave-bar'}
                style={{ height: `${Math.min(h, 1) * 100}%`, animationDelay: dancing ? `${i * 42}ms` : '0ms' }}
              />
            );
          })}
        </div>
      )}

      {!compact && (
        <div className="obi-avatar__label" role="status">
          {state === 'speaking' && <span className="obi-avatar__label-dot" />}
          {state === 'listening' && <span className="obi-avatar__label-dot obi-avatar__label-dot--mic" />}
          <span>{label}</span>
        </div>
      )}
    </div>
  );
}
