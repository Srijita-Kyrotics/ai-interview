import React, { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { COMPANY_META, COMPANY_GROUPS, ROLE_MAPPINGS } from '../constants'

function recommendRoles(skills) {
  if (!skills || !skills.length) return []
  const userSkills = skills.map(s => s.toLowerCase())
  const scores = Object.entries(ROLE_MAPPINGS).map(([role, meta]) => {
    const matched = meta.keywords.filter(rs => userSkills.some(us => us.includes(rs)))
    const matchPercentage = Math.round((matched.length / meta.keywords.length) * 100)
    return { role, matchPercentage, matched, difficulty: meta.difficulty, techStack: meta.techStack }
  }).filter(r => r.matchPercentage > 0)
  return scores.sort((a, b) => b.matchPercentage - a.matchPercentage).slice(0, 4)
}

function renderCompanyCard(company, selectedCompanies, toggleCompany) {
  const info = COMPANY_META[company] || {
    fullName: company,
    initials: company.slice(0, 3).toUpperCase(),
    accent: '#60a5fa',
    bg: 'rgba(96, 165, 250, 0.08)',
    type: 'service'
  }
  const isSelected = selectedCompanies.includes(company)
  const typeBadgeLabel = info.type === 'product' ? 'Product' : info.type === 'both' ? 'Product + Service' : 'Service'
  const typeBadgeClass = info.type === 'product' ? 'type-product' : info.type === 'both' ? 'type-both' : 'type-service'

  return (
    <button
      key={company}
      type="button"
      onClick={() => toggleCompany(company)}
      className={`company-card ${isSelected ? 'selected-company' : ''}`}
      style={{
        borderColor: isSelected ? '#22c55e' : info.accent,
        background: isSelected ? 'rgba(34,197,94,0.15)' : info.bg,
        transform: isSelected ? 'scale(1.02)' : 'scale(1)'
      }}
    >
      <div className="company-logo" style={{ borderColor: info.accent, color: info.accent }}>
        {info.logo ? (
          <img className={info.logoClass || ''} src={info.logo} alt={`${info.fullName} logo`}
            onError={(event) => {
              event.currentTarget.style.display = 'none'
              event.currentTarget.nextElementSibling.style.display = 'grid'
            }}
          />
        ) : null}
        <span className="company-logo-fallback" style={{ display: info.logo ? 'none' : 'grid' }}>{info.initials}</span>
      </div>
      <div className="company-copy" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
        <div>
          <h3 style={{ marginBottom: 4 }}>{info.fullName || company}</h3>
          <span className={`company-type-badge ${typeBadgeClass}`}>{typeBadgeLabel}</span>
        </div>
        <div className={`company-check-pill ${isSelected ? 'checked' : ''}`}>
          {isSelected ? (
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M2.5 7L5.5 10L11.5 4" stroke="white" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          ) : null}
        </div>
      </div>
    </button>
  )
}

function CompanyPage({ state, setState }) {
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [selectedCompanies, setSelectedCompanies] = useState([])
  const [mode, setMode] = useState('company') // 'company' or 'role'

  const toggleCompany = (company) => {
    setSelectedCompanies((prev) => {
      if (prev.includes(company)) {
        return prev.filter((c) => c !== company)
      }
      return [...prev, company]
    })
  }


  const startAssessment = async (overrideCompanies = null, isRoleMode = false) => {
    // For role-based mode: use all available companies as the question pool
    // so the backend returns all rounds; we always begin at aptitude
    const companiesToStart = isRoleMode
      ? Object.keys(state.companies)
      : (overrideCompanies || selectedCompanies)

    if (!isRoleMode && !companiesToStart.length) {
      setError('Please select at least one company.')
      return
    }

    const res = await api.post('/select-company', {
      session_id: state.sessionId,
      companies: companiesToStart
    })

    if (res.error) {
      setError(res.error)
      return
    }

    setState((s) => ({
      ...s,
      company: isRoleMode
        ? (overrideCompanies?.[0] || 'Role-Based')
        : companiesToStart.join(', '),
      selectedCompanies: companiesToStart,
      rounds: res.rounds,
      stage: 'aptitude'
    }))

    navigate('/aptitude')
  }

  if (!state.sessionId) return <Navigate to="/resume" replace />

  const recommendedRoles = recommendRoles(state.resume?.skills || [])

  return (
    <section className="panel main-panel">
      <div className="section-head">
        <div>
          <p className="eyebrow">Step 02</p>
          <h2>Targeted Companies & Roles</h2>
          <p className="muted">
            Choose your preferred mode to generate targeted interview questions.
          </p>
        </div>
        <div className="resume-chip">
          <b>{state.resume?.name || 'Candidate'}</b>
          <span>{(state.resume?.skills || []).slice(0, 3).join(' / ')}</span>
        </div>
      </div>

      <div className="mode-toggle">
        <button
          className={mode === 'company' ? 'active' : ''}
          onClick={() => setMode('company')}
          type="button"
        >
          Company-Based Assessment
        </button>
        <button
          className={mode === 'role' ? 'active' : ''}
          onClick={() => setMode('role')}
          type="button"
        >
          Role-Based Assessment
        </button>
      </div>

      {error ? <div className="notice danger">{error}</div> : null}

      {mode === 'company' ? (
        <>
          <div style={{ marginBottom: '1rem', display: 'flex', gap: '10px' }}>
            <button className="btn ghost" type="button" onClick={() => setSelectedCompanies(Object.keys(state.companies))}>Select All</button>
            <button className="btn ghost" type="button" onClick={() => setSelectedCompanies([])}>Clear</button>
          </div>

          {COMPANY_GROUPS.map((group) => {
            const companies = group.companies.filter((company) => state.companies[company])
            if (!companies.length) return null

            return (
              <div className="company-group" key={group.key}>
                <div className="company-group-header">
                  <span className={`company-group-badge ${group.key}`}>{group.badge}</span>
                  <span className="company-group-sub">{group.sub}</span>
                </div>
                <div className="company-grid">
                  {companies.map(company => renderCompanyCard(company, selectedCompanies, toggleCompany))}
                </div>
              </div>
            )
          })}

          <div className="assessment-btn-wrap">
            <button className="btn primary" type="button" onClick={() => startAssessment()}>
              {selectedCompanies.length === 0
                ? 'Select Companies to Begin'
                : selectedCompanies.length === 1
                  ? `Start Assessment for ${selectedCompanies[0]} →`
                  : `Start Assessment for ${selectedCompanies.slice(0, -1).join(', ')} and ${selectedCompanies[selectedCompanies.length - 1]} →`
              }
            </button>
            {selectedCompanies.length > 0 && (
              <span className="muted tiny">{selectedCompanies.length} {selectedCompanies.length === 1 ? 'company' : 'companies'} selected</span>
            )}
          </div>
        </>
      ) : (
        <>
          <div className="role-section-head">
            <div className="ai-badge">✦ AI Analysis</div>
            <h3>Recommended Roles Based on Your Resume</h3>
          </div>
          {recommendedRoles.length > 0 ? (
            <div className="role-grid">
              {recommendedRoles.map((rec) => (
                <div key={rec.role} className="role-card">
                  <h3>{rec.role}</h3>
                  <div className="role-card-meta">
                    <span className="match-badge">⬆ {rec.matchPercentage}% Match</span>
                    {rec.difficulty && (
                      <span className={`difficulty-badge ${rec.difficulty}`}>
                        {rec.difficulty}
                      </span>
                    )}
                  </div>
                  <div className="skills-list">
                    {rec.matched.map(skill => <span key={skill}>{skill}</span>)}
                  </div>
                  {rec.techStack && rec.techStack.length > 0 && (
                    <div className="tech-stack-row">
                      {rec.techStack.map(tech => <span key={tech} className="tech-chip">{tech}</span>)}
                    </div>
                  )}
                  <button className="btn primary full" type="button" onClick={() => startAssessment([rec.role], true)}>
                    Start {rec.role} Test →
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">
              <b>No precise roles detected</b>
              <p>We couldn't extract enough matching skills from your resume to suggest a specific role. Please use the Company-Based Assessment mode.</p>
            </div>
          )}
        </>
      )}
    </section>
  )
}

export { CompanyPage }
