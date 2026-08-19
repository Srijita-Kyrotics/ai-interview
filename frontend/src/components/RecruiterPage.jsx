import React, { useEffect, useState, useMemo } from 'react'
import { LayoutDashboard, Users, BarChart2, Search, TrendingUp, Award, Target, Activity } from 'lucide-react'
import { api } from '../api'
import { AdminSessionModal } from './AdminSessionModal'
import { CompareModal } from './CompareModal'
import { SessionReplay } from './SessionReplay'
import { scoreClass } from '../utils/score'

// Skill radar chart component
function SkillRadar({ candidate, benchmark }) {
  const skills = ['Technical', 'Communication', 'Problem Solving', 'System Design', 'Coding', 'Behavioral']
  
  const candidateData = skills.map(s => {
    const key = s.toLowerCase().replace(' ', '_')
    return candidate.scores?.[key] || candidate[key] || 0
  })
  
  const benchmarkData = skills.map(s => {
    const key = s.toLowerCase().replace(' ', '_')
    return benchmark[key] || 0
  })

  return (
    <div className="skill-radar-container">
      <canvas 
        id="skill-radar" 
        width={300} 
        height={300}
        ref={canvas => {
          if (canvas && canvas.getContext) {
            const ctx = canvas.getContext('2d')
            const centerX = canvas.width / 2
            const centerY = canvas.height / 2
            const radius = Math.min(centerX, centerY) - 20
            
            // Draw axes
            ctx.strokeStyle = '#e5e7eb'
            ctx.lineWidth = 1
            skills.forEach((skill, i) => {
              const angle = (i / skills.length) * 2 * Math.PI - Math.PI / 2
              ctx.beginPath()
              ctx.moveTo(centerX, centerY)
              ctx.lineTo(centerX + radius * Math.cos(angle), centerY + radius * Math.sin(angle))
              ctx.stroke()
              
              // Labels
              ctx.fillStyle = '#374151'
              ctx.font = '11px sans-serif'
              ctx.textAlign = 'center'
              ctx.fillText(skill, centerX + (radius + 15) * Math.cos(angle), centerY + (radius + 15) * Math.sin(angle))
            })
            
            // Draw concentric circles
            for (let level = 1; level <= 5; level++) {
              ctx.beginPath()
              const r = (level / 5) * radius
              for (let i = 0; i < skills.length; i++) {
                const angle = (i / skills.length) * 2 * Math.PI - Math.PI / 2
                const x = centerX + r * Math.cos(angle)
                const y = centerY + r * Math.sin(angle)
                if (i === 0) ctx.moveTo(x, y)
                else ctx.lineTo(x, y)
              }
              ctx.closePath()
              ctx.stroke()
            }
            
            // Draw candidate area
            ctx.beginPath()
            candidateData.forEach((val, i) => {
              const angle = (i / skills.length) * 2 * Math.PI - Math.PI / 2
              const r = (val / 100) * radius
              const x = centerX + r * Math.cos(angle)
              const y = centerY + r * Math.sin(angle)
              if (i === 0) ctx.moveTo(x, y)
              else ctx.lineTo(x, y)
            })
            ctx.closePath()
            ctx.fillStyle = 'rgba(11, 79, 168, 0.2)'
            ctx.strokeStyle = '#0B4FA8'
            ctx.lineWidth = 2
            ctx.fill()
            ctx.stroke()
            
            // Draw benchmark area
            ctx.beginPath()
            benchmarkData.forEach((val, i) => {
              const angle = (i / skills.length) * 2 * Math.PI - Math.PI / 2
              const r = (val / 100) * radius
              const x = centerX + r * Math.cos(angle)
              const y = centerY + r * Math.sin(angle)
              if (i === 0) ctx.moveTo(x, y)
              else ctx.lineTo(x, y)
            })
            ctx.closePath()
            ctx.fillStyle = 'rgba(16, 185, 129, 0.1)'
            ctx.strokeStyle = '#10B981'
            ctx.lineWidth = 2
            ctx.setLineDash([5, 5])
            ctx.stroke()
            ctx.setLineDash([])
            
            // Legend
            ctx.fillStyle = '#0B4FA8'
            ctx.fillRect(10, 10, 12, 12)
            ctx.fillStyle = '#374151'
            ctx.font = '11px sans-serif'
            ctx.fillText('Candidate', 25, 20)
            
            ctx.strokeStyle = '#10B981'
            ctx.setLineDash([5, 5])
            ctx.beginPath()
            ctx.moveTo(10, 30)
            ctx.lineTo(22, 30)
            ctx.stroke()
            ctx.setLineDash([])
            ctx.fillStyle = '#374151'
            ctx.fillText('Benchmark', 25, 34)
          }
        }}
      />
      <div className="radar-legend">
        <div className="legend-item">
          <span className="legend-color candidate"></span>
          <span>Candidate</span>
        </div>
        <div className="legend-item">
          <span className="legend-color benchmark"></span>
          <span>Benchmark</span>
        </div>
      </div>
    </div>
  )
}

