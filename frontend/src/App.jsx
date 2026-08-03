import React, { Suspense, useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { resetProctoringState, usePersistentProctoring } from './proctoring/proctoringState'
import { processAptitudeText } from './utils/aptitudeFormat'
import { AuthPage } from './components/AuthPage'
import { Shell } from './components/Shell'
import { Home } from './components/Home'
import { ResumePage } from './components/ResumePage'
import { CompanyPage } from './components/CompanyPage'
import { TerminatedPage } from './components/TerminatedPage'
import { ToastProvider } from './utils/ToastContext'

const RoundPage = React.lazy(() => import('./components/RoundPage').then(m => ({ default: m.RoundPage })))
const LiveInterview = React.lazy(() => import('./components/LiveInterview').then(m => ({ default: m.LiveInterview })))
const AIInterviewer = React.lazy(() => import('./components/AIInterviewer'))
const ReportPage = React.lazy(() => import('./components/ReportPage').then(m => ({ default: m.ReportPage })))
const DashboardPage = React.lazy(() => import('./components/DashboardPage').then(m => ({ default: m.DashboardPage })))
const RecruiterPage = React.lazy(() => import('./components/RecruiterPage').then(m => ({ default: m.RecruiterPage })))

function PageLoader() {
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
      <div className="spinner" />
    </div>
  )
}

function getStoredUser() {
  try {
    const stored = localStorage.getItem('mockRecruitmentUser')
    if (!stored) return null
    const user = JSON.parse(stored)
    if (!user?.email) return null
    return {
      name: user.name || user.email.split('@')[0] || 'Candidate',
      email: user.email,
      role: user.role || 'candidate',
      token: user.token || ''
    }
  } catch {
    localStorage.removeItem('mockRecruitmentUser')
    return null
  }
}

const FLOW_STORAGE_KEY = 'mockRecruitmentFlow'

function restoreFlowState() {
  try {
    const stored = localStorage.getItem(FLOW_STORAGE_KEY)
    if (!stored) return null
    const s = JSON.parse(stored)
    if (!s) return null
    return {
      stage: s.stage || 'resume',
      sessionId: s.sessionId || '',
      resume: s.resume || null,
      company: s.company || '',
      selectedCompanies: Array.isArray(s.selectedCompanies) ? s.selectedCompanies : [],
      rounds: Array.isArray(s.rounds) ? s.rounds : []
    }
  } catch {
    return null
  }
}

function shuffle(array) {
  const a = [...array]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

function pickRandom(arr, count) {
  const pool = shuffle(arr)
  return pool.slice(0, Math.min(count, pool.length))
}

function buildAptitudeRound(allQuestions) {
  const bySection = { quantitative: [], logical: [], verbal: [] }
  for (const q of allQuestions) {
    const sec = q.section
    if (bySection[sec]) bySection[sec].push(q)
  }
  const quant = pickRandom(bySection.quantitative, 14)
  const logical = pickRandom(bySection.logical, 8)
  const verbal = pickRandom(bySection.verbal, 8)
  return [...quant, ...logical, ...verbal]
}

function filterQuestions(questions, selectedCompanies) {
  if (!selectedCompanies?.length) {
    return shuffle(questions)
  }
  const filtered = questions.filter((q) => {
    if (!q.company) return true
    return q.company.some((c) => selectedCompanies.includes(c))
  })
  return shuffle(filtered)
}

export default function App() {
  const [user, setUser] = useState(getStoredUser)
  const [proctoring, setProctoring] = usePersistentProctoring()
  const [dataLoading, setDataLoading] = useState(true)
  const [dataError, setDataError] = useState(false)
  const [state, setState] = useState({
    stage: 'resume',
    sessionId: '',
    resume: null,
    company: '',
    selectedCompanies: [],
    rounds: [],
    companies: {},
    datasets: {
      aptitude: [],
      coding: [],
      technical: []
    },
    ...restoreFlowState()
  })

  const fetchData = () => {
    setDataLoading(true)
    setDataError(false)
    Promise.all([
      api.get('/companies'),
      fetch('/questions/aptitude.json').then(r => r.json()),
      api.get('/questions/coding'),
      api.get('/questions/technical')
    ]).then(([companies, aptitudeData, coding, technical]) => {
      let aptitude = aptitudeData.questions || aptitudeData
      aptitude = processAptitudeText(aptitude)
      setState((s) => ({ ...s, companies, datasets: { aptitude, coding, technical } }))
    }).catch(() => {
      setDataError(true)
    }).finally(() => {
      setDataLoading(false)
    })
  }

  useEffect(() => { fetchData() }, [])

  useEffect(() => {
    try {
      localStorage.setItem(FLOW_STORAGE_KEY, JSON.stringify({
        stage: state.stage,
        sessionId: state.sessionId,
        resume: state.resume,
        company: state.company,
        selectedCompanies: state.selectedCompanies,
        rounds: state.rounds
      }))
    } catch {
      /* storage quota exceeded — skip persistence */
    }
  }, [state])

  const logout = () => {
    localStorage.removeItem('mockRecruitmentUser')
    localStorage.removeItem(FLOW_STORAGE_KEY)
    setProctoring(resetProctoringState())
    setUser(null)
  }

  if (!user) return <AuthPage onAuth={setUser} />

  if (state.stage === 'terminated' || window.location.pathname === '/terminated') {
    return <TerminatedPage />
  }

  if (dataLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <div className="spinner" />
      </div>
    )
  }

  if (dataError) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', height: '100vh', color: '#94a3b8', gap: '16px' }}>
        <p>Failed to load application data.</p>
        <button className="btn primary" onClick={fetchData}>Retry</button>
      </div>
    )
  }

  return (
    <ToastProvider>
      <Shell state={state} user={user} onLogout={logout} proctoring={proctoring}>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/resume" element={<ResumePage state={state} setState={setState} setProctoring={setProctoring} />} />
            <Route path="/company" element={<CompanyPage state={state} setState={setState} user={user} />} />
            <Route path="/aptitude" element={<RoundPage key="aptitude" title="Aptitude Round" type="aptitude" pool={state.datasets.aptitude} build={buildAptitudeRound} state={state} setState={setState} proctoring={proctoring} setProctoring={setProctoring} />} />
            <Route path="/coding" element={<RoundPage key="coding" title="Coding Round" type="coding" pool={state.datasets.coding} build={(pool) => filterQuestions(pool, state.selectedCompanies).slice(0, 3)} state={state} setState={setState} proctoring={proctoring} setProctoring={setProctoring} />} />
            
            {/* Swapped legacy LiveInterview with our new AIInterviewer component */}
            <Route path="/technical" element={<AIInterviewer sessionId={state.sessionId} token={user.token} role="Software Engineer" company={state.company || 'the company'} proctoring={proctoring} setProctoring={setProctoring} onComplete={(report) => { console.log('Final Report:', report); window.location.href = '/report'; }} />} />

            <Route path="/report" element={<ReportPage state={state} proctoring={proctoring} />} />
            <Route path="/dashboard" element={<DashboardPage user={user} />} />
            <Route path="/recruiter" element={user?.role === 'recruiter' || user?.role === 'admin' ? <RecruiterPage user={user} /> : <Navigate to="/dashboard" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Shell>
    </ToastProvider>
  )
}
