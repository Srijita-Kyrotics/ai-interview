import React, { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Bot, CheckCircle, LayoutDashboard, Shield, Menu, X, Play } from 'lucide-react'
import { steps } from '../constants'

function Shell({ state, user, onLogout, proctoring, onStartAiInterview, children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const routeStage = location.pathname.split('/')[1] || 'resume'
  const isRecruiter = user?.role === 'recruiter' || user?.role === 'admin'
  const isDashboard = routeStage === 'dashboard'
  const isRecruiterPage = routeStage === 'recruiter'

  const isRoundCompleted = (stepKey) => (state.roundStatus?.[stepKey] || 'not_started') === 'completed'

  const handleNav = (path) => {
    navigate(path)
    setSidebarOpen(false)
  }

  const handleAiInterview = () => {
    setSidebarOpen(false)
    onStartAiInterview && onStartAiInterview()
  }

  return (
    <div className="app-shell">
      <div className="orb orb-1" aria-hidden="true" />
      <div className="orb orb-2" aria-hidden="true" />
      <div className="orb orb-3" aria-hidden="true" />

      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="brand-row">
          <div className="brand-mark small">AI</div>
          <div>
            <div className="app-name">AI Interview Coach</div>
            <div className="muted tiny">{isRecruiter ? 'Recruiter Portal' : 'Candidate Workspace'}</div>
          </div>
        </div>

        <div className="user-strip">
          <div className="avatar">{(user.name || user.email || 'C').slice(0, 1).toUpperCase()}</div>
          <div>
            <div className="user-name">{user.name}</div>
            <div className="muted tiny" style={{ textTransform: 'capitalize' }}>{user.role || 'candidate'}</div>
          </div>
        </div>

        <nav className="step-list">
          <button
            type="button"
            onClick={() => handleNav('/dashboard')}
            className={`step-item ${isDashboard ? 'active' : ''}`}
          >
            <span><LayoutDashboard size={15} /></span>
            <b>Dashboard</b>
          </button>

          {isRecruiter && (
            <button
              type="button"
              onClick={() => handleNav('/recruiter')}
              className={`step-item ${isRecruiterPage ? 'active' : ''}`}
            >
              <span><Shield size={15} /></span>
              <b>Recruiter Portal</b>
            </button>
          )}

          <button
            type="button"
            onClick={handleAiInterview}
            className={`step-item ai-interview-nav ${routeStage === 'technical' ? 'active' : ''}`}
            title="Jump straight into the Jack interview"
          >
            <span><Bot size={15} /></span>
            <b>Interview with Jack</b>
          </button>

          <div className="sidebar-divider" />

          {steps.map((step) => {
            const active = routeStage === step.key || state.stage === step.key
            const isCompleted = isRoundCompleted(step.key)
            return (
              <React.Fragment key={step.key}>
                <button
                  type="button"
                  onClick={() => handleNav(`/${step.key}`)}
                  className={`step-item ${active ? 'active' : ''} ${isCompleted ? 'completed' : ''}`}
                >
                  <span>
                    {isCompleted
                      ? <CheckCircle size={15} />
                      : step.icon
                        ? <step.icon size={15} />
                        : step.badge
                    }
                  </span>
                  <b>{step.label}</b>
                </button>
                {step.key === 'hr' && (
                  <button
                    type="button"
                    onClick={() => handleNav('/resume')}
                    className={`step-item full-interview-nav ${routeStage === 'resume' ? 'active' : ''}`}
                    title="Start the complete multi-round interview"
                  >
                    <span><Play size={15} /></span>
                    <b>Full Interview</b>
                  </button>
                )}
              </React.Fragment>
            )
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="tiny muted">Company</div>
          <div className="session-value">{state.company || 'Not selected'}</div>
          <button className="btn ghost full" type="button" onClick={onLogout}>Sign out</button>
        </div>
      </aside>

      {sidebarOpen && <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />}

      <main className="workspace">
        <header className="topbar">
          <button className="hamburger-btn" type="button" onClick={() => setSidebarOpen(!sidebarOpen)}>
            {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
          <div>
            <div className="eyebrow">Simulation flow</div>
            <h1>{isDashboard ? 'Dashboard' : isRecruiterPage ? 'Recruiter Portal' : steps.find((step) => step.key === routeStage)?.label || 'Resume Upload'}</h1>
          </div>
          <div className="status-pills">
            <span>{state.sessionId ? '✦ Resume parsed' : '○ Awaiting resume'}</span>
            <span>{state.company ? `◈ ${state.company}` : '○ Company pending'}</span>
          </div>
        </header>
        {children}
      </main>
    </div>
  )
}

export { Shell }
