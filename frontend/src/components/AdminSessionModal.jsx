import React, { useEffect, useState } from 'react'
import { Shield, X } from 'lucide-react'
import { api } from '../api'

function scoreClass(score) {
  if (score >= 70) return 'score-good'
  if (score >= 50) return 'score-mid'
  return 'score-low'
}

function AdminSessionModal({ sessionId, modalType = 'report', onClose }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/admin/sessions/${sessionId}`).then(r => { setDetail(r); setLoading(false) }).catch(() => setLoading(false))
  }, [sessionId])

  if (loading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content" onClick={e => e.stopPropagation()} style={{ padding: '2rem', textAlign: 'center' }}>
          <div className="loading-spinner" />
        </div>
      </div>
    )
  }
  if (!detail?.session) return null

  const report = detail.session
  const scores = report.breakdown || report.scores || {}
  const proctoring = detail.proctoring

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>
            {modalType === 'proctoring' ? 'Proctoring Details' : 'Session Report'} — {report.candidateName || 'Candidate'}
          </h3>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </div>

        {/* Report View */}
        {modalType === 'report' && (
          <>
            <div className="score-grid">
              {Object.entries(scores).map(([key, val]) => (
                <div key={key} className="score-grid-item">
                  <div className="score-grid-label">{key}</div>
                  <div className={`score-grid-value ${scoreClass(val)}`}>{val}%</div>
                </div>
              ))}
            </div>

            <div className="overall-score-card">
              <div className="overall-label">Overall Score</div>
              <div className="overall-value">{report.overallScore}%</div>
            </div>

            {report.feedback && (
              <div className="feedback-section">
                <div className="feedback-title" style={{ color: 'var(--text-muted)' }}>AI Feedback</div>
                <p className="feedback-item" style={{ lineHeight: 1.6 }}>{typeof report.feedback === 'string' ? report.feedback : report.feedback.summary || ''}</p>
              </div>
            )}

            {report.recommendations?.length > 0 && (
              <div className="feedback-section">
                <div className="feedback-title" style={{ color: 'var(--primary)' }}>Recommendations</div>
                {report.recommendations.map((r, i) => <div key={i} className="feedback-item">+ {r}</div>)}
              </div>
            )}
          </>
        )}

        {/* Proctoring View */}
        {modalType === 'proctoring' && (
          <>
            {!proctoring ? (
              <div className="empty-state">
                <Shield size={40} />
                <p>No proctoring data available for this session</p>
              </div>
            ) : (
              <>
                <div className="proctoring-detail-grid">
                  <div className="proctoring-detail-item">
                    <div className="detail-label">Integrity Score</div>
                    <div className={`detail-value ${scoreClass(proctoring.integrity_score || 100)}`}>
                      {proctoring.integrity_score || 100}%
                    </div>
                  </div>
                  <div className="proctoring-detail-item">
                    <div className="detail-label">Status</div>
                    <div className="detail-value" style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                      {proctoring.assessment_status || 'N/A'}
                    </div>
                  </div>
                </div>

                {proctoring.violations?.length > 0 && (
                  <div className="feedback-section">
                    <div className="feedback-title" style={{ color: 'var(--error)' }}>Violations ({proctoring.violations.length})</div>
                    {proctoring.violations.map((v, i) => (
                      <div key={i} className="violation-item">
                        {v.type || v.message || JSON.stringify(v)}
                        {v.timestamp && <span className="violation-time">{new Date(v.timestamp * 1000).toLocaleTimeString()}</span>}
                      </div>
                    ))}
                  </div>
                )}

                {proctoring.snapshots?.length > 0 && (
                  <div>
                    <div className="feedback-title" style={{ color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Snapshots ({proctoring.snapshots.length})</div>
                    <div className="snapshot-grid">
                      {proctoring.snapshots.map((snap, i) => (
                        <div key={i} className="snapshot-thumb">
                          {snap.image ? <img src={snap.image} alt="" /> : <div className="snapshot-placeholder">No img</div>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export { AdminSessionModal }
