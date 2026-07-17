import React, { useEffect, useState } from 'react'
import { LayoutDashboard, Users, BarChart2, Search } from 'lucide-react'
import { api } from '../api'
import { AdminSessionModal } from './AdminSessionModal'

function scoreClass(score) {
  if (score >= 70) return 'score-good'
  if (score >= 50) return 'score-mid'
  return 'score-low'
}

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
      <div style={{ textAlign: 'center', padding: '3rem' }}>
        <div className="loading-spinner" />
        <p className="muted" style={{ marginTop: '1rem' }}>Loading recruiter portal...</p>
      </div>
    )
  }

  const statCards = [
    { label: 'Total Candidates', value: stats?.total_candidates || 0, color: '#0B4FA8' },
    { label: 'Total Interviews', value: stats?.total_interviews || 0, color: '#10B981' },
    { label: 'Avg Platform Score', value: `${stats?.avg_platform_score || 0}%`, color: '#F59E0B' },
    { label: 'Top Score', value: `${stats?.top_score || 0}%`, color: '#EF4444' },
  ]

  const tabs = [
    { key: 'overview', label: 'Overview', icon: LayoutDashboard },
    { key: 'candidates', label: 'Candidates', icon: Users },
    { key: 'sessions', label: 'All Sessions', icon: BarChart2 },
  ]

  return (
    <div className="recruiter-page">
      <div className="page-header">
        <div>
          <h2>Recruiter Portal</h2>
          <p className="muted" style={{ fontSize: '0.85rem', margin: '0.25rem 0 0' }}>Manage candidates and review interview performance</p>
        </div>
        <button className="btn ghost btn-refresh" onClick={fetchData}>Refresh</button>
      </div>

      {/* Tab Navigation */}
      <div className="tab-nav">
        {tabs.map(t => (
          <button
            key={t.key}
            onClick={() => { setTab(t.key); if (t.key !== 'sessions') handleClearCandidateFilter() }}
            className={`tab-btn ${tab === t.key ? 'active' : ''}`}
          >
            <t.icon size={16} /> {t.label}
          </button>
        ))}
      </div>

      {/* Search Bar */}
      <div className="search-bar-wrapper">
        <Search size={16} className="search-icon" />
        <input
          className="search-bar"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          placeholder={selectedCandidate ? `Filtering by: ${selectedCandidate} (clear to show all)` : "Search candidates or companies..."}
        />
        {selectedCandidate && (
          <button className="filter-clear-btn" onClick={handleClearCandidateFilter}>
            Clear filter
          </button>
        )}
      </div>

      {tab === 'overview' && (
        <div>
          <div className="stat-cards-grid">
            {statCards.map((card, i) => (
              <div key={i} className="stat-card">
                <div className="stat-card-label" style={{ marginBottom: '0.25rem' }}>{card.label}</div>
                <div style={{ fontSize: '1.75rem', fontWeight: 700, color: card.color }}>{card.value}</div>
              </div>
            ))}
          </div>

          {/* Recent Sessions */}
          <div className="panel-card">
            <h3>Recent Interviews</h3>
            {allSessions.slice(0, 5).map(s => (
              <div key={s.session_id} className="session-list-item">
                <div>
                  <span className="cell-primary" style={{ fontSize: '0.85rem' }}>{s.company || 'N/A'}</span>
                  <span className="cell-muted" style={{ fontSize: '0.75rem', marginLeft: '0.75rem' }}>{new Date(s.date * 1000).toLocaleDateString()}</span>
                </div>
                <span className={scoreClass(s.overall_score)} style={{ fontSize: '0.85rem' }}>{s.overall_score}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'candidates' && (
        <div className="panel-card">
          {filteredCandidates.length === 0 ? (
            <div className="empty-state">
              <Users size={40} />
              <p>No candidates found</p>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    {['Name', 'Email', 'Interviews', 'Avg Score', 'Last Active', 'Action'].map(h => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredCandidates.map(c => (
                    <tr key={c.email}>
                      <td className="cell-primary">{c.name}</td>
                      <td className="cell-muted">{c.email}</td>
                      <td>{c.interview_count}</td>
                      <td className={scoreClass(c.avg_score)}>{c.avg_score}%</td>
                      <td className="cell-muted">{c.last_active ? new Date(c.last_active * 1000).toLocaleDateString() : 'N/A'}</td>
                      <td>
                        <button className="btn ghost" style={{ fontSize: '0.75rem', padding: '4px 12px' }} onClick={() => handleViewCandidateSessions(c.email)}>View Sessions</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'sessions' && (
        <div className="panel-card">
          {filteredSessions.length === 0 ? (
            <div className="empty-state">
              <BarChart2 size={40} />
              <p>No sessions found</p>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    {['Date', 'Company', 'Rounds', 'Score', 'Actions'].map(h => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredSessions.map(s => (
                    <tr key={s.session_id}>
                      <td className="cell-muted">{new Date(s.date * 1000).toLocaleDateString()}</td>
                      <td className="cell-primary">{s.company || 'N/A'}</td>
                      <td>
                        <div style={{ display: 'flex', gap: '0.25rem', flexWrap: 'wrap' }}>
                          {(s.rounds_completed || []).map(r => (
                            <span key={r} className="round-badge">{r}</span>
                          ))}
                        </div>
                      </td>
                      <td className={scoreClass(s.overall_score)}>{s.overall_score}%</td>
                      <td style={{ display: 'flex', gap: '0.5rem' }}>
                        <button className="btn ghost" style={{ fontSize: '0.75rem', padding: '4px 12px' }} onClick={() => openModal(s.session_id, 'report')}>Report</button>
                        <button className="btn ghost" style={{ fontSize: '0.75rem', padding: '4px 12px', color: 'var(--error)' }} onClick={() => openModal(s.session_id, 'proctoring')}>Proctoring</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