// Percentile badge component
function PercentileBadge({ value, label }) {
  const getColor = (p) => {
    if (p >= 90) return '#EF4444' // Top 10%
    if (p >= 75) return '#F59E0B' // Top 25%
    if (p >= 50) return '#10B981' // Above median
    return '#6B7280'
  }
  
  return (
    <div className="percentile-badge">
      <div className="percentile-value" style={{ color: getColor(value) }}>{value}th</div>
      <div className="percentile-label">{label}</div>
    </div>
  )
}

function RecruiterPage({ user }) {
  const [tab, setTab] = useState('overview')
  const [candidates, setCandidates] = useState([])
  const [allSessions, setAllSessions] = useState([])
  const [stats, setStats] = useState(null)
  const [benchmark, setBenchmark] = useState(null)
  const [selectedCandidate, setSelectedCandidate] = useState(null)
  const [selectedSession, setSelectedSession] = useState(null)
  const [modalType, setModalType] = useState('report')
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedSessionIds, setSelectedSessionIds] = useState([])
  const [showCompare, setShowCompare] = useState(false)
  const [replaySessionId, setReplaySessionId] = useState(null)
  const [replaySessionName, setReplaySessionName] = useState('')
  const [analyticsLoading, setAnalyticsLoading] = useState(false)

  const fetchData = () => {
    setLoading(true)
    Promise.all([
      api.get('/admin/candidates'),
      api.get('/admin/sessions'),
      api.get('/admin/stats'),
      api.get('/admin/benchmark').catch(() => ({})) // Optional benchmark data
    ])
      .then(([c, s, st, b]) => { 
        setCandidates(c.candidates || [])
        setAllSessions(s.sessions || [])
        setStats(st)
        if (b.benchmark) setBenchmark(b.benchmark)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  const fetchAnalytics = async () => {
    setAnalyticsLoading(true)
    try {
      const b = await api.get('/admin/benchmark')
      if (b.benchmark) setBenchmark(b.benchmark)
    } catch (e) {
      console.warn('Benchmark data unavailable')
    } finally {
      setAnalyticsLoading(false)
    }
  }

  useEffect(() => { 
    fetchData()
    fetchAnalytics()
  }, [])

  const filteredCandidates = useMemo(() => candidates.filter(c =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
    c.email.toLowerCase().includes(searchQuery.toLowerCase())
  ), [candidates, searchQuery])

  const filteredSessions = useMemo(() => {
    if (selectedCandidate) {
      return allSessions.filter(s => {
        const state = s._user_id || s.user_id || ''
        return state === selectedCandidate
      }).filter(s =>
        s.company?.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.session_id?.toLowerCase().includes(searchQuery.toLowerCase())
      )
    }
    return allSessions.filter(s =>
      s.company?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.session_id?.toLowerCase().includes(searchQuery.toLowerCase())
    )
  }, [allSessions, selectedCandidate, searchQuery])

  // Calculate percentile rankings
  const candidatesWithPercentiles = useMemo(() => {
    if (!candidates.length || !benchmark) return candidates
    
    return candidates.map(c => {
      const overall = c.avg_score || 0
      const percentile = benchmark.percentiles?.overall 
        ? Math.round(benchmark.percentiles.overall.filter(p => p <= overall).length / benchmark.percentiles.overall.length * 100)
        : 50
      
      return { ...c, percentile }
    })
  }, [candidates, benchmark])

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

  const toggleSessionSelect = (sessionId) => {
    setSelectedSessionIds(prev =>
      prev.includes(sessionId) ? prev.filter(id => id !== sessionId) : [...prev, sessionId]
    )
  }

  if (replaySessionId) {
    return <SessionReplay sessionId={replaySessionId} sessionName={replaySessionName} onBack={() => { setReplaySessionId(null); setReplaySessionName('') }} />
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
    { label: 'Total Candidates', value: stats?.total_candidates || 0, color: '#0B4FA8', icon: Users },
    { label: 'Total Interviews', value: stats?.total_interviews || 0, color: '#10B981', icon: Activity },
    { label: 'Avg Platform Score', value: `${stats?.avg_platform_score || 0}%`, color: '#F59E0B', icon: Target },
    { label: 'Top Score', value: `${stats?.top_score || 0}%`, color: '#EF4444', icon: Award },
  ]

  const tabs = [
    { key: 'overview', label: 'Overview', icon: LayoutDashboard },
    { key: 'candidates', label: 'Candidates', icon: Users },
    { key: 'sessions', label: 'All Sessions', icon: BarChart2 },
    { key: 'analytics', label: 'Analytics', icon: TrendingUp },
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
                <card.icon size={20} style={{ marginBottom: '0.5rem', color: card.color }} />
                <div className="stat-card-label" style={{ marginBottom: '0.25rem' }}>{card.label}</div>
                <div style={{ fontSize: '1.75rem', fontWeight: 700, color: card.color }}>{card.value}</div>
              </div>
            ))}
          </div>

          {/* Benchmark Summary */}
          {benchmark && (
            <div className="panel-card" style={{ marginTop: '1.5rem' }}>
              <h3>Platform Benchmarks</h3>
              <div className="benchmark-grid">
                <div className="benchmark-item">
                  <div className="benchmark-label">Median Score</div>
                  <div className="benchmark-value">{benchmark.median_overall || 'N/A'}%</div>
                </div>
                <div className="benchmark-item">
                  <div className="benchmark-label">Top 25% Threshold</div>
                  <div className="benchmark-value">{benchmark.p75_overall || 'N/A'}%</div>
                </div>
                <div className="benchmark-item">
                  <div className="benchmark-label">Top 10% Threshold</div>
                  <div className="benchmark-value">{benchmark.p90_overall || 'N/A'}%</div>
                </div>
                <div className="benchmark-item">
                  <div className="benchmark-label">Avg Technical</div>
                  <div className="benchmark-value">{benchmark.median_technical || 'N/A'}%</div>
                </div>
                <div className="benchmark-item">
                  <div className="benchmark-label">Avg Communication</div>
                  <div className="benchmark-value">{benchmark.median_communication || 'N/A'}%</div>
                </div>
                <div className="benchmark-item">
                  <div className="benchmark-label">Avg Problem Solving</div>
                  <div className="benchmark-value">{benchmark.median_problem_solving || 'N/A'}%</div>
                </div>
              </div>
            </div>
          )}

          {/* Recent Sessions */}
          <div className="panel-card" style={{ marginTop: '1.5rem' }}>
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
                    {['Name', 'Email', 'Interviews', 'Avg Score', 'Percentile', 'Last Active', 'Action'].map(h => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredCandidates.map(c => {
                    const percentile = c.percentile || 50
                    const getPercentileColor = (p) => {
                      if (p >= 90) return '#EF4444'
                      if (p >= 75) return '#F59E0B'
                      if (p >= 50) return '#10B981'
                      return '#6B7280'
                    }
                    return (
                      <tr key={c.email}>
                        <td className="cell-primary">{c.name}</td>
                        <td className="cell-muted">{c.email}</td>
                        <td>{c.interview_count}</td>
                        <td className={scoreClass(c.avg_score)}>{c.avg_score}%</td>
                        <td>
                          <PercentileBadge value={percentile} label="Percentile" />
                        </td>
                        <td className="cell-muted">{c.last_active ? new Date(c.last_active * 1000).toLocaleDateString() : 'N/A'}</td>
                        <td>
                          <button className="btn ghost" style={{ fontSize: '0.75rem', padding: '4px 12px' }} onClick={() => handleViewCandidateSessions(c.email)}>View Sessions</button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'sessions' && (
        <div className="panel-card">
          {selectedSessionIds.length >= 2 && (
            <div style={{ marginBottom: '1rem' }}>
              <button className="btn primary" onClick={() => setShowCompare(true)}>
                Compare {selectedSessionIds.length} Sessions
              </button>
              <button className="btn ghost" style={{ marginLeft: '0.5rem' }} onClick={() => setSelectedSessionIds([])}>Clear Selection</button>
            </div>
          )}
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
                    {['', 'Date', 'Company', 'Rounds', 'Score', 'Percentile', 'Actions'].map(h => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredSessions.map(s => {
                    const percentile = benchmark && benchmark.percentiles?.overall
                      ? Math.round(benchmark.percentiles.overall.filter(p => p <= s.overall_score).length / benchmark.percentiles.overall.length * 100)
                      : 50
                    return (
                      <tr key={s.session_id}>
                        <td>
                          <input
                            type="checkbox"
                            checked={selectedSessionIds.includes(s.session_id)}
                            onChange={() => toggleSessionSelect(s.session_id)}
                            aria-label={`Select session ${s.session_id}`}
                          />
                        </td>
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
                        <td>
                          <PercentileBadge value={percentile} label="" />
                        </td>
                        <td style={{ display: 'flex', gap: '0.5rem' }}>
                          <button className="btn ghost" style={{ fontSize: '0.75rem', padding: '4px 12px' }} onClick={() => openModal(s.session_id, 'report')}>Report</button>
                          <button className="btn ghost" style={{ fontSize: '0.75rem', padding: '4px 12px', color: 'var(--error)' }} onClick={() => openModal(s.session_id, 'proctoring')}>Proctoring</button>
                          <button className="btn ghost" style={{ fontSize: '0.75rem', padding: '4px 12px', color: 'var(--primary)' }} onClick={() => { setReplaySessionId(s.session_id); setReplaySessionName(`${s.company || 'Session'} — ${new Date(s.date * 1000).toLocaleDateString()}`) }}>Replay</button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'analytics' && (
        <div>
          <div className="panel-card" style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3>Candidate Analytics & Benchmarking</h3>
              <button className="btn ghost" onClick={fetchAnalytics} disabled={analyticsLoading}>
                {analyticsLoading ? 'Refreshing...' : 'Refresh Benchmarks'}
              </button>
            </div>
            
            {filteredCandidates.length === 0 ? (
              <div className="empty-state">
                <Users size={40} />
                <p>No candidates to analyze</p>
              </div>
            ) : (
              <div className="analytics-grid">
                {filteredCandidates.slice(0, 12).map(c => (
                  <div key={c.email} className="analytics-card">
                    <div className="analytics-card-header">
                      <div className="cell-primary">{c.name}</div>
                      <div className="cell-muted" style={{ fontSize: '0.75rem' }}>{c.email}</div>
                    </div>
                    
                    <div className="analytics-card-scores">
                      <div className="score-main">
                        <span className={scoreClass(c.avg_score)} style={{ fontSize: '2rem', fontWeight: 700 }}>{c.avg_score}%</span>
                        <PercentileBadge value={c.percentile || 50} label="Overall" />
                      </div>
                      
                      <div className="score-breakdown">
                        {[
                          { key: 'technical', label: 'Technical' },
                          { key: 'communication', label: 'Communication' },
                          { key: 'problem_solving', label: 'Problem Solving' },
                          { key: 'system_design', label: 'System Design' },
                          { key: 'coding', label: 'Coding' },
                          { key: 'behavioral', label: 'Behavioral' }
                        ].map(s => {
                          const val = c.scores?.[s.key] || c[`avg_${s.key}`] || 0
                          const bench = benchmark?.[`median_${s.key}`] || 0
                          return (
                            <div key={s.key} className="score-bar">
                              <span className="score-bar-label">{s.label}</span>
                              <div className="score-bar-track">
                                <div 
                                  className="score-bar-fill" 
                                  style={{ 
                                    width: `${val}%`,
                                    background: val >= bench ? '#10B981' : '#F59E0B'
                                  }}
                                />
                                {val < bench && (
                                  <div className="score-bar-benchmark" style={{ left: `${bench}%` }} title={`Benchmark: ${bench}%`} />
                                )}
                              </div>
                              <span className="score-bar-value">{val}%</span>
                            </div>
                          )
                        })}
                      </div>
                    </div>

                    <SkillRadar candidate={c} benchmark={benchmark || {}} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Session Detail Modal */}
      {selectedSession && (
        <AdminSessionModal sessionId={selectedSession} modalType={modalType} onClose={() => setSelectedSession(null)} />
      )}

      {/* Compare Modal */}
      {showCompare && (
        <CompareModal sessionIds={selectedSessionIds} onClose={() => setShowCompare(false)} />
      )}
    </div>
  )
}

export { RecruiterPage }
