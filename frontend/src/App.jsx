import React, { Suspense, useEffect, useMemo, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { resetProctoringState, usePersistentProctoring } from './proctoring/proctoringState'
import { processAptitudeText } from './components/RoundPage'
import { AuthPage } from './components/AuthPage'
import { Shell } from './components/Shell'
import { Home } from './components/Home'
import { ResumePage } from './components/ResumePage'
import { CompanyPage } from './components/CompanyPage'
import { TerminatedPage } from './components/TerminatedPage'

const RoundPage = React.lazy(() => import('./components/RoundPage').then(m => ({ default: m.RoundPage })))
const ChatInterview = React.lazy(() => import('./components/ChatInterview').then(m => ({ default: m.ChatInterview })))
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
  const quant = pickRandom(bySection.quantitative, 25)
  const logical = pickRandom(bySection.logical, 15)
  const verbal = pickRandom(bySection.verbal, 15)
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
      technical: [],
      hr: []
    }
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

  const aptitudeItems = useMemo(() => {
    return buildAptitudeRound(state.datasets.aptitude)
  }, [state.datasets.aptitude, state.sessionId])

  const codingItems = useMemo(() => {
    return filterQuestions(state.datasets.coding, state.selectedCompanies)
  }, [state.datasets.coding, state.selectedCompanies])

  const technicalItems = useMemo(() => {
    return filterQuestions(state.datasets.technical, state.selectedCompanies)
  }, [state.datasets.technical, state.selectedCompanies])

  const hrItems = useMemo(() => {
    return filterQuestions(state.datasets.hr, state.selectedCompanies)
  }, [state.datasets.hr, state.selectedCompanies])

  const logout = () => {
    localStorage.removeItem('mockRecruitmentUser')
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
    <Shell state={state} user={user} onLogout={logout} proctoring={proctoring}>
      <Suspense fallback={<PageLoader />}>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/resume" element={<ResumePage state={state} setState={setState} setProctoring={setProctoring} />} />
          <Route path="/company" element={<CompanyPage state={state} setState={setState} />} />
          <Route path="/aptitude" element={<RoundPage key="aptitude" title="Aptitude Round" items={aptitudeItems} type="aptitude" state={state} setState={setState} proctoring={proctoring} setProctoring={setProctoring} />} />
          <Route path="/coding" element={<RoundPage key="coding" title="Coding Round" items={codingItems} type="coding" state={state} setState={setState} proctoring={proctoring} setProctoring={setProctoring} />} />
          <Route path="/technical" element={<ChatInterview key="technical" title="Technical Interview" questions={technicalItems} state={state} setState={setState} proctoring={proctoring} setProctoring={setProctoring} />} />
          <Route path="/hr" element={<ChatInterview key="hr" title="HR Interview" questions={hrItems} state={state} setState={setState} proctoring={proctoring} setProctoring={setProctoring} />} />
          <Route path="/report" element={<ReportPage state={state} proctoring={proctoring} />} />
          <Route path="/dashboard" element={<DashboardPage user={user} />} />
          <Route path="/recruiter" element={user?.role === 'recruiter' || user?.role === 'admin' ? <RecruiterPage user={user} /> : <Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Shell>
  )
}
