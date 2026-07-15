import React, { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { resetProctoringState } from '../proctoring/proctoringState'

function ResumePage({ state, setState, setProctoring }) {
  const navigate = useNavigate()
  const [isParsing, setIsParsing] = useState(false)
  const [error, setError] = useState('')

  const onFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setIsParsing(true)
    setError('')
    const fd = new FormData()
    fd.append('file', file)
    try {
      const res = await api.post('/upload-resume', fd, true)
      if (res.error) throw new Error(res.error)
      setProctoring(resetProctoringState())
      setState((s) => ({ ...s, sessionId: res.session_id, resume: res.resume, company: '', rounds: [], stage: 'company' }))
      navigate('/company')
    } catch (err) {
      setError(err.message || 'Could not parse the resume.')
    } finally {
      setIsParsing(false)
    }
  }

  const resume = state.resume || {}
  const hasResume = Boolean(resume.name)

  const normalizeEntries = (items) => (Array.isArray(items) ? items.map((item) => (typeof item === 'string' ? { raw: item } : item)) : [])
  const education = normalizeEntries(resume.education)
  const experience = normalizeEntries(resume.experience)
  const projects = normalizeEntries(resume.projects)
  const certifications = normalizeEntries(resume.certifications)
  const skills = Array.isArray(resume.skills) ? resume.skills : []

  const renderEducationItem = (item, idx) => {
    const label = item.degree || item.title || item.raw || 'Education'
    const meta = [item.institution, item.duration].filter(Boolean).join(' • ')
    return (
      <li key={idx}>
        <strong>{label}</strong>
        {meta ? <small>{meta}</small> : null}
        {item.description ? <p>{item.description}</p> : null}
      </li>
    )
  }

  const renderExperienceItem = (item, idx) => {
    const label = item.role || item.title || item.raw || 'Experience'
    const meta = [item.company, item.duration].filter(Boolean).join(' • ')
    return (
      <li key={idx}>
        <strong>{label}</strong>
        {meta ? <small>{meta}</small> : null}
        {item.description ? <p>{item.description}</p> : null}
      </li>
    )
  }

  const renderProjectItem = (item, idx) => {
    const label = item.name || item.title || item.raw || 'Project'
    return (
      <li key={idx}>
        <strong>{label}</strong>
        {item.description ? <p>{item.description}</p> : null}
      </li>
    )
  }

  const renderCertificationItem = (item, idx) => {
    const label = item.name || item.raw || 'Certification'
    const meta = [item.issuer, item.year].filter(Boolean).join(' • ')
    return (
      <li key={idx}>
        <strong>{label}</strong>
        {meta ? <small>{meta}</small> : null}
      </li>
    )
  }

  return (
    <section className="content-grid">
      <div className="panel main-panel resume-panel">
        <div className="resume-head">
          <div>
            <p className="eyebrow">Step 01</p>
            <h2>Candidate Profile Analysis</h2>
            <p className="muted">Upload your resume and let our AI analyze your profile, extracting structured information from your education, experience, projects, certifications, and skills.</p>
          </div>
          <div className="resume-action">
            <span className="resume-file-label">Supported: TXT, text-readable PDF</span>
          </div>
        </div>

        <label className="upload-zone">
          <input type="file" accept=".pdf,.txt" onChange={onFile} />
          <span className="upload-icon">+</span>
          <b>{isParsing ? 'Parsing resume...' : 'Drop or choose a resume file'}</b>
          <small>Use a text-readable PDF or TXT resume for the most accurate extraction.</small>
        </label>
        {error ? <div className="notice danger">{error}</div> : null}

        {hasResume ? (
          <div className="resume-card">
            <div className="resume-card-header">
              <div>
                <p className="eyebrow">Candidate Overview</p>
                <h3>{resume.name}</h3>
                <p className="muted">{resume.email || 'Email not found'}{resume.phone ? ` • ${resume.phone}` : ''}</p>
              </div>
              <div className="company-logo badge-logo">{resume.name?.slice(0, 2).toUpperCase()}</div>
            </div>
            <div className="resume-chip">Qualification: {resume.qualification || 'N/A'}</div>
            <div className="detail-grid">
              <div className="detail-block">
                <span>Profile summary</span>
                <p>{resume.summary || 'A motivated candidate with practical experience in building scalable applications.'}</p>
              </div>
              <div className="detail-block">
                <span>Education</span>
                <ul>{education.length ? education.slice(0, 4).map(renderEducationItem) : <li>No education details found</li>}</ul>
              </div>
              <div className="detail-block">
                <span>Experience</span>
                <ul>{experience.length ? experience.slice(0, 4).map(renderExperienceItem) : <li>No experience details found</li>}</ul>
              </div>
              <div className="detail-block">
                <span>Projects</span>
                <ul>{projects.length ? projects.slice(0, 4).map(renderProjectItem) : <li>No project details found</li>}</ul>
              </div>
            </div>
            <div className="certification-panel">
              <div className="detail-block full-width">
                <span>Certifications</span>
                <ul>{certifications.length ? certifications.slice(0, 6).map(renderCertificationItem) : <li>No certifications found</li>}</ul>
              </div>
            </div>
            <div className="skill-cloud">
              {skills.length ? skills.map((skill) => <span key={skill}>{skill}</span>) : <span>No skills extracted</span>}
            </div>
          </div>
        ) : null}
      </div>

      <div className="panel insight-panel">
        <p className="eyebrow">Parsed snapshot</p>
        {hasResume ? (
          <div className="parsed-list">
            <div>
              <strong>Name</strong>
              <p>{resume.name}</p>
            </div>
            <div>
              <strong>Email</strong>
              <p>{resume.email || 'Not found'}</p>
            </div>
            <div>
              <strong>Phone</strong>
              <p>{resume.phone || 'Not found'}</p>
            </div>
            <div>
              <strong>Qualification</strong>
              <p>{resume.qualification || 'Not found'}</p>
            </div>
            <div>
              <strong>Top skills</strong>
              <p>{skills.slice(0, 8).join(', ') || 'N/A'}</p>
            </div>
            <div>
              <strong>Key projects</strong>
              <p>{projects.slice(0, 3).map((item) => item.name || item.raw).join('; ') || 'N/A'}</p>
            </div>
          </div>
        ) : (
          <div className="empty-state">
            <b>No resume parsed yet</b>
            <p>Upload a resume to see extracted candidate details.</p>
          </div>
        )}
      </div>
    </section>
  )
}

export { ResumePage }
