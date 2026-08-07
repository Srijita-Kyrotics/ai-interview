import React from 'react';

// ─────────────────────────────────────────────────────────────────────────────
// OBI — Animated AI Interviewer Avatar
// Pure CSS/SVG robot rendered from divs. States:
//   idle · connecting · listening · thinking · speaking
// The `lipLevel` prop (0..1) drives the mouth aperture while speaking.
// ─────────────────────────────────────────────────────────────────────────────

export default function ObiAvatar({
  mode = 'idle',
  lipLevel = 0,
  size = 'hero',
  ariaLabel = 'Obi, your AI interviewer',
}) {
  const validMode = ['idle', 'connecting', 'listening', 'thinking', 'speaking'].includes(mode) ? mode : 'idle';
  const lip = Math.max(0, Math.min(1, lipLevel));

  return (
    <div
      className={`oiv-avatar oiv-avatar--${size} oiv-avatar--${validMode}`}
      role="img"
      aria-label={ariaLabel}
      style={{ '--lip': lip }}
    >
      {/* Ambient halo + animated orbit rings */}
      <div className="oiv-avatar__halo" aria-hidden="true" />
      <div className="oiv-avatar__ring oiv-avatar__ring--outer" aria-hidden="true" />
      <div className="oiv-avatar__ring oiv-avatar__ring--inner" aria-hidden="true" />

      {/* The physical bot */}
      <div className="oiv-avatar__body" aria-hidden="true">
        <div className="oiv-avatar__antenna">
          <span className="oiv-avatar__antenna-rod" />
          <span className="oiv-avatar__antenna-tip" />
        </div>

        <div className="oiv-avatar__ears">
          <span className="oiv-avatar__ear oiv-avatar__ear--l" />
          <span className="oiv-avatar__ear oiv-avatar__ear--r" />
        </div>

        <div className="oiv-avatar__head">
          <div className="oiv-avatar__visor" />
          <div className="oiv-avatar__face">
            <div className="oiv-avatar__eye oiv-avatar__eye--l">
              <span className="oiv-avatar__pupil" />
              <span className="oiv-avatar__lid" />
            </div>
            <div className="oiv-avatar__eye oiv-avatar__eye--r">
              <span className="oiv-avatar__pupil" />
              <span className="oiv-avatar__lid" />
            </div>

            <div className="oiv-avatar__mouth">
              <span className="oiv-avatar__mouth-dots">
                <i /><i /><i />
              </span>
              <span className="oiv-avatar__mouth-oval" />
            </div>

            <span className="oiv-avatar__cheek oiv-avatar__cheek--l" />
            <span className="oiv-avatar__cheek oiv-avatar__cheek--r" />
          </div>
        </div>

        <div className="oiv-avatar__neck" />
        <div className="oiv-avatar__torso">
          <div className="oiv-avatar__core">
            <span className="oiv-avatar__core-light" />
          </div>
          <span className="oiv-avatar__torso-vents">
            <i /><i /><i />
          </span>
        </div>
      </div>
    </div>
  );
}
