import React, { useEffect, useState } from 'react'
import { Shield } from 'lucide-react'
import { api } from '../api'

function AdminSessionModal({ sessionId, modalType = 'report', onClose }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/admin/sessions/${sessionId}`).then(r => { setDetail(r); setLoading(false) }).catch(() => setLoading(false))
  }, [sessionId])

  if (loading) return <div className="modal-overlay" onClick={onClose}><div className="modal-content" onClick={e => e.stopPropagation()} style={{ padding: '2rem', textAlign: 'center' }}><div className="loading-spinner" /></div></div>
  if (!detail?.session) return null

  const report = detail.session
  const scores = report.breakdown || report.scores || {}
  const proctoring = detail.proctoring

  return (
    <div className="modal-overlay" onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div className="modal-content" onClick={e => e.stopPropagation()} style={{ background: '#1e293b', borderRadius: 16, padding: '2rem', maxWidth: 650, width: '90%', maxHeight: '85vh', overflow: 'auto', border: '1px solid rgba(255,255,255,0.08)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f1f5f9' }}>
            {modalType === 'proctoring' ? 'Proctoring Details' : 'Session Report'} — {report.candidateName || 'Candidate'}
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', fontSize: '1.25rem', cursor: 'pointer' }}>&times;</button>
        </div>

        {/* Report View */}
        {modalType === 'report' && (
          <>
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

            {report.feedback && (
              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#94a3b8', marginBottom: '0.5rem' }}>AI Feedback</div>
                <p style={{ fontSize: '0.8rem', color: '#cbd5e1', lineHeight: 1.5 }}>{typeof report.feedback === 'string' ? report.feedback : report.feedback.summary || ''}</p>
              </div>
            )}

            {report.recommendations?.length > 0 && (
              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#38bdf8', marginBottom: '0.5rem' }}>Recommendations</div>
                {report.recommendations.map((r, i) => <div key={i} style={{ fontSize: '0.8rem', color: '#cbd5e1', padding: '2px 0' }}>+ {r}</div>)}
              </div>
            )}
          </>
        )}

        {/* Proctoring View */}
        {modalType === 'proctoring' && (
          <>
            {!proctoring ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
                <Shield size={40} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                <p>No proctoring data available for this session</p>
              </div>
            ) : (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1.5rem' }}>
                  <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '1rem' }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Integrity Score</div>
                    <div style={{ fontSize: '1.75rem', fontWeight: 700, color: (proctoring.integrity_score || 100) >= 80 ? '#34d399' : '#f87171' }}>
                      {proctoring.integrity_score || 100}%
                    </div>
                  </div>
                  <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '1rem' }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Status</div>
                    <div style={{ fontSize: '1rem', fontWeight: 600, color: '#f1f5f9' }}>{proctoring.assessment_status || 'N/A'}</div>
                  </div>
                </div>

                {proctoring.violations?.length > 0 && (
                  <div style={{ marginBottom: '1rem' }}>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#f87171', marginBottom: '0.5rem' }}>Violations ({proctoring.violations.length})</div>
                    {proctoring.violations.map((v, i) => (
                      <div key={i} style={{ fontSize: '0.8rem', color: '#fbbf24', padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                        {v.type || v.message || JSON.stringify(v)}
                        {v.timestamp && <span style={{ color: '#64748b', marginLeft: '0.5rem' }}>{new Date(v.timestamp * 1000).toLocaleTimeString()}</span>}
                      </div>
                    ))}
                  </div>
                )}

                {proctoring.snapshots?.length > 0 && (
                  <div>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#94a3b8', marginBottom: '0.5rem' }}>Snapshots ({proctoring.snapshots.length})</div>
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                      {proctoring.snapshots.map((snap, i) => (
                        <div key={i} style={{ width: 80, height: 60, borderRadius: 8, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
                          {snap.image ? <img src={snap.image} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', fontSize: '0.6rem' }}>No img</div>}
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
