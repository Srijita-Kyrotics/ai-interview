import React from 'react'

function TerminatedPage() {
  return (
    <div className="termination-screen">
      <div className="termination-card">
        <div className="termination-icon">⚠</div>
        <div className="termination-title">Test Terminated</div>
        <div className="termination-message">
          Your assessment has been terminated due to repeated malpractice detection (tab switching, loss of focus, or exiting fullscreen).
        </div>
        <button className="btn ghost" type="button" onClick={() => window.location.href = '/'}>
          Return to Dashboard
        </button>
      </div>
    </div>
  )
}

export { TerminatedPage }
