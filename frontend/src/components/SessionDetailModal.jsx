import React, { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../api'
import { scoreClass } from '../utils/score'

function SessionDetailModal({ sessionId, onClose }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/user/sessions/${sessionId}`).then(r => { setDetail(r); setLoading(false) }).catch(() => setLoading(false))
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

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>{report.selectedCompany || 'Interview'} Report</h3>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        </div>

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

        {report.strengths?.length > 0 && (
          <div className="feedback-section">
            <div className="feedback-title" style={{ color: 'var(--success)' }}>Strengths</div>
            {report.strengths.map((s, i) => <div key={i} className="feedback-item">+ {s}</div>)}
          </div>
        )}

        {report.weaknesses?.length > 0 && (
          <div className="feedback-section">
            <div className="feedback-title" style={{ color: 'var(--error)' }}>Weaknesses</div>
            {report.weaknesses.map((w, i) => <div key={i} className="feedback-item">- {w}</div>)}
          </div>
        )}

        {detail.proctoring && (
          <div className="proctoring-detail-grid" style={{ marginTop: '1rem' }}>
            <div className="proctoring-detail-item">
              <div className="detail-label">Integrity Score</div>
              <div className={`detail-value ${scoreClass(detail.proctoring.integrity_score || 100)}`}>
                {detail.proctoring.integrity_score || 100}%
              </div>
            </div>
            <div className="proctoring-detail-item">
              <div className="detail-label">Status</div>
              <div className="detail-value" style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-primary)' }}>
                {detail.proctoring.assessment_status || 'N/A'}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export { SessionDetailModal }
