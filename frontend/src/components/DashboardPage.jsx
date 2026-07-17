import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BarChart2, Building2, Calendar, TrendingUp, Award } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { api } from '../api'
import { SessionDetailModal } from './SessionDetailModal'
import { scoreClass } from '../utils/score'

function DashboardPage({ user }) {
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [sessions, setSessions] = useState([])
  const [selectedSession, setSelectedSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const lastFetchAtRef = useRef(0)

  const fetchData = () => {
    const now = Date.now()
    if (now - lastFetchAtRef.current < 2000) return
    lastFetchAtRef.current = now
    setLoading(true)
    Promise.all([api.get('/user/stats'), api.get('/user/sessions')])
      .then(([s, sess]) => { setStats(s); setSessions(sess.sessions || []) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    fetchData()
    const onFocus = () => fetchData()
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [])

  const chartData = useMemo(() => {
    if (!stats?.trend?.length) return []
    return stats.trend.map(t => ({
      date: new Date(t.date * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      Overall: t.overall,
      Aptitude: t.aptitude,
      Coding: t.coding,
      Technical: t.technical,
      HR: t.hr,
    }))
  }, [stats])

  if (loading) {
    return (
      <div className="dashboard-page" style={{ textAlign: 'center', padding: '3rem' }}>
        <div className="loading-spinner" />
        <p className="muted" style={{ marginTop: '1rem' }}>Loading your dashboard...</p>
      </div>
    )
  }

  const statCards = [
    { label: 'Total Interviews', value: stats?.total_interviews || 0, icon: Calendar, color: '#0B4FA8' },
    { label: 'Average Score', value: `${stats?.overall_avg || 0}%`, icon: TrendingUp, color: '#10B981' },
    { label: 'Best Score', value: `${stats?.best_score || 0}%`, icon: Award, color: '#F59E0B' },
    { label: 'Companies Practiced', value: stats?.companies_practiced?.length || 0, icon: Building2, color: '#EF4444' },
  ]

  return (
    <div className="dashboard-page">
      <div className="page-header">
        <div>
          <h2>Your Dashboard</h2>
          <p className="muted" style={{ fontSize: '0.85rem', margin: '0.25rem 0 0' }}>Track your interview performance over time</p>
        </div>
        <button className="btn primary" onClick={() => navigate('/resume')} aria-label="Start a new mock interview">Start New Interview</button>
      </div>

      {/* Stats Cards */}
      <div className="stat-cards-grid">
        {statCards.map((card, i) => (
          <div key={i} className="stat-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div className="stat-card-icon" style={{ background: `${card.color}12` }}>
                <card.icon size={20} color={card.color} />
              </div>
              <div>
                <div className="stat-card-value">{card.value}</div>
                <div className="stat-card-label">{card.label}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Performance Chart */}
      {chartData.length > 1 && (
        <div className="panel-card">
          <h3>Performance Trend</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="date" stroke="var(--text-muted)" fontSize={12} />
              <YAxis stroke="var(--text-muted)" fontSize={12} domain={[0, 100]} />
              <Tooltip
                contentStyle={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  color: 'var(--text-primary)',
                  boxShadow: 'var(--shadow-md)'
                }}
              />
              <Legend />
              <Line type="monotone" dataKey="Overall" stroke="#0B4FA8" strokeWidth={2} dot={{ r: 4 }} />
              <Line type="monotone" dataKey="Aptitude" stroke="#10B981" strokeWidth={1.5} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="Coding" stroke="#F59E0B" strokeWidth={1.5} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="Technical" stroke="#EF4444" strokeWidth={1.5} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="HR" stroke="#38bdf8" strokeWidth={1.5} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Session History */}
      <div className="panel-card">
        <h3>Interview History</h3>
        {sessions.length === 0 ? (
          <div className="empty-state">
            <BarChart2 size={40} />
            <p>No interviews yet. Start your first one!</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  {['Date', 'Company', 'Rounds', 'Score', 'Action'].map(h => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
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
                    <td>
                      <button className="btn ghost" style={{ fontSize: '0.75rem', padding: '4px 12px' }} onClick={() => setSelectedSession(s.session_id)}>View</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Session Detail Modal */}
      {selectedSession && (
        <SessionDetailModal sessionId={selectedSession} onClose={() => setSelectedSession(null)} />
      )}
    </div>
  )
}

export { DashboardPage }
