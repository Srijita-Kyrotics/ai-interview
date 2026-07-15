import React from 'react'

export function ProctoringPanel({ proctoring }) {
  if (!proctoring?.currentRound) return null

  return (
    <aside className="proctor-panel" aria-label="Proctoring dashboard">
      <div className="proctor-panel-head">
        <span>Proctoring</span>
        <strong>{proctoring.currentRound}</strong>
      </div>
      <div className="proctor-stats">
        <div><span>Warnings</span><b>{Math.min(proctoring.warnings, 3)}/3</b></div>
        <div><span>Integrity</span><b>{proctoring.integrityScore}%</b></div>
        <div><span>Violations</span><b>{proctoring.violations.length}</b></div>
      </div>
      <div className="proctor-signals">
        <span className={proctoring.cameraActive ? 'active' : ''}>Camera: {proctoring.cameraActive ? 'Active' : 'Inactive'}</span>
        <span className={proctoring.screenShareActive ? 'active' : ''}>Screen Share: {proctoring.screenShareActive ? 'Active' : 'Inactive'}</span>
        <span className={proctoring.faceDetectionActive ? 'active' : ''}>Face Detection: {proctoring.faceDetectionActive ? 'Active' : 'Standby'}</span>
      </div>
    </aside>
  )
}

export function ProctoringModal({ modal, onClose }) {
  if (!modal) return null

  const isTerminated = modal.type === 'terminated'
  const isWarning    = modal.type === 'warning'

  return (
    <div
      className={`proctoring-toast ${isTerminated ? 'proctoring-toast--terminated' : 'proctoring-toast--warning'}`}
      role="alert"
      aria-live="assertive"
    >
      <style>{`
        .proctoring-toast {
          position: fixed;
          top: 20px;
          left: 50%;
          transform: translateX(-50%);
          z-index: 9999;
          min-width: 320px;
          max-width: 500px;
          padding: 18px 24px;
          border-radius: 16px;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 8px;
          text-align: center;
          backdrop-filter: blur(20px);
          animation: toastSlideDown 0.35s cubic-bezier(0.34,1.56,0.64,1) both;
          box-shadow: 0 20px 60px rgba(0,0,0,0.5);
        }
        @keyframes toastSlideDown {
          from { top: -120px; opacity: 0; }
          to   { top: 20px;   opacity: 1; }
        }
        .proctoring-toast--warning {
          background: rgba(30,16,0,0.92);
          border: 1px solid rgba(245,158,11,0.5);
          box-shadow: 0 20px 60px rgba(0,0,0,0.5), 0 0 40px rgba(245,158,11,0.2);
        }
        .proctoring-toast--terminated {
          background: rgba(30,0,0,0.95);
          border: 1px solid rgba(239,68,68,0.55);
          box-shadow: 0 20px 60px rgba(0,0,0,0.6), 0 0 60px rgba(239,68,68,0.3);
        }
        .proctoring-toast h3 {
          margin: 0;
          font-size: 1.1rem;
          font-weight: 800;
          letter-spacing: 0.04em;
          color: #fff;
        }
        .proctoring-toast--warning h3 { color: #fbbf24; }
        .proctoring-toast--terminated h3 { color: #f87171; }
        .proctoring-toast p {
          margin: 0;
          font-size: 0.9rem;
          color: rgba(255,255,255,0.8);
          line-height: 1.55;
        }
        .proctoring-toast-dismiss {
          margin-top: 8px;
          padding: 7px 18px;
          border: 1px solid rgba(255,255,255,0.25);
          border-radius: 999px;
          background: rgba(255,255,255,0.10);
          color: #fff;
          cursor: pointer;
          font-size: 0.82rem;
          font-weight: 600;
          transition: background 0.2s;
        }
        .proctoring-toast-dismiss:hover { background: rgba(255,255,255,0.20); }
      `}</style>
      <h3>{isTerminated ? '⚠ TEST TERMINATED' : `⚠ Malpractice Warning ${modal.warning}/3`}</h3>
      <p>{modal.reason}</p>
      {!isTerminated && (
        <button className="proctoring-toast-dismiss" onClick={onClose}>
          I understand
        </button>
      )}
    </div>
  )
}

export function ViolationTimeline({ logs = [] }) {
  if (!logs.length) return <p className="muted">No proctoring events were recorded.</p>
  return (
    <div className="violation-timeline">
      {logs.map((log, index) => (
        <div key={`${log.time}-${index}`} className="violation-entry">
          <strong style={{ color: '#f87171', marginRight: 8 }}>{log.time}</strong>
          <span style={{ color: '#e2e8f0' }}>{log.event}</span>
          {log.reason && <small style={{ display: 'block', color: '#64748b', marginTop: 4 }}>{log.reason}</small>}
        </div>
      ))}
    </div>
  )
}

export function SnapshotGrid({ snapshots = [] }) {
  if (!snapshots.length) return <p className="muted">No violation snapshots were captured.</p>
  return (
    <div className="snapshot-grid">
      {snapshots.map((snapshot, index) => (
        <figure key={`${snapshot.timestamp}-${index}`} style={{ margin: 0 }}>
          {snapshot.image ? <img src={snapshot.image} alt={`Violation snapshot ${index + 1}`} /> : null}
          <figcaption style={{ marginTop: 6, fontSize: '0.75rem' }}>
            <strong style={{ display: 'block', color: '#f87171' }}>{snapshot.reason}</strong>
            <span style={{ color: '#64748b' }}>{new Date(snapshot.timestamp).toLocaleString()}</span>
          </figcaption>
        </figure>
      ))}
    </div>
  )
}
