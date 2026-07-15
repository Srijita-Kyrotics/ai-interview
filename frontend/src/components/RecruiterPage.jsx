import React, { useEffect, useState } from 'react'
import { LayoutDashboard, Users, BarChart2, Search } from 'lucide-react'
import { api } from '../api'
import { AdminSessionModal } from './AdminSessionModal'

function RecruiterPage({ user }) {
  const [tab, setTab] = useState('overview')
  const [candidates, setCandidates] = useState([])
  const [allSessions, setAllSessions] = useState([])
  const [stats, setStats] = useState(null)
  const [selectedCandidate, setSelectedCandidate] = useState(null)
  const [selectedSession, setSelectedSession] = useState(null)
  const [modalType, setModalType] = useState('report')
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')

  const fetchData = () => {
    setLoading(true)
    Promise.all([api.get('/admin/candidates'), api.get('/admin/sessions'), api.get('/admin/stats')])
      .then(([c, s, st]) => { setCandidates(c.candidates || []); setAllSessions(s.sessions || []); setStats(st) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchData() }, [])

  const filteredCandidates = candidates.filter(c =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase()) || c.email.toLowerCase().includes(searchQuery.toLowerCase())
  )

  const filteredSessions = selectedCandidate
    ? allSessions.filter(s => {
        const state = s._user_id || s.user_id || ''
        return state === selectedCandidate
      }).filter(s =>
        s.company?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.session_id?.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : allSessions.filter(s =>
        s.company?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.session_id?.toLowerCase().includes(searchQuery.toLowerCase())
      )

  const handleViewCandidateSessions = (email) => {
    setSelectedCandidate(email)
    setSearchQuery('')
    setTab('sessions')
  }

  const handleClearCandidateFilter = () => {
    setSelectedCandidate(null)
    setSearchQuery('')
  }

  const openModal = (sessionId, type) => {
    setSelectedSession(sessionId)
    setModalType(type)
  }

  if (loading) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <div className="loading-spinner" />
        <p className="muted" style={{ marginTop: '1rem' }}>Loading recruiter portal...</p>
      </div>
    )
  }

  return (
    <div style={{ padding: '1.5rem', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#f1f5f9' }}>Recruiter Portal</h2>
          <p className="muted" style={{ fontSize: '0.85rem' }}>Manage candidates and review interview performance</p>
        </div>
        <button className="btn ghost" style={{ fontSize: '0.8rem' }} onClick={fetchData}>Refresh</button>
      </div>

      {/* Tab Navigation */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '0.5rem' }}>
        {[
          { key: 'overview', label: 'Overview', icon: LayoutDashboard },
          { key: 'candidates', label: 'Candidates', icon: Users },
          { key: 'sessions', label: 'All Sessions', icon: BarChart2 },
        ].map(t => (
          <button key={t.key} onClick={() => { setTab(t.key); if (t.key !== 'sessions') handleClearCandidateFilter() }} style={{
            display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem', borderRadius: 8,
            background: tab === t.key ? 'rgba(129,140,248,0.15)' : 'transparent',
            color: tab === t.key ? '#818cf8' : '#94a3b8', border: 'none', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 500,
            transition: 'all 0.15s ease'
          }}>
            <t.icon size={16} /> {t.label}
          </button>
        ))}
      </div>

      {/* Search Bar */}
      <div style={{ marginBottom: '1rem', position: 'relative' }}>
        <Search size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#64748b' }} />
        <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder={selectedCandidate ? `Filtering by: ${selectedCandidate} (clear to show all)` : "Search candidates or companies..."}
          style={{ width: '100%', padding: '0.6rem 0.6rem 0.6rem 2.25rem', borderRadius: 8, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.04)', color: '#f1f5f9', fontSize: '0.85rem', outline: 'none' }} />
        {selectedCandidate && (
          <button onClick={handleClearCandidateFilter} style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'rgba(248,113,113,0.15)', color: '#f87171', border: 'none', borderRadius: 4, padding: '2px 8px', cursor: 'pointer', fontSize: '0.75rem' }}>
            Clear filter
          </button>
        )}
      </div>

      {tab === 'overview' && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
            {[
              { label: 'Total Candidates', value: stats?.total_candidates || 0, color: '#818cf8' },
              { label: 'Total Interviews', value: stats?.total_interviews || 0, color: '#34d399' },
              { label: 'Avg Platform Score', value: `${stats?.avg_platform_score || 0}%`, color: '#fbbf24' },
              { label: 'Top Score', value: `${stats?.top_score || 0}%`, color: '#f87171' },
            ].map((card, i) => (
              <div key={i} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, padding: '1.25rem', border: '1px solid rgba(255,255,255,0.06)' }}>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '0.25rem' }}>{card.label}</div>
                <div style={{ fontSize: '1.75rem', fontWeight: 700, color: card.color }}>{card.value}</div>
              </div>
            ))}
          </div>

          {/* Recent Sessions */}
          <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, padding: '1.5rem', border: '1px solid rgba(255,255,255,0.06)' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#f1f5f9', marginBottom: '1rem' }}>Recent Interviews</h3>
            {allSessions.slice(0, 5).map(s => (
              <div key={s.session_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <div>
                  <span style={{ color: '#f1f5f9', fontWeight: 500, fontSize: '0.85rem' }}>{s.company || 'N/A'}</span>
                  <span style={{ color: '#64748b', fontSize: '0.75rem', marginLeft: '0.75rem' }}>{new Date(s.date * 1000).toLocaleDateString()}</span>
                </div>
                <span style={{ color: s.overall_score >= 70 ? '#34d399' : '#fbbf24', fontWeight: 600, fontSize: '0.85rem' }}>{s.overall_score}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'candidates' && (
        <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, padding: '1.5rem', border: '1px solid rgba(255,255,255,0.06)' }}>
          {filteredCandidates.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
              <Users size={40} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
              <p>No candidates found</p>
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                  {['Name', 'Email', 'Interviews', 'Avg Score', 'Last Active', 'Action'].map(h => (
                    <th key={h} style={{ padding: '0.75rem', textAlign: 'left', color: '#94a3b8', fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredCandidates.map(c => (
                  <tr key={c.email} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <td style={{ padding: '0.75rem', color: '#f1f5f9', fontWeight: 500 }}>{c.name}</td>
                    <td style={{ padding: '0.75rem', color: '#94a3b8' }}>{c.email}</td>
                    <td style={{ padding: '0.75rem', color: '#cbd5e1' }}>{c.interview_count}</td>
                    <td style={{ padding: '0.75rem', color: c.avg_score >= 70 ? '#34d399' : '#fbbf24', fontWeight: 600 }}>{c.avg_score}%</td>
                    <td style={{ padding: '0.75rem', color: '#94a3b8' }}>{c.last_active ? new Date(c.last_active * 1000).toLocaleDateString() : 'N/A'}</td>
                    <td style={{ padding: '0.75rem' }}>
                      <button className="btn ghost" style={{ fontSize: '0.75rem', padding: '4px 12px' }} onClick={() => handleViewCandidateSessions(c.email)}>View Sessions</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === 'sessions' && (
        <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, padding: '1.5rem', border: '1px solid rgba(255,255,255,0.06)' }}>
          {filteredSessions.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
              <BarChart2 size={40} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
              <p>No sessions found</p>
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                  {['Date', 'Company', 'Rounds', 'Score', 'Actions'].map(h => (
                    <th key={h} style={{ padding: '0.75rem', textAlign: 'left', color: '#94a3b8', fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredSessions.map(s => (
                  <tr key={s.session_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <td style={{ padding: '0.75rem', color: '#cbd5e1' }}>{new Date(s.date * 1000).toLocaleDateString()}</td>
                    <td style={{ padding: '0.75rem', color: '#f1f5f9', fontWeight: 500 }}>{s.company || 'N/A'}</td>
                    <td style={{ padding: '0.75rem' }}>
                      <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                        {(s.rounds_completed || []).map(r => (
                          <span key={r} style={{ background: 'rgba(129,140,248,0.15)', color: '#818cf8', padding: '2px 8px', borderRadius: 6, fontSize: '0.7rem', textTransform: 'capitalize' }}>{r}</span>
                        ))}
                      </div>
                    </td>
                    <td style={{ padding: '0.75rem', color: s.overall_score >= 70 ? '#34d399' : '#fbbf24', fontWeight: 600 }}>{s.overall_score}%</td>
                    <td style={{ padding: '0.75rem', display: 'flex', gap: '0.5rem' }}>
                      <button className="btn ghost" style={{ fontSize: '0.75rem', padding: '4px 12px' }} onClick={() => openModal(s.session_id, 'report')}>Report</button>
                      <button className="btn ghost" style={{ fontSize: '0.75rem', padding: '4px 12px', color: '#f87171' }} onClick={() => openModal(s.session_id, 'proctoring')}>Proctoring</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Session Detail Modal */}
      {selectedSession && (
        <AdminSessionModal sessionId={selectedSession} modalType={modalType} onClose={() => setSelectedSession(null)} />
      )}
    </div>
  )
}

export { RecruiterPage }
