import React, { useEffect, useState } from 'react'
import { ArrowLeft, MessageSquare, AlertTriangle } from 'lucide-react'
import { api } from '../api'

function SessionReplay({ sessionId, sessionName, onBack }) {
  const [timeline, setTimeline] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/admin/sessions/${sessionId}/timeline`)
      .then(r => { setTimeline(r.timeline || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [sessionId])

  if (loading) {
    return (
      <section className="panel main-panel">
        <div className="section-head"><div><h2>Loading timeline...</h2></div></div>
        <div className="empty-state"><div className="loading-spinner" /></div>
      </section>
    )
  }

  return (
    <section className="panel main-panel">
      <div className="section-head">
        <div>
          <button className="btn ghost" type="button" onClick={onBack} style={{ marginBottom: '0.5rem' }}>
            <ArrowLeft size={16} style={{ marginRight: 6, verticalAlign: 'middle' }} /> Back to Sessions
          </button>
          <p className="eyebrow">Session Replay</p>
          <h2>{sessionName || sessionId}</h2>
          <p className="muted">{timeline.length} events recorded</p>
        </div>
      </div>
      {timeline.length === 0 ? (
        <div className="empty-state"><p>No timeline events found for this session.</p></div>
      ) : (
        <div className="replay-timeline">
          {timeline.map((entry, idx) => (
            <div key={idx} className={`replay-entry ${entry.type === 'violation' ? 'replay-entry--violation' : 'replay-entry--answer'}`}>
              <div className="replay-dot" />
              <div className="replay-content">
                <div className="replay-header">
                  <span className={`replay-badge ${entry.type === 'violation' ? 'replay-badge--error' : 'replay-badge--info'}`}>
                    {entry.type === 'violation' ? <AlertTriangle size={12} /> : <MessageSquare size={12} />}
                    {entry.type === 'violation' ? 'Violation' : entry.round}
                  </span>
                  <span className="replay-step">Step {entry.step}</span>
                </div>
                {entry.type === 'violation' ? (
                  <p className="replay-text">{entry.event}</p>
                ) : (
                  <p className="replay-text">{entry.answer?.slice(0, 500)}{entry.answer?.length > 500 ? '...' : ''}</p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

export { SessionReplay }
