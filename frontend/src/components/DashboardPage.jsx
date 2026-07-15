import React, { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BarChart2, Building2, Calendar, TrendingUp, Award } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'
import { api } from '../api'
import { SessionDetailModal } from './SessionDetailModal'

function DashboardPage({ user }) {
  const navigate = useNavigate()
  const [stats, setStats] = useState(null)
  const [sessions, setSessions] = useState([])
  const [selectedSession, setSelectedSession] = useState(null)
  const [loading, setLoading] = useState(true)

  const fetchData = () => {
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
      <div className="dashboard-page" style={{ padding: '2rem', textAlign: 'center' }}>
        <div className="loading-spinner" />
        <p className="muted" style={{ marginTop: '1rem' }}>Loading your dashboard...</p>
      </div>
    )
  }

  return (
    <div className="dashboard-page" style={{ padding: '1.5rem', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#f1f5f9' }}>Your Dashboard</h2>
          <p className="muted" style={{ fontSize: '0.85rem' }}>Track your interview performance over time</p>
        </div>
        <button className="btn primary" onClick={() => navigate('/resume')}>Start New Interview</button>
      </div>

      {/* Stats Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        {[
          { label: 'Total Interviews', value: stats?.total_interviews || 0, icon: Calendar, color: '#818cf8' },
          { label: 'Average Score', value: `${stats?.overall_avg || 0}%`, icon: TrendingUp, color: '#34d399' },
          { label: 'Best Score', value: `${stats?.best_score || 0}%`, icon: Award, color: '#fbbf24' },
          { label: 'Companies Practiced', value: stats?.companies_practiced?.length || 0, icon: Building2, color: '#f87171' },
        ].map((card, i) => (
          <div key={i} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '12px', padding: '1.25rem', border: '1px solid rgba(255,255,255,0.06)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: `${card.color}20`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <card.icon size={20} color={card.color} />
              </div>
              <div>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#f1f5f9' }}>{card.value}</div>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>{card.label}</div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Performance Chart */}
      {chartData.length > 1 && (
        <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '12px', padding: '1.5rem', border: '1px solid rgba(255,255,255,0.06)', marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#f1f5f9', marginBottom: '1rem' }}>Performance Trend</h3>
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="date" stroke="#64748b" fontSize={12} />
              <YAxis stroke="#64748b" fontSize={12} domain={[0, 100]} />
              <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#f1f5f9' }} />
              <Legend />
              <Line type="monotone" dataKey="Overall" stroke="#818cf8" strokeWidth={2} dot={{ r: 4 }} />
              <Line type="monotone" dataKey="Aptitude" stroke="#34d399" strokeWidth={1.5} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="Coding" stroke="#fbbf24" strokeWidth={1.5} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="Technical" stroke="#f87171" strokeWidth={1.5} dot={{ r: 3 }} />
              <Line type="monotone" dataKey="HR" stroke="#38bdf8" strokeWidth={1.5} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Session History */}
      <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: '12px', padding: '1.5rem', border: '1px solid rgba(255,255,255,0.06)' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#f1f5f9', marginBottom: '1rem' }}>Interview History</h3>
        {sessions.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
            <BarChart2 size={40} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
            <p>No interviews yet. Start your first one!</p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                  {['Date', 'Company', 'Rounds', 'Score', 'Action'].map(h => (
                    <th key={h} style={{ padding: '0.75rem', textAlign: 'left', color: '#94a3b8', fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sessions.map((s) => (
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
                    <td style={{ padding: '0.75rem', color: s.overall_score >= 70 ? '#34d399' : s.overall_score >= 50 ? '#fbbf24' : '#f87171', fontWeight: 600 }}>{s.overall_score}%</td>
                    <td style={{ padding: '0.75rem' }}>
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
