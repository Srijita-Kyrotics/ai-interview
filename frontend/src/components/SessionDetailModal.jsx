import React, { useEffect, useState } from 'react'
import { api } from '../api'

function SessionDetailModal({ sessionId, onClose }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/user/sessions/${sessionId}`).then(r => { setDetail(r); setLoading(false) }).catch(() => setLoading(false))
  }, [sessionId])

  if (loading) return <div className="modal-overlay" onClick={onClose}><div className="modal-content" onClick={e => e.stopPropagation()} style={{ padding: '2rem', textAlign: 'center' }}><div className="loading-spinner" /></div></div>
  if (!detail?.session) return null

  const report = detail.session
  const scores = report.breakdown || report.scores || {}

  return (
    <div className="modal-overlay" onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div className="modal-content" onClick={e => e.stopPropagation()} style={{ background: '#1e293b', borderRadius: 16, padding: '2rem', maxWidth: 600, width: '90%', maxHeight: '80vh', overflow: 'auto', border: '1px solid rgba(255,255,255,0.08)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f1f5f9' }}>{report.selectedCompany || 'Interview'} Report</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', fontSize: '1.25rem', cursor: 'pointer' }}>&times;</button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.75rem', marginBottom: '1.5rem' }}>
          {Object.entries(scores).map(([key, val]) => (
            <div key={key} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '0.75rem 1rem' }}>
              <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'capitalize' }}>{key}</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: val >= 70 ? '#34d399' : val >= 50 ? '#fbbf24' : '#f87171' }}>{val}%</div>
            </div>
          ))}
        </div>

        <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '1rem', marginBottom: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Overall Score</div>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#818cf8' }}>{report.overallScore}%</div>
        </div>

        {report.strengths?.length > 0 && (
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#34d399', marginBottom: '0.5rem' }}>Strengths</div>
            {report.strengths.map((s, i) => <div key={i} style={{ fontSize: '0.8rem', color: '#cbd5e1', padding: '2px 0' }}>+ {s}</div>)}
          </div>
        )}

        {report.weaknesses?.length > 0 && (
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#f87171', marginBottom: '0.5rem' }}>Weaknesses</div>
            {report.weaknesses.map((w, i) => <div key={i} style={{ fontSize: '0.8rem', color: '#cbd5e1', padding: '2px 0' }}>- {w}</div>)}
          </div>
        )}

        {detail.proctoring && (
          <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '1rem' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#94a3b8', marginBottom: '0.5rem' }}>Proctoring</div>
            <div style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>Integrity Score: {detail.proctoring.integrity_score || 100}%</div>
            <div style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>Status: {detail.proctoring.assessment_status || 'N/A'}</div>
          </div>
        )}
      </div>
    </div>
  )
}

export { SessionDetailModal }
