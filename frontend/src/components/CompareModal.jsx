import React, { useEffect, useRef, useState } from 'react'
import { X } from 'lucide-react'
import { api } from '../api'
import { scoreClass } from '../utils/score'

function CompareModal({ sessionIds, onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const contentRef = useRef(null)

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    api.post('/admin/compare', { session_ids: sessionIds })
      .then(r => { setData(r); setLoading(false) })
      .catch(() => setLoading(false))
  }, [sessionIds])

  useEffect(() => {
    if (!loading && contentRef.current) contentRef.current.focus()
  }, [loading])

  if (loading) {
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content" onClick={e => e.stopPropagation()} style={{ padding: '2rem', textAlign: 'center' }}>
          <div className="loading-spinner" />
        </div>
      </div>
    )
  }

  const comparisons = data?.comparisons || []
  if (!comparisons.length) return null

  const allRoundKeys = ['aptitude', 'coding', 'technical', 'hr']

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" ref={contentRef} tabIndex={-1} onClick={e => e.stopPropagation()} style={{ maxWidth: '90vw', overflowX: 'auto' }}>
        <div className="modal-header">
          <h3>Candidate Comparison</h3>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close dialog"><X size={20} /></button>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Metric</th>
              {comparisons.map((c, i) => (
                <th key={i}>{c.candidate_name || c.session_id?.slice(0, 8)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="cell-muted">Company</td>
              {comparisons.map((c, i) => <td key={i} className="cell-primary">{c.company || 'N/A'}</td>)}
            </tr>
            <tr>
              <td className="cell-muted">Overall</td>
              {comparisons.map((c, i) => <td key={i} className={scoreClass(c.overall_score)}>{c.overall_score}%</td>)}
            </tr>
            {allRoundKeys.map(round => (
              <tr key={round}>
                <td className="cell-muted">{round}</td>
                {comparisons.map((c, i) => (
                  <td key={i} className={scoreClass(c.scores?.[round] || 0)}>{c.scores?.[round] || 0}%</td>
                ))}
              </tr>
            ))}
            <tr>
              <td className="cell-muted">Proctoring Score</td>
              {comparisons.map((c, i) => <td key={i}>{c.proctoring_score}%</td>)}
            </tr>
            <tr>
              <td className="cell-muted">Proctoring Status</td>
              {comparisons.map((c, i) => <td key={i}>{c.proctoring_status}</td>)}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

export { CompareModal }
