import React, { useEffect } from 'react'

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
  useEffect(() => {
    if (!modal) return
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [modal, onClose])

  if (!modal) return null

  const isTerminated = modal.type === 'terminated'
  const isWarning    = modal.type === 'warning'

  return (
    <div
      className={`proctoring-toast ${isTerminated ? 'proctoring-toast--terminated' : 'proctoring-toast--warning'}`}
      role="alert"
      aria-live="assertive"
    >
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
          <strong className="violation-entry-time">{log.time}</strong>
          <span className="violation-entry-event">{log.event}</span>
          {log.reason && <small className="violation-entry-reason">{log.reason}</small>}
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
        <figure key={`${snapshot.timestamp}-${index}`} className="snapshot-figure">
          {snapshot.image ? <img src={snapshot.image} alt={`Violation snapshot ${index + 1}`} /> : null}
          <figcaption className="snapshot-figcaption">
            <strong className="snapshot-figcaption-reason">{snapshot.reason}</strong>
            <span className="snapshot-figcaption-time">{new Date(snapshot.timestamp).toLocaleString()}</span>
          </figcaption>
        </figure>
      ))}
    </div>
  )
}
