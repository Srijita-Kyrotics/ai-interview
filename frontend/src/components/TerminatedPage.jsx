import React from 'react'
import { useNavigate } from 'react-router-dom'
import { loadProctoringState, resetProctoringState } from '../proctoring/proctoringState'

function TerminatedPage() {
  const navigate = useNavigate()
  const proctoring = loadProctoringState()
  const reason = proctoring.terminatedReason || 'Repeated malpractice detection (tab switching, loss of focus, or exiting fullscreen).'
  const warningCount = proctoring.warnings || 3
  const integrity = proctoring.integrityScore ?? 100

  return (
    <div className="termination-screen">
      <div className="termination-card">
        <div className="termination-icon">⚠</div>
        <div className="termination-title">Interview Ended</div>
        <div className="termination-message">
          <p>You received {warningCount} warning{warningCount === 1 ? '' : 's'} during the interview. On the final warning, the interview was ended automatically.</p>
          <p className="termination-reason">{reason}</p>
          <p className="termination-integrity">Integrity score: {integrity}%</p>
        </div>
        <button
          className="btn primary"
          type="button"
          onClick={() => {
            resetProctoringState()
            navigate('/', { replace: true })
          }}
        >
          Return to Dashboard
        </button>
      </div>
    </div>
  )
}

export { TerminatedPage }
