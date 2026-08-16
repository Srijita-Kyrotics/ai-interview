import React, { Suspense, useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api, isTokenExpired, AUTH_EVENT } from './api'
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

// Full-screen interview room: rendered outside the app Shell so Obi owns the
// entire viewport (no sidebar / topbar chrome).
function AiInterviewRoute({ state, setState, user, proctoring, setProctoring }) {
  const navigate = useNavigate()
  return (
    <Suspense fallback={<PageLoader />}>
      <AIInterviewer
        sessionId={state.sessionId}
        token={user.token}
        resume={state.resume}
        role={undefined}
        company={state.company || 'the company'}
        proctoring={proctoring}
        setProctoring={setProctoring}
        onComplete={(report) => {
          console.log('Final Report:', report)
          setState((s) => ({ ...s, roundStatus: { ...s.roundStatus, technical: 'completed' } }))
          navigate('/report', { replace: true })
        }}
      />
    </Suspense>
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

const DEFAULT_ROUND_STATUS = {
  aptitude: 'not_started',
  coding: 'not_started',
  technical: 'not_started',
  hr: 'not_started',
  fullInterview: 'not_started'
}

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
      rounds: Array.isArray(s.rounds) ? s.rounds : [],
      roundStatus: { ...DEFAULT_ROUND_STATUS, ...(s.roundStatus || {}) }
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
  const navigate = useNavigate()
  const location = useLocation()
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
      technical: [],
      hr: []
    },
    roundStatus: { ...DEFAULT_ROUND_STATUS },
    ...restoreFlowState()
  })

  const fetchData = () => {
    setDataLoading(true)
    setDataError(false)
    Promise.all([
      api.get('/companies'),
      fetch('/questions/aptitude.json').then(r => r.json()),
      api.get('/questions/coding'),
      api.get('/questions/technical'),
      api.get('/questions/hr')
    ]).then(([companies, aptitudeData, coding, technical, hr]) => {
      let aptitude = aptitudeData.questions || aptitudeData
      aptitude = processAptitudeText(aptitude)
      setState((s) => ({ ...s, companies, datasets: { aptitude, coding, technical, hr } }))
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
        rounds: state.rounds,
        roundStatus: state.roundStatus
      }))
    } catch {
      /* storage quota exceeded — skip persistence */
    }
  }, [state])

  const logout = useCallback(() => {
    localStorage.removeItem('mockRecruitmentUser')
    localStorage.removeItem(FLOW_STORAGE_KEY)
    setProctoring(resetProctoringState())
    setUser(null)
  }, [setUser, setProctoring])

  useEffect(() => {
    if (isTokenExpired()) logout()
  }, [logout])

  useEffect(() => {
    const onAuthExpired = () => logout()
    window.addEventListener(AUTH_EVENT, onAuthExpired)
    return () => window.removeEventListener(AUTH_EVENT, onAuthExpired)
  }, [logout])

  const goToAiInterview = useCallback(async () => {
    if (state.sessionId) {
      setState((s) => ({ ...s, roundStatus: { ...s.roundStatus, technical: 'in_progress' } }))
      navigate('/technical')
      return
    }
    try {
      const res = await api.post('/ai-interview/create-session')
      setState((s) => ({
        ...s,
        sessionId: res.session_id,
        stage: 'technical',
        resume: res.resume,
        roundStatus: { ...s.roundStatus, technical: 'in_progress' }
      }))
      navigate('/technical')
    } catch (err) {
      if (err.status !== 401) {
        alert(`Could not start AI interview: ${err.message}`)
      }
    }
  }, [state.sessionId, navigate])

  if (!user) return <AuthPage onAuth={setUser} />

  if (state.stage === 'terminated' || window.location.pathname === '/terminated') {
    return <TerminatedPage />
  }

  // Dedicated full-screen interview room — no app chrome around it.
  if (location.pathname === '/technical') {
    return (
      <ToastProvider>
        <AiInterviewRoute state={state} setState={setState} user={user} proctoring={proctoring} setProctoring={setProctoring} />
      </ToastProvider>
    )
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
      <Shell state={state} user={user} onLogout={logout} proctoring={proctoring} onStartAiInterview={goToAiInterview}>
        <Suspense fallback={<PageLoader />}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/resume" element={<ResumePage state={state} setState={setState} setProctoring={setProctoring} />} />
            <Route path="/company" element={<CompanyPage state={state} setState={setState} user={user} />} />
            <Route path="/aptitude" element={<RoundPage key="aptitude" title="Aptitude Round" type="aptitude" pool={state.datasets.aptitude} build={buildAptitudeRound} state={state} setState={setState} proctoring={proctoring} setProctoring={setProctoring} />} />
            <Route path="/coding" element={<RoundPage key="coding" title="Coding Round" type="coding" pool={state.datasets.coding} build={(pool) => filterQuestions(pool, state.selectedCompanies).slice(0, 3)} state={state} setState={setState} proctoring={proctoring} setProctoring={setProctoring} />} />

            <Route path="/hr" element={<RoundPage key="hr" title="HR Round" type="hr" pool={state.datasets.hr} build={(pool) => (state.datasets.hr || []).slice(0, 8)} state={state} setState={setState} proctoring={proctoring} setProctoring={setProctoring} />} />

            <Route path="/report" element={<ReportPage state={state} proctoring={proctoring} />} />
            <Route path="/dashboard" element={<DashboardPage user={user} state={state} onStartAiInterview={goToAiInterview} />} />
            <Route path="/recruiter" element={user?.role === 'recruiter' || user?.role === 'admin' ? <RecruiterPage user={user} /> : <Navigate to="/dashboard" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </Shell>
    </ToastProvider>
  )
}
