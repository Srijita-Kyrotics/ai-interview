import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { jsPDF } from 'jspdf'
import { ProctoringModal, ProctoringPanel, SnapshotGrid, ViolationTimeline } from './proctoring/ProctoringUI'
import { calculateInterviewScores, resetProctoringState, usePersistentProctoring } from './proctoring/proctoringState'
import { useAssessmentProctoring } from './proctoring/useAssessmentProctoring'
import { formatQuestionText } from './utils/questionFormat'
import { FileText, Building2, Brain, Code2, MessageSquare, Users, BarChart2, CheckCircle, LayoutDashboard, Shield, TrendingUp, Calendar, Award, Search } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

function getAuthToken() {
  try {
    const stored = localStorage.getItem('mockRecruitmentUser')
    if (stored) {
      const user = JSON.parse(stored)
      return user?.token || ''
    }
  } catch {}
  return ''
}

const api = {
  get: async (path) => {
    const token = getAuthToken()
    const headers = token ? { 'Authorization': `Bearer ${token}` } : {}
    return (await fetch(`${API}${path}`, { headers })).json()
  },
  post: async (path, body, isForm = false) => {
    const token = getAuthToken()
    const headers = isForm ? {} : { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`
    return (await fetch(`${API}${path}`, {
      method: 'POST',
      headers,
      body: isForm ? body : JSON.stringify(body)
    })).json()
  }
}

const steps = [
  { key: 'resume', label: 'Upload Resume', badge: '01', icon: FileText },
  { key: 'company', label: 'Targeted Companies', badge: '02', icon: Building2 },
  { key: 'aptitude', label: 'Aptitude', badge: '03', icon: Brain },
  { key: 'coding', label: 'Coding', badge: '04', icon: Code2 },
  { key: 'technical', label: 'Technical', badge: '05', icon: MessageSquare },
  { key: 'hr', label: 'HR Interview', badge: '06', icon: Users },
  { key: 'report', label: 'Report', badge: '07', icon: BarChart2 }
]

const roundDurations = {
  aptitude: 20,
  coding: 10 * 60
}

const interviewQuestionDuration = 5 * 60

const COMPANY_META = {
  // ── Product-Based ──────────────────────────────────────
  Google: {
    fullName: 'Google LLC',
    initials: 'G',
    logo: '/logo/google-logo.jpg',
    logoClass: 'logo-google',
    accent: '#eab308',
    bg: 'rgba(234,179,8,0.08)',
    type: 'product'
  },
  Microsoft: {
    fullName: 'Microsoft Corporation',
    initials: 'MS',
    logo: '/logo/microsoft-logo-4.png',
    logoClass: 'logo-microsoft',
    accent: '#2563eb',
    bg: 'rgba(37,99,235,0.08)',
    type: 'product'
  },
  Amazon: {
    fullName: 'Amazon.com, Inc.',
    initials: 'AMZ',
    logo: '/logo/amazon logo.jpg',
    logoClass: 'logo-amazon',
    accent: '#ea580c',
    bg: 'rgba(249,115,22,0.08)',
    type: 'product'
  },
  Adobe: {
    fullName: 'Adobe Inc.',
    initials: 'ADB',
    logo: '/logo/Adobe-logo.png',
    logoClass: 'logo-adobe',
    accent: '#e13122',
    bg: 'rgba(225,49,34,0.08)',
    type: 'product'
  },
  Oracle: {
    fullName: 'Oracle Corporation',
    initials: 'ORC',
    logo: '/logo/oracle-logo.png',
    logoClass: 'logo-oracle',
    accent: '#c74634',
    bg: 'rgba(199,70,52,0.08)',
    type: 'product'
  },
  Salesforce: {
    fullName: 'Salesforce, Inc.',
    initials: 'SF',
    logo: '/logo/salesforce-logo.png',
    logoClass: 'logo-salesforce',
    accent: '#00a1e0',
    bg: 'rgba(0,161,224,0.08)',
    type: 'product'
  },
  Atlassian: {
    fullName: 'Atlassian Corporation',
    initials: 'ATL',
    logo: '/logo/Atlassian-Logo.jpg',
    logoClass: 'logo-atlassian',
    accent: '#0052cc',
    bg: 'rgba(0,82,204,0.08)',
    type: 'product'
  },
  NVIDIA: {
    fullName: 'NVIDIA Corporation',
    initials: 'NVD',
    logo: '/logo/nvidia-logo.png',
    logoClass: 'logo-nvidia',
    accent: '#76b900',
    bg: 'rgba(118,185,0,0.08)',
    type: 'product'
  },

  // ── Service-Based ───────────────────────────────────────
  TCS: {
    fullName: 'Tata Consultancy Services',
    initials: 'TCS',
    logo: '/logo/TCS-logo.jpg',
    logoClass: 'logo-tcs',
    accent: '#0369a1',
    bg: 'rgba(14,165,233,0.08)',
    type: 'service'
  },
  Infosys: {
    fullName: 'Infosys Limited',
    initials: 'INF',
    logo: '/logo/infosys-logo.jpg',
    logoClass: 'logo-infosys',
    accent: '#0f766e',
    bg: 'rgba(20,184,166,0.08)',
    type: 'service'
  },
  Wipro: {
    fullName: 'Wipro Limited',
    initials: 'WIP',
    logo: '/logo/wipro-logo.png',
    logoClass: 'logo-wipro',
    accent: '#1d4ed8',
    bg: 'rgba(59,130,246,0.08)',
    type: 'service'
  },
  HCLTech: {
    fullName: 'HCLTech',
    initials: 'HCL',
    logo: '/logo/hcl-tech.png',
    logoClass: 'logo-hcl',
    accent: '#00539b',
    bg: 'rgba(0,83,155,0.08)',
    type: 'service'
  },
  'Tech Mahindra': {
    fullName: 'Tech Mahindra Limited',
    initials: 'TM',
    logo: '/logo/tech-mahindra-logo.png',
    logoClass: 'logo-tech-mahindra',
    accent: '#e31937',
    bg: 'rgba(227,25,55,0.08)',
    type: 'service'
  },
  Cognizant: {
    fullName: 'Cognizant Technology Solutions',
    initials: 'CTS',
    logo: '/logo/cognizant-logo.jpg',
    logoClass: 'logo-cognizant',
    accent: '#334155',
    bg: 'rgba(148,163,184,0.08)',
    type: 'service'
  },
  Capgemini: {
    fullName: 'Capgemini',
    initials: 'CPG',
    logo: '/logo/capgemini-logo.jpg',
    logoClass: 'logo-capgemini',
    accent: '#0ea5e9',
    bg: 'rgba(14,165,233,0.08)',
    type: 'service'
  },
  LTIMindtree: {
    fullName: 'LTIMindtree Limited',
    initials: 'LTI',
    logo: '/logo/LTIMindtree_Logo.svg.png',
    logoClass: 'logo-ltimindtree',
    accent: '#6d28d9',
    bg: 'rgba(109,40,217,0.08)',
    type: 'service'
  },

  // ── Hybrid (Product + Service) ──────────────────────────
  Accenture: {
    fullName: 'Accenture',
    initials: 'ACN',
    logo: '/logo/accenture-logo.png',
    logoClass: 'logo-accenture',
    accent: '#7c3aed',
    bg: 'rgba(167,139,250,0.08)',
    type: 'both'
  },
  IBM: {
    fullName: 'IBM Corporation',
    initials: 'IBM',
    logo: '/logo/ibm-logo.png',
    logoClass: 'logo-ibm',
    accent: '#1f70c1',
    bg: 'rgba(31,112,193,0.08)',
    type: 'both'
  },
  SAP: {
    fullName: 'SAP SE',
    initials: 'SAP',
    logo: '/logo/SAP-Logo.svg.png',
    logoClass: 'logo-sap',
    accent: '#0070f2',
    bg: 'rgba(0,112,242,0.08)',
    type: 'both'
  },
  Cisco: {
    fullName: 'Cisco Systems, Inc.',
    initials: 'CSC',
    logo: '/logo/Cisco_logo_blue_2016.svg.png',
    logoClass: 'logo-cisco',
    accent: '#00bceb',
    bg: 'rgba(0,188,235,0.08)',
    type: 'both'
  },
  Zoho: {
    fullName: 'Zoho Corporation',
    initials: 'ZHO',
    logo: '/logo/ZOHO_logo_2023.svg.png',
    logoClass: 'logo-zoho',
    accent: '#e42527',
    bg: 'rgba(228,37,39,0.08)',
    type: 'both'
  },
  Freshworks: {
    fullName: 'Freshworks Inc.',
    initials: 'FW',
    logo: '/logo/freshworks-logo.png',
    logoClass: 'logo-freshworks',
    accent: '#22c55e',
    bg: 'rgba(34,197,94,0.08)',
    type: 'both'
  }
}

const COMPANY_GROUPS = [
  {
    key: 'product',
    badge: 'Product-Based',
    sub: 'Build and own world-class software products',
    companies: ['Google', 'Microsoft', 'Amazon', 'Adobe', 'Oracle', 'Salesforce', 'Atlassian', 'NVIDIA']
  },
  {
    key: 'service',
    badge: 'Service-Based',
    sub: 'Large IT services and consulting firms',
    companies: ['TCS', 'Infosys', 'Wipro', 'HCLTech', 'Tech Mahindra', 'Cognizant', 'Capgemini', 'LTIMindtree']
  },
  {
    key: 'hybrid',
    badge: 'Hybrid',
    sub: 'Companies with both product and service-led hiring tracks',
    companies: ['Accenture', 'IBM', 'SAP', 'Cisco', 'Zoho', 'Freshworks']
  }
]


function formatTime(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0')
  const seconds = (totalSeconds % 60).toString().padStart(2, '0')
  return `${minutes}:${seconds}`
}

function useSpeech() {
  const [muted, setMuted] = useState(false)
  const speak = (text) => {
    if (muted || !('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text))
  }
  return { muted, setMuted, speak }
}

function getSpeechRecognition() {
  return window.SpeechRecognition || window.webkitSpeechRecognition
}

function audioBlobToDataUrl(blob) {
  if (!blob) return Promise.resolve('')
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => resolve(reader.result || '')
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}

function CodeEditor({ value, onChange, language, starter, questionTitle }) {
  const lineCount = Math.max(1, value.split('\n').length)
  const charCount = value.length
  const onKeyDown = (event) => {
    if (event.key !== 'Tab') return
    event.preventDefault()
    const target = event.currentTarget
    const start = target.selectionStart
    const end = target.selectionEnd
    const nextValue = `${value.slice(0, start)}  ${value.slice(end)}`
    onChange(nextValue)
    window.requestAnimationFrame(() => {
      target.selectionStart = start + 2
      target.selectionEnd = start + 2
    })
  }

  return (
    <div className="leetcode-editor-shell">
      <div className="editor-toolbar">
        <div className="editor-title-stack">
          <span className="editor-kicker">Code</span>
          <strong>{questionTitle || 'Solution'}</strong>
        </div>
        <div className="editor-meta">
          <span>{language}</span>
          <span>{lineCount} lines</span>
          <span>{charCount} chars</span>
        </div>
      </div>
      <div className="code-editor-wrapper">
        <div className="editor-lines" aria-hidden="true">
          {Array.from({ length: lineCount }, (_, i) => (
            <div key={i} className="line-number">{i + 1}</div>
          ))}
        </div>
        <textarea
          className="code-editor"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={starter || 'Write your code here'}
          spellCheck="false"
        />
      </div>
    </div>
  )
}

function VoiceAnswerControls({ userStream, transcript, onTranscriptChange, onAudioChange }) {
  const [isRecording, setIsRecording] = useState(false)
  const [audioBlob, setAudioBlob] = useState(null)
  const [recordingTime, setRecordingTime] = useState(0)
  const [speechStatus, setSpeechStatus] = useState('')
  const mediaRecorderRef = useRef(null)
  const recognitionRef = useRef(null)
  const audioRef = useRef(null)
  const [audioUrl, setAudioUrl] = useState(null)

  useEffect(() => {
    if (!audioBlob) { setAudioUrl(null); return }
    const url = URL.createObjectURL(audioBlob)
    setAudioUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [audioBlob])

  useEffect(() => {
    if (!isRecording) return undefined
    const timer = window.setInterval(() => setRecordingTime((seconds) => seconds + 1), 1000)
    return () => window.clearInterval(timer)
  }, [isRecording])

  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current?.state === 'recording') mediaRecorderRef.current.stop()
      recognitionRef.current?.stop()
    }
  }, [])

  useEffect(() => {
    onAudioChange?.(audioBlob)
  }, [audioBlob, onAudioChange])

  const formatRecordingTime = (seconds) => {
    const mins = Math.floor(seconds / 60).toString().padStart(2, '0')
    const secs = (seconds % 60).toString().padStart(2, '0')
    return `${mins}:${secs}`
  }

  const startSpeechToText = () => {
    const Recognition = getSpeechRecognition()
    if (!Recognition) {
      setSpeechStatus('Speech-to-text is not supported in this browser. Your audio can still be replayed before submit.')
      return
    }
    const recognition = new Recognition()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'
    recognition.onresult = (event) => {
      let nextTranscript = ''
      for (let i = 0; i < event.results.length; i += 1) {
        nextTranscript += event.results[i][0].transcript
      }
      onTranscriptChange(nextTranscript.trim())
    }
    recognition.onerror = () => setSpeechStatus('Speech-to-text paused. You can type or re-record.')
    recognitionRef.current = recognition
    recognition.start()
    setSpeechStatus('Listening and transcribing...')
  }

  const startRecording = async () => {
    try {
      const audioTrack = userStream?.getAudioTracks?.()[0]
      const stream = audioTrack ? new MediaStream([audioTrack]) : await navigator.mediaDevices.getUserMedia({ audio: true })
      const chunks = []
      const recorder = new MediaRecorder(stream)
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data)
      }
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'audio/webm' })
        setAudioBlob(blob)
        if (!audioTrack) stream.getTracks().forEach((track) => track.stop())
      }
      mediaRecorderRef.current = recorder
      setAudioBlob(null)
      setRecordingTime(0)
      setIsRecording(true)
      setSpeechStatus('')
      recorder.start()
      startSpeechToText()
    } catch {
      setSpeechStatus('Could not start microphone recording. Please allow microphone access and try again.')
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === 'recording') mediaRecorderRef.current.stop()
    recognitionRef.current?.stop()
    setIsRecording(false)
    setSpeechStatus((status) => status || 'Recording saved.')
  }

  const reRecord = () => {
    setAudioBlob(null)
    onTranscriptChange('')
    startRecording()
  }

  return (
    <div className="voice-answer-card">
      <div className="voice-answer-head">
        <div>
          <span>Voice answer</span>
          <strong>{isRecording ? formatRecordingTime(recordingTime) : audioBlob ? 'Ready to review' : 'Not recorded'}</strong>
        </div>
        {isRecording ? <span className="recording-pill">Recording</span> : null}
      </div>
      <textarea
        className="input transcript-box"
        value={transcript}
        onChange={(e) => onTranscriptChange(e.target.value)}
        placeholder="Your speech-to-text transcript will appear here. You can edit it before submitting."
      />
      {speechStatus ? <p className="tiny muted">{speechStatus}</p> : null}
      <div className="playback-controls">
        {!isRecording ? (
          <button className="btn primary record-btn" type="button" onClick={startRecording}>
            {audioBlob ? 'Record Again' : 'Start Recording'}
          </button>
        ) : (
          <button className="btn danger record-btn" type="button" onClick={stopRecording}>Stop Recording</button>
        )}
        {audioBlob ? (
          <>
            <button className="btn ghost" type="button" onClick={() => audioRef.current?.play()}>Play</button>
            <button className="btn ghost" type="button" onClick={reRecord}>Re-record</button>
            <audio ref={audioRef} src={audioUrl} />
          </>
        ) : null}
      </div>
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

function AuthPage({ onAuth }) {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ name: '', email: '', password: '', confirmPassword: '', otp: '', captcha: '' })
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [otpStatus, setOtpStatus] = useState('')
  const [captcha, setCaptcha] = useState({ token: '', question: '' })
  const [isSendingOtp, setIsSendingOtp] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [otpRequested, setOtpRequested] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)
  const isCreate = mode === 'create'

  const loadCaptcha = async () => {
    const res = await api.get('/auth/captcha')
    setCaptcha({ token: res.token, question: res.question })
    setForm((current) => ({ ...current, captcha: '' }))
  }

  useEffect(() => {
    loadCaptcha()
  }, [])

  const updateField = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }))
    setError('')
    setFieldErrors((current) => ({ ...current, [key]: '' }))
  }

  const validateEmail = (value) => {
    if (!value) return 'Email is required.'
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return 'Enter a valid email address.'
    return ''
  }

  const validatePassword = (value) => {
    const trimmed = value?.trim() || ''
    if (!trimmed) return 'Password is required.'
    if (trimmed.length < 8) return 'Password must be at least 8 characters long.'
    if (!/[^A-Za-z0-9]/.test(trimmed)) return 'Password must include at least one special character.'
    return ''
  }

  const validateName = (value) => {
    if (isCreate && !value.trim()) return 'Your full name is required.'
    return ''
  }

  const validateConfirmPassword = (value) => {
    const trimmedValue = value?.trim() || ''
    const trimmedPassword = form.password?.trim() || ''
    if (!trimmedValue) return 'Please confirm your password.'
    if (trimmedValue !== trimmedPassword) return 'Passwords do not match.'
    return ''
  }

  const validateOtp = (value) => {
    if (!value) return 'Enter the one-time code sent to your email.'
    return ''
  }

  const validateCaptcha = (value) => {
    if (!value) return 'Enter the captcha answer.'
    return ''
  }

  const isEmailValid = Boolean(form.email && !validateEmail(form.email))
  const showCredentials = isEmailValid
  const passwordValidationMessage = form.password ? validatePassword(form.password) : 'Create a strong password to continue.'
  const confirmValidationMessage = isCreate ? (form.confirmPassword ? validateConfirmPassword(form.confirmPassword) : 'Confirm your password.') : ''
  const canRequestOtp = showCredentials && !passwordValidationMessage && (!isCreate || !confirmValidationMessage) && (!isCreate || !!form.name.trim())

  const sendOtp = async () => {
    const email = form.email.trim().toLowerCase()
    const password = form.password
    const emailError = validateEmail(email)
    const passwordError = validatePassword(password)
    const confirmError = isCreate ? validateConfirmPassword(form.confirmPassword) : ''
    const nameError = isCreate ? validateName(form.name) : ''

    const newErrors = {
      email: emailError,
      password: passwordError,
      confirmPassword: confirmError,
      name: nameError
    }
    setFieldErrors(newErrors)

    if (emailError) {
      window.alert('The email id is invalid.')
      setError('Enter a valid email address before requesting OTP.')
      return
    }

    if (nameError) {
      window.alert(nameError)
      setError(nameError)
      return
    }

    if (passwordError || confirmError) {
      const errorMessage = passwordError || confirmError || 'Fix your password before requesting OTP.'
      window.alert(errorMessage)
      setError(errorMessage)
      return
    }

    setIsSendingOtp(true)
    setError('')
    setOtpStatus('')
    try {
      if (!isCreate) {
        const emailCheck = await api.post('/auth/check-email', { email })
        if (!emailCheck.ok || !emailCheck.exists) {
          window.alert('Email not found. Please register with this email first.')
          setError('Email not found. Please register with this email first.')
          return
        }
      }
      if (isCreate) {
        const emailCheck = await api.post('/auth/check-email', { email })
        if (emailCheck.ok && emailCheck.exists) {
          window.alert('An account already exists for this email. Please login instead.')
          setError('An account already exists for this email. Please login instead.')
          return
        }
      }
      const res = await api.post('/auth/send-otp', { email })
      if (!res.ok) {
        window.alert(res.error || 'Could not send OTP.')
        setError(res.error || 'Could not send OTP.')
        return
      }
      setOtpRequested(true)
      setOtpStatus(res.dev_otp ? `${res.message} Development OTP: ${res.dev_otp}` : res.message)
    } catch {
      window.alert('Could not contact the OTP service.')
      setError('Could not contact the OTP service.')
    } finally {
      setIsSendingOtp(false)
    }
  }

  const submit = async (e) => {
    e.preventDefault()
    const email = form.email.trim().toLowerCase()
    const password = form.password
    const confirmPassword = form.confirmPassword
    const otp = form.otp.trim()
    const captchaAnswer = form.captcha.trim()

    const emailError = validateEmail(email)
    const passwordError = validatePassword(password)
    const confirmError = isCreate ? validateConfirmPassword(confirmPassword) : ''
    const nameError = isCreate ? validateName(form.name) : ''
    const otpError = validateOtp(otp)
    const captchaError = validateCaptcha(captchaAnswer)

    const newErrors = {
      email: emailError,
      password: passwordError,
      confirmPassword: confirmError,
      name: nameError,
      otp: otpRequested ? otpError : '',
      captcha: otpRequested ? captchaError : ''
    }
    setFieldErrors(newErrors)

    if (emailError || passwordError || confirmError || nameError || otpError || captchaError) {
      window.alert('Please correct the highlighted fields before continuing.')
      setError('Please correct the highlighted fields before continuing.')
      return
    }

    if (!otpRequested) {
      window.alert('Request OTP first, then confirm it with the captcha.')
      setError('Request your OTP first, then confirm it with the captcha.')
      return
    }

    setIsSubmitting(true)
    setError('')
    try {
      const endpoint = isCreate ? '/auth/register' : '/auth/login'
      const payload = {
        email,
        password,
        otp,
        captcha_token: captcha.token,
        captcha_answer: captchaAnswer
      }
      if (isCreate) payload.name = form.name.trim()

      const res = await api.post(endpoint, payload)
      if (!res.ok) {
        window.alert(res.error || 'Verification failed.')
        setError(res.error || 'Verification failed.')
        await loadCaptcha()
        return
      }
      if (isCreate) {
        const user = { name: res.user?.name || form.name.trim(), email, role: res.user?.role || 'candidate', token: res.token }
        localStorage.setItem('mockRecruitmentUser', JSON.stringify(user))
        onAuth(user)
        return
      }
      const user = { name: res.user?.name || res.name || email.split('@')[0], email, role: res.user?.role || 'candidate', token: res.token }
      localStorage.setItem('mockRecruitmentUser', JSON.stringify(user))
      onAuth(user)
    } catch {
      window.alert('Could not verify credentials.')
      setError('Could not verify credentials.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="auth-screen">
      {/* Ambient orbs */}
      <div className="orb orb-1" aria-hidden="true" />
      <div className="orb orb-2" aria-hidden="true" />

      <section className="auth-visual">
        <div className="auth-visual-grid" aria-hidden="true" />
        <div className="welcome-message">
          <div className="brand-badge">AI-Powered Mock  Recruitment Platform</div>
          <h1>AI Interview Coach</h1>
          <p>Sign in with your email, request an OTP, and verify with captcha to access the interview simulator.</p>
        </div>
        <div className="feature-list" aria-hidden="true">
          <div className="feature-card">
            <span>🔐 Secure access</span>
            <p>Email + OTP + captcha verification keeps your session protected end-to-end.</p>
          </div>
          <div className="feature-card">
            <span>🎯 Practice workflow</span>
            <p>Upload a resume, choose a target company or the role based on your profile, and simulate real interview rounds.</p>
          </div>
          <div className="feature-card">
            <span>⚡ Instant feedback</span>
            <p>Get AI-driven performance analytics and readiness scores after every round.</p>
          </div>
        </div>
      </section>

      <section className="auth-panel">
        <div className="panel-header">
          <div>
            <p className="eyebrow">Candidate access</p>
            <h2>{isCreate ? 'Create your account' : 'Welcome back'}</h2>
            <p className="muted">Sign in first, then upload a resume and choose the company interview to practice.</p>
          </div>
        </div>

        <form className="auth-form" onSubmit={submit}>
          <div className="form-section">
            <div className="section-title">Account details</div>
            <label>
              Email
              <input
                className={`input ${fieldErrors.email ? 'invalid' : ''}`}
                type="email"
                value={form.email}
                onChange={(e) => updateField('email', e.target.value)}
                placeholder="you@example.com"
              />
              {fieldErrors.email ? <div className="field-error">{fieldErrors.email}</div> : null}
            </label>
            {showCredentials ? (
              <>
                {isCreate && (
                  <label>
                    Full name
                    <input
                      className={`input ${fieldErrors.name ? 'invalid' : ''}`}
                      value={form.name}
                      onChange={(e) => updateField('name', e.target.value)}
                      placeholder="Jane Doe"
                    />
                    {fieldErrors.name ? <div className="field-error">{fieldErrors.name}</div> : null}
                  </label>
                )}
                <label>
                  {isCreate ? 'Create password' : 'Password'}
                  <div className="password-field-wrapper">
                    <input
                      className={`input ${fieldErrors.password ? 'invalid' : ''}`}
                      type={showPassword ? 'text' : 'password'}
                      value={form.password}
                      onChange={(e) => updateField('password', e.target.value)}
                      placeholder="At least 8 characters and a special character"
                    />
                    <button
                      className="eye-toggle"
                      type="button"
                      onClick={() => setShowPassword((current) => !current)}
                      aria-label={showPassword ? 'Hide password' : 'Show password'}
                    >
                      {showPassword ? '👁️' : '👁'}
                    </button>
                  </div>
                  {fieldErrors.password ? <div className="field-error">{fieldErrors.password}</div> : null}
                </label>
                {isCreate && (
                  <label>
                    Confirm password
                    <div className="password-field-wrapper">
                      <input
                        className={`input ${fieldErrors.confirmPassword ? 'invalid' : ''}`}
                        type={showConfirmPassword ? 'text' : 'password'}
                        value={form.confirmPassword}
                        onChange={(e) => updateField('confirmPassword', e.target.value)}
                        placeholder="Repeat your password"
                      />
                      <button
                        className="eye-toggle"
                        type="button"
                        onClick={() => setShowConfirmPassword((current) => !current)}
                        aria-label={showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'}
                      >
                        {showConfirmPassword ? '👁️' : '👁'}
                      </button>
                    </div>
                    {fieldErrors.confirmPassword ? <div className="field-error">{fieldErrors.confirmPassword}</div> : null}
                  </label>
                )}
                {!canRequestOtp && !otpRequested ? (
                  <div className="notice info">
                    {isCreate
                      ? passwordValidationMessage || confirmValidationMessage || 'Fill the password fields correctly to send OTP.'
                      : passwordValidationMessage || 'Enter your password correctly to send OTP.'}
                  </div>
                ) : null}
              </>
            ) : (
              <div className="notice info">Enter a valid email to continue with account creation or login.</div>
            )}
          </div>

          {(canRequestOtp || otpRequested) && (
            <div className="form-section">
              <div className="section-title">Secure access</div>
              <label>
                One-time code
                <button className="btn ghost" type="button" disabled={isSendingOtp || !canRequestOtp} onClick={sendOtp}>
                  {isSendingOtp ? 'Sending…' : otpRequested ? 'Resend OTP' : 'Send OTP'}
                </button>
                <input
                  className={`input ${fieldErrors.otp ? 'invalid' : ''}`}
                  inputMode="numeric"
                  value={form.otp}
                  onChange={(e) => updateField('otp', e.target.value)}
                  placeholder="Enter OTP"
                  disabled={!otpRequested}
                />
                {fieldErrors.otp ? <div className="field-error">{fieldErrors.otp}</div> : null}
              </label>
              {otpStatus ? <div className="secure-note">{otpStatus}</div> : null}
              <label>
                Captcha verification
                <div className="captcha-box">
                  <div className="captcha-question">{captcha.question || 'Loading captcha...'}</div>
                  <button className="btn ghost" type="button" onClick={loadCaptcha}>Refresh</button>
                </div>
                <input
                  className={`input ${fieldErrors.captcha ? 'invalid' : ''}`}
                  inputMode="numeric"
                  value={form.captcha}
                  onChange={(e) => updateField('captcha', e.target.value)}
                  placeholder="Answer the captcha"
                  disabled={!otpRequested}
                />
                {fieldErrors.captcha ? <div className="field-error">{fieldErrors.captcha}</div> : null}
              </label>
            </div>
          )}

          {error ? <div className="notice danger">{error}</div> : null}
          <button className="btn primary" type="submit" disabled={isSubmitting}>
            {isSubmitting ? 'Verifying…' : isCreate ? 'Create account' : 'Login'}
          </button>
        </form>

        <button
          className="link-button"
          type="button"
          onClick={() => {
            setError('')
            setFieldErrors({})
            setOtpStatus('')
            setOtpRequested(false)
            setForm({ name: '', email: '', password: '', confirmPassword: '', otp: '', captcha: '' })
            loadCaptcha()
            setMode(isCreate ? 'login' : 'create')
          }}
        >
          {isCreate ? 'Already have an account? Login' : 'New user? Create account'}
        </button>
      </section>
    </div>
  )
}

function Shell({ state, user, onLogout, proctoring, children }) {
  const navigate = useNavigate()
  const location = useLocation()
  const routeStage = location.pathname.split('/')[1] || 'resume'
  const isRecruiter = user?.role === 'recruiter' || user?.role === 'admin'
  const isDashboard = routeStage === 'dashboard'
  const isRecruiterPage = routeStage === 'recruiter'

  const currentStageIndex = steps.findIndex(s => s.key === state.stage)
  const isStepLocked = (stepKey) => {
    if (state.stage === 'report') return stepKey !== 'report' && stepKey !== 'company'
    const idx = steps.findIndex(s => s.key === stepKey)
    return idx !== currentStageIndex
  }

  return (
    <div className="app-shell">
      {/* Ambient decorative orbs */}
      <div className="orb orb-1" aria-hidden="true" />
      <div className="orb orb-2" aria-hidden="true" />
      <div className="orb orb-3" aria-hidden="true" />

      <aside className="sidebar">
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
          {/* Dashboard Link */}
          <button
            type="button"
            onClick={() => navigate('/dashboard')}
            className={`step-item ${isDashboard ? 'active' : ''}`}
          >
            <span><LayoutDashboard size={15} /></span>
            <b>Dashboard</b>
          </button>

          {/* Recruiter Link (only for recruiter/admin) */}
          {isRecruiter && (
            <button
              type="button"
              onClick={() => navigate('/recruiter')}
              className={`step-item ${isRecruiterPage ? 'active' : ''}`}
            >
              <span><Shield size={15} /></span>
              <b>Recruiter Portal</b>
            </button>
          )}

          {/* Divider */}
          <div style={{ height: 1, background: 'rgba(255,255,255,0.06)', margin: '0.5rem 0' }} />

          {steps.map((step) => {
            const locked = isStepLocked(step.key)
            const active = routeStage === step.key || state.stage === step.key
            const stepIndex = steps.findIndex(s => s.key === step.key)
            const isCompleted = stepIndex < currentStageIndex
            return (
              <button
                key={step.key}
                type="button"
                disabled={locked}
                onClick={() => navigate(`/${step.key}`)}
                className={`step-item ${active ? 'active' : ''} ${locked && !isCompleted ? 'locked' : ''} ${isCompleted ? 'completed' : ''}`}
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
            )
          })}
        </nav>

        <div className="sidebar-footer">
          <div className="tiny muted">Company</div>
          <div className="session-value">{state.company || 'Not selected'}</div>
          <button className="btn ghost full" type="button" onClick={onLogout}>Sign out</button>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
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

function Home() {
  return <Navigate to="/dashboard" replace />
}

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

const ROLE_MAPPINGS = {
  'Frontend Developer': {
    keywords: ['react', 'vue', 'angular', 'html', 'css', 'javascript', 'tailwind', 'bootstrap', 'next', 'frontend'],
    difficulty: 'medium',
    techStack: ['React', 'TypeScript', 'CSS', 'Webpack', 'REST APIs']
  },
  'Backend Developer': {
    keywords: ['node', 'express', 'python', 'django', 'java', 'spring', 'sql', 'mongodb', 'backend', 'api'],
    difficulty: 'medium',
    techStack: ['Node.js', 'SQL', 'REST APIs', 'Docker', 'Redis']
  },
  'Full Stack Developer': {
    keywords: ['react', 'node', 'mongodb', 'express', 'javascript', 'python', 'django', 'full stack'],
    difficulty: 'hard',
    techStack: ['React', 'Node.js', 'MongoDB', 'Express', 'GraphQL']
  },
  'Machine Learning Engineer': {
    keywords: ['python', 'tensorflow', 'pytorch', 'scikit', 'ml', 'data science', 'keras', 'machine learning'],
    difficulty: 'hard',
    techStack: ['Python', 'TensorFlow', 'PyTorch', 'Pandas', 'scikit-learn']
  },
  'Data Analyst': {
    keywords: ['sql', 'excel', 'power bi', 'tableau', 'python', 'r', 'data analysis', 'pandas'],
    difficulty: 'easy',
    techStack: ['SQL', 'Power BI', 'Tableau', 'Python', 'Excel']
  },
  'DevOps Engineer': {
    keywords: ['docker', 'kubernetes', 'aws', 'ci/cd', 'jenkins', 'linux', 'cloud', 'devops'],
    difficulty: 'hard',
    techStack: ['Docker', 'Kubernetes', 'AWS', 'Terraform', 'Jenkins']
  },
  'AI Engineer': {
    keywords: ['llm', 'openai', 'langchain', 'nlp', 'transformers', 'huggingface', 'ai', 'prompt'],
    difficulty: 'hard',
    techStack: ['LangChain', 'OpenAI API', 'HuggingFace', 'Python', 'Vector DBs']
  },
  'Cloud Engineer': {
    keywords: ['aws', 'azure', 'gcp', 'cloud', 'lambda', 's3', 'terraform', 'serverless'],
    difficulty: 'medium',
    techStack: ['AWS', 'Terraform', 'Kubernetes', 'Azure', 'GCP']
  }
}

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

function getNextStage(type) {
  if (type === 'aptitude') return 'coding'
  if (type === 'coding') return 'technical'
  if (type === 'technical') return 'hr'
  return 'report'
}

function RoundPage({ title, items, type, state, setState, proctoring, setProctoring }) {
  const navigate = useNavigate()
  const [idx, setIdx] = useState(0)
  const [answer, setAnswer] = useState('')
  const [selectedMCQ, setSelectedMCQ] = useState('')
  const [timeLeft, setTimeLeft] = useState(roundDurations[type] || 10 * 60)
  const [hasPermissions, setHasPermissions] = useState(false)
  const [isStarted, setIsStarted] = useState(false)
  const [proctorError, setProctorError] = useState('')
  const [userStream, setUserStream] = useState(null)
  const [screenStream, setScreenStream] = useState(null)
  const [selectedLanguage, setSelectedLanguage] = useState('javascript')
  const [code, setCode] = useState('')
  const [runOutput, setRunOutput] = useState('')
  const [testResults, setTestResults] = useState([])
  const [runStatus, setRunStatus] = useState('')
  const [isRunning, setIsRunning] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [audioBlob, setAudioBlob] = useState(null)
  const [recordingTime, setRecordingTime] = useState(0)
  const videoRef = useRef(null)
  const screenRef = useRef(null)
  const audioRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const submittingRef = useRef(false)
  const submitRef = useRef(null)
  const proctor = useAssessmentProctoring({
    active: isStarted,
    round: type,
    sessionId: state.sessionId,
    navigate,
    setState,
    proctoring,
    setProctoring,
    webcamVideoRef: videoRef,
    webcamStream: userStream,
    screenStream
  })

  const current = items[idx]
  const duration = roundDurations[type] || 10 * 60
  const timerPercent = Math.max(0, Math.min(100, (timeLeft / duration) * 100))
  const isTimerCritical = timeLeft <= 60
  const isTimerWarning = timeLeft <= 180 && timeLeft > 60
  const timerClass = isTimerCritical ? 'timer-critical' : isTimerWarning ? 'timer-warning' : 'timer-normal'
  const languages = ['javascript', 'python', 'java', 'c', 'csharp']
  const languageLabels = { javascript: 'JavaScript', python: 'Python', java: 'Java', c: 'C', csharp: 'C#' }
  const sections = useMemo(() => Array.from(new Set(items.map(i => i.section).filter(Boolean))), [items])

  useEffect(() => {
    setTimeLeft(duration)
    submittingRef.current = false
  }, [duration, idx])

  useEffect(() => {
    if (type === 'coding' && current?.starter) {
      setSelectedLanguage('javascript')
      setCode(current.starter.javascript || '')
    } else {
      setAnswer('')
      setSelectedMCQ('')
      setAudioBlob(null)
      setRecordingTime(0)
    }
  }, [current, type])

  useEffect(() => {
    if (!isRecording) return
    const timer = setInterval(() => {
      setRecordingTime((t) => t + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [isRecording])

  useEffect(() => {
    if (!isStarted || !current || !state.sessionId || !state.company) return undefined
    const timer = window.setInterval(() => {
      setTimeLeft((remaining) => Math.max(remaining - 1, 0))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [isStarted, current, state.company, state.sessionId])

  useEffect(() => {
    if (timeLeft !== 0 || !current || !state.sessionId || !state.company) return
    submitRef.current?.(true)
  }, [timeLeft, current, state.company, state.sessionId])

  useEffect(() => {
    if (hasPermissions || isStarted) {
      if (videoRef.current && userStream) videoRef.current.srcObject = userStream
      if (screenRef.current && screenStream) screenRef.current.srcObject = screenStream
    }
  }, [hasPermissions, isStarted, userStream, screenStream])

  useEffect(() => {
    return () => {
      if (userStream) userStream.getTracks().forEach((t) => t.stop())
      if (screenStream) screenStream.getTracks().forEach((t) => t.stop())
    }
  }, [userStream, screenStream])

  useEffect(() => {

    document.documentElement
      .requestFullscreen()
      .catch(() => { })

  }, [])

  const startProctoring = async () => {
    try {
      setProctorError('')
      const uMedia = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
      const dMedia = await navigator.mediaDevices.getDisplayMedia({ video: true })

      setUserStream(uMedia)
      setScreenStream(dMedia)
      setHasPermissions(true)
    } catch (err) {
      if (err && err.name === 'NotAllowedError') {
        setProctorError('Permission denied. Please allow webcam, microphone, and screen sharing.')
      } else {
        setProctorError('Failed to access webcam, microphone, or screen share. These are required for the fully AI proctored test.')
      }
      if (userStream) userStream.getTracks().forEach((t) => t.stop())
      if (screenStream) screenStream.getTracks().forEach((t) => t.stop())
      setUserStream(null)
      setScreenStream(null)
      setHasPermissions(false)
    }
  }

  const beginTest = async () => {
    await proctor.requestFullscreen()
    await api.post('/start-round', { session_id: state.sessionId, company: state.company, round_key: type })
    setTimeLeft(duration)
    setIsStarted(true)
    setRunStatus('')
    setTestResults([])
  }

  const startRecording = async () => {
    try {
      if (!userStream) return
      const audioStream = userStream.getAudioTracks()[0]
      if (!audioStream) return
      const mediaStream = new MediaStream([audioStream])
      mediaRecorderRef.current = new MediaRecorder(mediaStream)
      const chunks = []
      mediaRecorderRef.current.ondataavailable = (e) => chunks.push(e.data)
      mediaRecorderRef.current.onstop = () => {
        const blob = new Blob(chunks, { type: 'audio/webm' })
        setAudioBlob(blob)
      }
      mediaRecorderRef.current.start()
      setIsRecording(true)
      setRecordingTime(0)
    } catch (err) {
      console.error('Recording failed:', err)
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop()
      setIsRecording(false)
    }
  }

  const reRecord = () => {
    setAudioBlob(null)
    setRecordingTime(0)
    startRecording()
  }

  const formatRecordingTime = (seconds) => {
    const mins = Math.floor(seconds / 60).toString().padStart(2, '0')
    const secs = (seconds % 60).toString().padStart(2, '0')
    return `${mins}:${secs}`
  }

  const handleRun = async () => {
    if (!current) return
    setIsRunning(true)
    setRunStatus('Running code...')
    setRunOutput('')
    setTestResults([])
    try {
      const res = await api.post('/run-code', {
        question_id: current.id,
        language: selectedLanguage,
        code,
      })
      if (!res.ok) {
        setRunStatus(res.error || 'Could not run code.')
      } else {
        setRunStatus(`${res.passed}/${res.total} tests passed`)
        setRunOutput(res.console || 'Compiled successfully.')
        setTestResults(res.results || [])
      }
    } catch {
      setRunStatus('Could not contact run service.')
    } finally {
      setIsRunning(false)
    }
  }

  const submit = async (expired = false, skipped = false) => {
    if (!current || submittingRef.current) return
    submittingRef.current = true

    if (type === 'aptitude') {
      await api.post('/submit-answer', {
        session_id: state.sessionId,
        round_key: 'aptitude',
        question_index: idx,
        answer: skipped ? '[Skipped]' : (selectedMCQ || '[No answer]'),
      })
    } else if (type === 'coding') {
      await api.post('/submit-code', {
        session_id: state.sessionId,
        round_key: 'coding',
        question_index: idx,
        language: selectedLanguage,
        code: skipped ? '[Skipped]' : code,
      })
    } else if (type === 'technical' || type === 'hr') {
      const audioData = await audioBlobToDataUrl(audioBlob)
      await api.post('/submit-answer', {
        session_id: state.sessionId,
        round_key: type,
        question_index: idx,
        answer: audioBlob
          ? JSON.stringify({ type: 'voice', transcript: answer.trim(), audio: audioData })
          : (expired && !answer.trim() ? '[Time expired]' : answer),
      })
    }

    submittingRef.current = false
    if (idx < items.length - 1) {
      setIdx(idx + 1)
    } else {
      const nextStage = getNextStage(type)
      if (nextStage !== 'report') {
        setState((s) => ({ ...s, stage: nextStage, roundTransition: true }))
        navigate(`/${nextStage}`)
      } else {
        setState((s) => ({ ...s, stage: 'report' }))
        navigate('/report')
      }
    }
  }

  submitRef.current = submit

  if (!state.sessionId) return <Navigate to="/resume" replace />
  if (!state.company) return <Navigate to="/company" replace />

  if (!isStarted) {
    return (
      <section className="panel main-panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">{state.company} simulation</p>
            <h2>{title} - Proctored</h2>
            <p className="muted">Grant webcam, microphone, and screen-share permissions. After that, click Begin Test to start the timer.</p>
          </div>
        </div>
        {proctorError ? <div className="notice danger">{proctorError}</div> : null}
        <div className="empty-state" style={{ minHeight: 'auto', padding: '40px 0' }}>
          {!hasPermissions ? (
            <button className="btn primary" type="button" onClick={startProctoring}>Grant Permissions</button>
          ) : (
            <>
              <div className="permission-preview">
                <div className="permission-box">
                  <p>Webcam preview</p>
                  <video ref={videoRef} autoPlay muted playsInline style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                </div>
                <div className="permission-box">
                  <p>Screen share preview</p>
                  <video ref={screenRef} autoPlay muted playsInline style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                </div>
              </div>
              <button className="btn primary" type="button" onClick={beginTest}>Begin Test</button>
            </>
          )}
        </div>
      </section>
    )
  }

  return (
    <section className="panel main-panel test-room">
      <ProctoringModal modal={proctor.modal} onClose={proctor.dismissModal} />
      <div className="test-topbar">
        <div className="topbar-block">
          <span>Questions</span>
          <strong>{idx + 1} / {items.length}</strong>
        </div>
        <div className={`topbar-block topbar-center ${timerClass}`}>
          <span>Timer</span>
          <strong>{formatTime(timeLeft)}</strong>
        </div>
        <div className="topbar-block topbar-right">
          <span>Video</span>
          <div className="topbar-video">
            <span className="live-dot" />
            <span>Live</span>
          </div>
        </div>
      </div>

      <div className={`timer-track ${timerClass}`} aria-hidden="true">
        <span style={{ width: `${timerPercent}%` }} />
      </div>

      {userStream && (
        <div className="video-preview-topright">
          <video ref={videoRef} autoPlay muted playsInline style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          <span className="live-indicator">● Live</span>
        </div>
      )}

      {current ? (
        <div className={type === 'coding' ? 'question-layout coding-layout' : 'question-layout'}>
          {type === 'aptitude' && sections.length > 0 && (
            <div className="language-tabs" style={{ marginBottom: '1rem', justifyContent: 'flex-start', borderBottom: '1px solid var(--border)' }}>
              {sections.map(sec => {
                const isActive = current.section === sec
                return (
                  <button key={sec} type="button" className={isActive ? 'active' : ''} disabled={!isActive} style={{ cursor: isActive ? 'default' : 'not-allowed', opacity: isActive ? 1 : 0.6 }}>
                    {sec}
                  </button>
                )
              })}
            </div>
          )}
          <div className="question-card">
            <span>Question</span>
            <p><FormattedText text={current.question || current.statement} /></p>
            {current.image && !isFormulaImage(current.image) ? (
              <div className="question-image">
                <QuestionImage src={current.image} alt="Question diagram" />
              </div>
            ) : null}
            {current.images?.length ? (
              <div className="question-images">
                {current.images.filter((src) => !isFormulaImage(src)).map((src, i) => (
                  <QuestionImage key={i} src={src} alt={`Question diagram ${i + 1}`} />
                ))}
              </div>
            ) : null}
            {current.examples ? (
              <div className="question-examples">
                <strong>Examples</strong>
                <ul>
                  {current.examples.map((item, index) => <li key={index}>{item}</li>)}
                </ul>
              </div>
            ) : null}
          </div>

          {type === 'aptitude' ? (
            <div className="mcq-panel">
              <div className="mcq-options">
                {current.options?.map((option, idx) => (
                  <label key={idx} className={`mcq-option ${selectedMCQ === option ? 'selected' : ''}`}>
                    <input
                      type="radio"
                      name={`question-${current.id}`}
                      value={option}
                      checked={selectedMCQ === option}
                      onChange={(e) => setSelectedMCQ(e.target.value)}
                    />
                    <span className="radio-circle"></span>
                    <span className="option-text"><FormattedText text={option} /></span>
                  </label>
                ))}
              </div>
              <div className="action-row">
                <button className="btn primary" type="button" onClick={() => submit(false)} disabled={!selectedMCQ}>Submit answer</button>
                <button className="btn ghost" type="button" onClick={() => setIdx((i) => Math.min(i + 1, items.length - 1))}>Skip</button>
              </div>
            </div>
          ) : type === 'coding' ? (
            <div className="coding-panel">
              <div className="language-tabs">
                {languages.map((lang) => (
                  <button key={lang} type="button" className={selectedLanguage === lang ? 'active' : ''} onClick={() => {
                    setSelectedLanguage(lang)
                    setCode(current.starter?.[lang] || '')
                  }}>
                    {languageLabels[lang]}
                  </button>
                ))}
              </div>
              <div className="editor-container">
                <div className="editor-main">
                  <CodeEditor
                    value={code}
                    onChange={setCode}
                    language={languageLabels[selectedLanguage]}
                    starter={current.starter?.[selectedLanguage]}
                    questionTitle={current.title || 'Solution'}
                  />
                </div>
              </div>
              <div className="coding-actions">
                <button className="btn primary" type="button" onClick={handleRun} disabled={isRunning}>
                  {isRunning ? 'Running…' : 'Run Code'}
                </button>
                <button className="btn ghost" type="button" onClick={() => submit(false, true)}>
                  Skip
                </button>
                <button className="btn primary" type="button" onClick={() => submit(false)} disabled={!code.trim()}>
                  Save & Next
                </button>
              </div>
              <div className="code-feedback-grid">
                <div className="output-box">
                  <div className="output-title">Console Output</div>
                  <pre>{runOutput || 'Run code to see output.'}</pre>
                </div>
                <div className="testcase-box">
                  <div className="output-title">Test Cases</div>
                  {testResults.length ? (
                    <div className="test-results">
                      {testResults.map((test, index) => (
                        <div key={index} className={`test-row ${test.status}`}>
                          <span>{test.input}</span>
                          <strong>{test.status.toUpperCase()}</strong>
                          <small>Expected: {test.expected}</small>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="muted">Run the code to validate testcases and see results here.</p>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <div className="speech-panel">
              <div className="speech-recorder">
                {!audioBlob ? (
                  <>
                    <div className="recording-info">
                      {isRecording ? (
                        <>
                          <div className="recording-indicator">
                            <span className="recording-dot"></span>
                            Recording...
                          </div>
                          <div className="recording-time">{formatRecordingTime(recordingTime)}</div>
                        </>
                      ) : (
                        <p className="instruction-text">Record your answer by clicking the microphone button below.</p>
                      )}
                    </div>
                    <div className="speech-controls">
                      {!isRecording ? (
                        <button className="btn primary record-btn" type="button" onClick={startRecording}>
                          🎤 Start Recording
                        </button>
                      ) : (
                        <button className="btn danger record-btn" type="button" onClick={stopRecording}>
                          ⏹️ Stop Recording
                        </button>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="recording-info">
                      <p className="success-text">✓ Recording saved ({formatRecordingTime(recordingTime)})</p>
                    </div>
                    <div className="playback-controls">
                      <button className="btn ghost" type="button" onClick={() => audioRef.current?.play()}>
                        ▶️ Play
                      </button>
                      <button className="btn ghost" type="button" onClick={reRecord}>
                        🔄 Re-record
                      </button>
                    </div>
                    <audio ref={audioRef} src={audioUrl || ''} style={{ marginTop: '16px', width: '100%' }} />
                  </>
                )}
              </div>
              <div className="text-alternative">
                <div className="divider">OR</div>
                <textarea
                  className="input answer-box"
                  value={answer}
                  onChange={(e) => setAnswer(e.target.value)}
                  placeholder="Type your answer instead"
                />
              </div>
              <div className="action-row">
                <button className="btn primary" type="button" onClick={() => submit(false)} disabled={!audioBlob && !answer.trim()}>
                  {idx < items.length - 1 ? 'Save & Next' : 'Submit'}
                </button>
                <button className="btn ghost" type="button" onClick={() => setIdx((i) => Math.min(i + 1, items.length - 1))}>Skip</button>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="empty-state"><b>No questions available</b><p>This round has no dataset yet.</p></div>
      )}
    </section>
  )
}

function ChatInterview({ title, questions, state, setState, proctoring, setProctoring }) {
  const navigate = useNavigate()
  const { muted, setMuted, speak } = useSpeech()
  const [idx, setIdx] = useState(0)
  const [text, setText] = useState('')
  const [audioBlob, setAudioBlob] = useState(null)
  const [audioUrl, setAudioUrl] = useState(null)
  const [messages, setMessages] = useState([])
  const [timeLeft, setTimeLeft] = useState(interviewQuestionDuration)
  const scroller = useRef(null)

  const [hasPermissions, setHasPermissions] = useState(false)
  const [isStarted, setIsStarted] = useState(false)
  const [proctorError, setProctorError] = useState('')
  const [userStream, setUserStream] = useState(null)
  const [screenStream, setScreenStream] = useState(null)
  const videoRef = useRef(null)
  const screenRef = useRef(null)
  const submittingRef = useRef(false)
  const sendRef = useRef(null)
  const questionStartedAtRef = useRef(Date.now())
  
  useEffect(() => {
    if (!audioBlob) { setAudioUrl(null); return }
    const url = URL.createObjectURL(audioBlob)
    setAudioUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [audioBlob])

  const [aiQuestions, setAiQuestions] = useState(null)
  const activeQuestions = aiQuestions || questions

  const timerPercent = Math.max(0, Math.min(100, (timeLeft / interviewQuestionDuration) * 100))
  const isTimerCritical = timeLeft <= 30
  const isTimerWarning = timeLeft <= 60 && timeLeft > 30
  const timerClass = isTimerCritical ? 'timer-critical' : isTimerWarning ? 'timer-normal' : ''
  const roleKey = title.toLowerCase().includes('hr') ? 'hr' : 'technical'
  const proctor = useAssessmentProctoring({
    active: isStarted,
    round: roleKey,
    sessionId: state.sessionId,
    navigate,
    setState,
    proctoring,
    setProctoring,
    webcamVideoRef: videoRef,
    webcamStream: userStream,
    screenStream
  })

  useEffect(() => {
    if (!state.sessionId) return
    let isMounted = true
    const fetchAiQuestions = async () => {
      try {
        const res = await api.post('/ai/questions', {
          session_id: state.sessionId,
          round_type: roleKey,
          count: 5
        })
        if (isMounted && res.questions) {
          setAiQuestions(res.questions)
        }
      } catch (err) {
        console.error("AI questions failed, using fallback")
      }
    }
    fetchAiQuestions()
    return () => { isMounted = false }
  }, [state.sessionId, roleKey])

  useEffect(() => {
    if (!isStarted) return
    const q = activeQuestions[idx]
    if (!q) return
    setTimeLeft(interviewQuestionDuration)
    submittingRef.current = false
    questionStartedAtRef.current = Date.now()
    const questionText = formatQuestionText(q.question)
    setMessages((m) => [...m, { role: 'interviewer', text: questionText }])
    speak(questionText)
  }, [idx, isStarted])

  useEffect(() => {
    if (!isStarted || !activeQuestions[idx]) return undefined
    const timer = window.setInterval(() => {
      setTimeLeft((remaining) => Math.max(remaining - 1, 0))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [idx, isStarted, activeQuestions])

  useEffect(() => {
    if (!isStarted || timeLeft !== 0 || !activeQuestions[idx]) return
    sendRef.current?.(true)
  }, [timeLeft, isStarted, idx, activeQuestions])

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (hasPermissions || isStarted) {
      if (videoRef.current && userStream) videoRef.current.srcObject = userStream
      if (screenRef.current && screenStream) screenRef.current.srcObject = screenStream
    }
  }, [hasPermissions, isStarted, userStream, screenStream])

  useEffect(() => {
    return () => {
      if (userStream) userStream.getTracks().forEach(t => t.stop())
      if (screenStream) screenStream.getTracks().forEach(t => t.stop())
    }
  }, [userStream, screenStream])

  useEffect(() => {

    document.documentElement
      .requestFullscreen()
      .catch(() => { })

  }, [])

  const startProctoring = async () => {
    try {
      setProctorError('')
      const uMedia = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
      const dMedia = await navigator.mediaDevices.getDisplayMedia({ video: true })
      setUserStream(uMedia)
      setScreenStream(dMedia)
      setHasPermissions(true)
    } catch (err) {
      if (err && err.name === 'NotAllowedError') {
        setProctorError('Permission denied. Please allow webcam, microphone, and screen sharing.')
      } else {
        setProctorError('Failed to access webcam, microphone, or screen share. These are required for the fully AI proctored interview.')
      }
      if (userStream) userStream.getTracks().forEach(t => t.stop())
      if (screenStream) screenStream.getTracks().forEach(t => t.stop())
      setUserStream(null)
      setScreenStream(null)
      setHasPermissions(false)
    }
  }

  const beginInterview = async () => {
    await proctor.requestFullscreen()
    await api.post('/start-round', { session_id: state.sessionId, company: state.company, round_key: roleKey })
    setIsStarted(true)
  }

  if (!state.sessionId) return <Navigate to="/resume" replace />
  if (!state.company) return <Navigate to="/company" replace />

  if (!isStarted) {
    return (
      <section className="panel main-panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">{state.company} live room</p>
            <h2>{title} - Proctored</h2>
            <p className="muted">You must grant webcam, microphone, and screen sharing permissions before the interview can begin. Once permissions are granted, click Begin Interview.</p>
          </div>
        </div>
        {proctorError ? <div className="notice danger">{proctorError}</div> : null}
        <div className="empty-state" style={{ minHeight: 'auto', padding: '40px 0' }}>
          {!hasPermissions ? (
            <button className="btn primary" type="button" onClick={startProctoring}>Grant Permissions</button>
          ) : (
            <>
              <div className="permission-preview">
                <div className="permission-box">
                  <p>Webcam preview</p>
                  <video ref={videoRef} autoPlay muted playsInline style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                </div>
                <div className="permission-box">
                  <p>Screen share preview</p>
                  <video ref={screenRef} autoPlay muted playsInline style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                </div>
              </div>
              <button className="btn primary" type="button" onClick={beginInterview}>Begin Interview</button>
            </>
          )}
        </div>
      </section>
    )
  }

  const send = async (expired = false) => {
    const q = activeQuestions[idx]
    if (!q || submittingRef.current || (!expired && !text.trim() && !audioBlob)) return
    submittingRef.current = true
    const answerText = expired && !text.trim() && !audioBlob ? '[Time expired]' : (text.trim() || '[Voice recorded]')
    const audioData = await audioBlobToDataUrl(audioBlob)
    const submittedAnswer = audioBlob
      ? JSON.stringify({ type: 'voice', transcript: text.trim(), audio: audioData })
      : answerText
    await api.post('/submit-answer', { session_id: state.sessionId, round_key: roleKey, question_index: idx, answer: submittedAnswer })
    const timeSpent = Math.round((Date.now() - questionStartedAtRef.current) / 1000)
    const voiceDuration = audioBlob ? Math.max(5, Math.min(180, Math.round(audioBlob.size / 16000))) : 0
    setProctoring((currentState) => ({
      ...currentState,
      timeSpent: {
        ...currentState.timeSpent,
        [roleKey]: (currentState.timeSpent?.[roleKey] || 0) + timeSpent
      },
      interviewMetrics: {
        ...currentState.interviewMetrics,
        [roleKey]: {
          questionTimes: [...(currentState.interviewMetrics?.[roleKey]?.questionTimes || []), timeSpent],
          voiceDurations: [...(currentState.interviewMetrics?.[roleKey]?.voiceDurations || []), voiceDuration],
          submissions: [
            ...(currentState.interviewMetrics?.[roleKey]?.submissions || []),
            { questionIndex: idx, submittedAt: new Date().toISOString(), answerLength: answerText.length, hasVoice: Boolean(audioBlob) }
          ]
        }
      }
    }))
    setMessages((m) => [...m, { role: 'candidate', text: answerText }])
    setText('')
    setAudioBlob(null)
    submittingRef.current = false
    if (idx < activeQuestions.length - 1) {
      setIdx(idx + 1)
      setTimeLeft(180)
      setMessages([])
    } else {
      const nextStage = title.toLowerCase().includes('hr') ? 'report' : 'hr'
      setState((s) => ({ ...s, stage: nextStage, roundTransition: true }))
      navigate(`/${nextStage}`)
    }
  }

  sendRef.current = send

  const skipQuestion = async () => {
    if (submittingRef.current) return
    submittingRef.current = true
    await api.post('/submit-answer', { session_id: state.sessionId, round_key: roleKey, question_index: idx, answer: '[Skipped]' })
    setMessages((m) => [...m, { role: 'candidate', text: '[Skipped]' }])
    submittingRef.current = false
    if (idx < activeQuestions.length - 1) {
      setIdx(idx + 1)
      setTimeLeft(180)
      setMessages([])
    } else {
      const nextStage = title.toLowerCase().includes('hr') ? 'report' : 'hr'
      setState((s) => ({ ...s, stage: nextStage, roundTransition: true }))
      navigate(`/${nextStage}`)
    }
  }


  const current = activeQuestions[idx]
  return (
    <section className="panel main-panel interview-panel">
      <ProctoringModal modal={proctor.modal} onClose={proctor.dismissModal} />
      <div className="section-head">
        <div>
          <p className="eyebrow">{state.company} live room</p>
          <h2>{title}</h2>
        </div>
        <div className="status-pills">
          <span>{title}</span>
          <span>{activeQuestions.length ? `Question ${idx + 1} of ${activeQuestions.length}` : 'Loading...'}</span>
          <span className={timerClass}>{formatTime(timeLeft)}</span>
        </div>
        <div className="action-row compact">
          <button className="btn ghost" type="button" onClick={() => current && speak(formatQuestionText(current.question))}>Replay</button>
          <button className="btn ghost" type="button" onClick={() => setMuted((m) => !m)}>{muted ? 'Unmute' : 'Mute'}</button>
        </div>
      </div>

      <div className={`timer-track interview-timer-track ${timerClass}`} aria-hidden="true">
        <span style={{ width: `${timerPercent}%` }} />
      </div>

      <div className="video-preview-topright interview-webcam">
        <video ref={videoRef} autoPlay muted playsInline style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        <span className="live-indicator">Live</span>
      </div>

      <div ref={scroller} className="chat-window">
        {messages.map((message, index) => (
          <div key={`${message.role}-${index}`} className={`chat-bubble ${message.role}`}>
            <b>{message.role === 'interviewer' ? 'AI interviewer' : 'Candidate'}</b>
            <p>{message.text}</p>
          </div>
        ))}
      </div>
      <VoiceAnswerControls
        key={`interview-voice-${idx}`}
        userStream={userStream}
        transcript={text}
        onTranscriptChange={setText}
        onAudioChange={setAudioBlob}
      />
      <div className="chat-input">
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Review or type your answer before submitting" />
        <button className="btn ghost" type="button" onClick={skipQuestion} disabled={submittingRef.current}>Skip</button>
        <button className="btn primary" type="button" onClick={() => send(false)} disabled={(!text.trim() && !audioBlob) || submittingRef.current}>Submit answer</button>
      </div>
    </section>
  )
}

// TerminatedPage (full-screen version defined below at line ~2199)

function ReportPage({ state, proctoring }) {
  const [report, setReport] = useState(null)
  const [isGenerating, setIsGenerating] = useState(true)

  useEffect(() => {
    if (!state.sessionId) return
    const fetchReport = async () => {
      setIsGenerating(true)
      try {
        await api.post('/ai/feedback', { session_id: state.sessionId })
      } catch (err) {
        console.error("AI feedback generation failed", err)
      }
      const data = await api.get(`/report?session_id=${state.sessionId}`)
      setReport(data)
      setIsGenerating(false)
    }
    fetchReport()
  }, [state.sessionId])

  const interviewScores = useMemo(() => {
    return calculateInterviewScores(proctoring?.interviewMetrics || {})
  }, [proctoring?.interviewMetrics])

  const downloadPdf = () => {
    if (!report) return
    const doc = new jsPDF()
    doc.setFontSize(20)
    doc.text('Assessment Report', 20, 20)
    doc.setFontSize(12)
    doc.text(`Candidate: ${report.candidateName || 'Unknown'}`, 20, 30)
    doc.text(`Company: ${report.selectedCompany || 'Unknown'}`, 20, 40)
    doc.text(`Overall Score: ${report.overallScore || 0}%`, 20, 50)

    doc.text(`Communication Score: ${interviewScores.communicationScore}%`, 20, 70)
    doc.text(`Confidence Score: ${interviewScores.confidenceScore}%`, 20, 80)
    doc.text(`Participation Score: ${interviewScores.participationScore}%`, 20, 90)

    doc.save('Assessment_Report.pdf')
  }

  if (!state.sessionId) return <Navigate to="/resume" replace />
  if (!state.company) return <Navigate to="/company" replace />

  return (
    <section className="panel main-panel report-panel">
      <div className="section-head">
        <div>
          <p className="eyebrow">Final report</p>
          <h2>Candidate readiness summary</h2>
          <p className="muted">A mock assessment dashboard showing round scores, strengths, remediation, and next steps.</p>
        </div>
        <div className="action-row compact">
          <button className="btn primary" type="button" onClick={downloadPdf}>Download PDF</button>
        </div>
      </div>
      {report ? (
        <>
          <div className="report-grid">
            <div className="report-card summary-card">
              <span>Overall score</span>
              <h3>{report.overallScore}%</h3>
              <p>{report.feedback?.summary}</p>
            </div>
            <div className="report-card breakdown-card">
              <span>Interview Metrics</span>
              <ul>
                <li>
                  <div className="score-row"><strong>Communication</strong><span>{interviewScores.communicationScore}%</span></div>
                  <div className="score-bar"><div className="score-fill" style={{ width: `${interviewScores.communicationScore}%` }} /></div>
                </li>
                <li>
                  <div className="score-row"><strong>Confidence</strong><span>{interviewScores.confidenceScore}%</span></div>
                  <div className="score-bar"><div className="score-fill" style={{ width: `${interviewScores.confidenceScore}%` }} /></div>
                </li>
                <li>
                  <div className="score-row"><strong>Participation</strong><span>{interviewScores.participationScore}%</span></div>
                  <div className="score-bar"><div className="score-fill" style={{ width: `${interviewScores.participationScore}%` }} /></div>
                </li>
              </ul>
            </div>
            <div className="report-card breakdown-card">
              <span>Round breakdown</span>
              <ul>
                {Object.entries(report.breakdown || {}).map(([round, value]) => (
                  <li key={round}>
                    <div className="score-row"><strong>{round}</strong><span>{value}%</span></div>
                    <div className="score-bar"><div className="score-fill" style={{ width: `${value}%` }} /></div>
                  </li>
                ))}
              </ul>
            </div>
            <div className="report-card notes-card">
              <span>Top insights</span>
              <h4>Strengths</h4>
              <ul>
                {(report.strengths || []).map((item, idx) => <li key={idx}>{item}</li>)}
              </ul>
              <h4>Areas to improve</h4>
              <ul>
                {(report.weaknesses || []).map((item, idx) => <li key={idx}>{item}</li>)}
              </ul>
            </div>
          </div>
          <div className="report-details">
            <div className="report-card full-card">
              <span>Recommendations</span>
              <ul>
                {(report.recommendations || []).map((item, idx) => <li key={idx}>{item}</li>)}
              </ul>
            </div>
          </div>
        </>
      ) : (
        <div className="empty-state">
          <b>{isGenerating ? "Generating AI Feedback..." : "Loading report..."}</b>
          <p>{isGenerating ? "Analyzing your interview answers..." : "Your performance summary will appear here shortly."}</p>
        </div>
      )}
    </section>
  )
}

function TerminatedPage() {
  return (
    <div className="termination-screen">
      <div className="termination-card">
        <div className="termination-icon">⚠</div>
        <div className="termination-title">Test Terminated</div>
        <div className="termination-message">
          Your assessment has been terminated due to repeated malpractice detection (tab switching, loss of focus, or exiting fullscreen).
        </div>
        <button className="btn ghost" type="button" onClick={() => window.location.href = '/'}>
          Return to Dashboard
        </button>
      </div>
    </div>
  )
}

function findHighlighted(sentence, options, correct) {
  const words = sentence.split(/\s+/)
  if (!words.length || !correct) return null

  const skip = new Set(['the', 'a', 'an', 'is', 'was', 'were', 'are', 'been', 'being', 'be',
    'in', 'on', 'at', 'to', 'for', 'of', 'by', 'with', 'from', 'as', 'into', 'through',
    'it', 'its', 'they', 'them', 'he', 'she', 'his', 'her', 'their', 'this', 'that',
    'and', 'or', 'but', 'not', 'no', 'so', 'if', 'than', 'then'])

  let bestStart = words.length, bestEnd = 0
  const candidates = [correct, ...options.filter(o => o !== 'No correction required')]
  for (const cand of candidates) {
    const candWords = cand.toLowerCase().split(/\s+/)
    for (const cw of candWords) {
      if (skip.has(cw) || cw.length < 2) continue
      for (let i = 0; i < words.length; i++) {
        const w = words[i].replace(/[^a-zA-Z]/g, '').toLowerCase()
        if (w === cw || (w.length >= 3 && cw.length >= 3 && (w.startsWith(cw) || cw.startsWith(w)))) {
          bestStart = Math.min(bestStart, i)
          bestEnd = Math.max(bestEnd, i + 1)
        }
      }
    }
  }

  if (bestStart >= bestEnd) return null

  const len = bestEnd - bestStart
  if (len > 8) {
    const mid = Math.floor((bestStart + bestEnd) / 2)
    bestStart = Math.max(0, mid - 3)
    bestEnd = Math.min(words.length, mid + 3)
  }

  return { start: bestStart, end: bestEnd }
}

const imageRefPattern = /figure|diagram|graph|chart|shown below|given below|above figure|following figure|picture|illustration|as shown|as given|pictorially|schematically|table|map|graphically|pipeline|pipe[ds]|network|layout/i

function needsImage(q) {
  return imageRefPattern.test(q.question || '') || imageRefPattern.test(q.statement || '')
}

const parenCleanRe = /\(([a-zA-Z0-9]+)\)\/([a-zA-Z0-9]+)/g
const mixedFractionRe = /\(([a-zA-Z0-9]+)\)\s*\(\(([^()]+?)\/([^()]+?)\)\)/g
const spacedFractionRe = /\(\s*([a-zA-Z0-9.]+)\s*\)\s*\/\s*\(\s*([a-zA-Z0-9.]+)\s*\)/g
const supSubFractionRe = /\^\(\s*([a-zA-Z0-9.]+)\s*\)\s*\/\s*_\(\s*([a-zA-Z0-9.]+)\s*\)/g

function cleanParens(str) {
  return (str || '')
    .replace(/\^\(\)/g, '')
    .replace(mixedFractionRe, '$1 $2/$3')
    .replace(spacedFractionRe, '$1/$2')
    .replace(supSubFractionRe, '$1/$2')
    .replace(parenCleanRe, '$1/$2')
    .replace(/\(\s*([a-zA-Z0-9]+)\s*\)/g, '$1')
}

function isFormulaImage(src = '') {
  return /(^|\/)(?:\d+-sym-|sym-|frac|math|formula|equation)/i.test(src) || /fraction|frac/i.test(src)
}

function QuestionImage({ src, alt }) {
  const [decision, setDecision] = useState('pending')

  useEffect(() => {
    if (!src) {
      setDecision('hidden')
      return undefined
    }

    let active = true
    const probe = new window.Image()
    probe.onload = () => {
      if (!active) return
      const area = probe.naturalWidth * probe.naturalHeight
      const narrow = Math.min(probe.naturalWidth, probe.naturalHeight) <= 40
      const tiny = area > 0 && area <= 1600
      setDecision(narrow && tiny ? 'hidden' : 'show')
    }
    probe.onerror = () => {
      if (active) setDecision('hidden')
    }
    probe.src = src

    return () => {
      active = false
    }
  }, [src])

  if (!src || decision !== 'show') return null

  return (
    <img src={src} alt={alt} />
  )
}

function processAptitudeText(questions) {
  return questions.map(q => {
    if (q.options) {
      q.options = q.options.map(opt => formatQuestionText(cleanParens(opt)))
    }
    q.question = formatQuestionText(cleanParens(q.question || ''))
    const text = q.question

    if (text.includes('highlighted')) {
      const lines = text.split('\n')
      const instruction = lines[0]
      const sentence = lines.slice(1).join(' ').trim()
      if (sentence) {
        const hl = findHighlighted(sentence, q.options || [], q.correct || '')
        if (hl) {
          const wordArr = sentence.split(/\s+/)
          const before = wordArr.slice(0, hl.start).join(' ')
          const mid = wordArr.slice(hl.start, hl.end).join(' ')
          const after = wordArr.slice(hl.end).join(' ')
          const sep = before && after ? ' ' : ''
          q.question = instruction + '\n' + before + (before ? ' ' : '') + '«hl»' + mid + '«/hl»' + (after ? ' ' : '') + after
          return q
        }
      }
    }

    const match = text.match(/^(.*?)\n([A-Z][A-Z\s-]{1,})$/)
    if (match) {
      const word = match[2].trim()
      q.question = match[1] + '\n«b»' + word + '«/b»'
    }

    return q
  })
}

function FormattedText({ text }) {
  if (!text) return null
  text = formatQuestionText(text)

  const markers = [
    { open: '«b»', close: '«/b»', el: 'strong' },
    { open: '«hl»', close: '«/hl»', el: 'mark' },
  ]

  const root = []
  const stack = []
  let i = 0
  let uid = 0

  while (i < text.length) {

    if (text[i] === '^') {
      let k = i + 1
      while (k < text.length && text[k] === ' ') k++
      if (k < text.length && text[k] === '(') {
        let depth = 1
        let j = k + 1
        while (j < text.length && depth > 0) {
          if (text[j] === '(') depth++
          else if (text[j] === ')') depth--
          if (depth > 0) j++
        }
        if (depth === 0) {
          const content = text.slice(k + 1, j)
          const target = stack.length > 0 ? stack[stack.length - 1].children : root
          target.push(<sup key={uid++}>{content}</sup>)
          i = j + 1
          continue
        }
      } else if (k < text.length && /[A-Za-z0-9]/.test(text[k])) {
        let j = k + 1
        while (j < text.length && /[A-Za-z0-9./-]/.test(text[j])) j++
        const content = text.slice(k, j)
        const target = stack.length > 0 ? stack[stack.length - 1].children : root
        target.push(<sup key={uid++}>{content}</sup>)
        i = j
        continue
      }
    }

    let matched = false
    for (const m of markers) {
      if (text.slice(i, i + m.open.length) === m.open) {
        stack.push({ m, children: [] })
        i += m.open.length
        matched = true
        break
      }
      if (m.close && text.slice(i, i + m.close.length) === m.close) {
        if (stack.length > 0 && stack[stack.length - 1].m === m) {
          const frame = stack.pop()
          const El = m.el
          const target = stack.length > 0 ? stack[stack.length - 1].children : root
          target.push(<El key={uid++}>{frame.children}</El>)
        }
        i += m.close.length
        matched = true
        break
      }
    }
    if (matched) continue

    let nextPos = text.length
    for (const m of markers) {
      const p = text.indexOf(m.open, i)
      if (p >= 0 && p < nextPos) nextPos = p
    }
    if (stack.length > 0) {
      const top = stack[stack.length - 1].m
      if (top.close) {
        const p = text.indexOf(top.close, i)
        if (p >= 0 && p < nextPos) nextPos = p
      }
    }

    const np = text.indexOf('^(', i)
    if (np >= 0 && np < nextPos) nextPos = np

    if (nextPos === i) {
      const target = stack.length > 0 ? stack[stack.length - 1].children : root
      target.push(text[i])
      i++
    } else {
      const segment = text.slice(i, nextPos)
      const target = stack.length > 0 ? stack[stack.length - 1].children : root
      target.push(segment)
      i = nextPos
    }
  }

  return <>{root}</>
}

// ──────────────────────────────────────────────────────────────────────────────
// Candidate Dashboard
// ──────────────────────────────────────────────────────────────────────────────

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

function SessionDetailModal({ sessionId, onClose }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/user/sessions/${sessionId}`).then(r => { setDetail(r); setLoading(false) }).catch(() => setLoading(false))
  }, [sessionId])

  if (loading) return <div className="modal-overlay" onClick={onClose}><div className="modal-content" onClick={e => e.stopPropagation()} style={{ padding: '2rem', textAlign: 'center' }}><div className="loading-spinner" /></div></div>
  if (!detail?.session) return null

  const report = detail.session
  const scores = report.breakdown || report.scores || {}

  return (
    <div className="modal-overlay" onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div className="modal-content" onClick={e => e.stopPropagation()} style={{ background: '#1e293b', borderRadius: 16, padding: '2rem', maxWidth: 600, width: '90%', maxHeight: '80vh', overflow: 'auto', border: '1px solid rgba(255,255,255,0.08)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f1f5f9' }}>{report.selectedCompany || 'Interview'} Report</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', fontSize: '1.25rem', cursor: 'pointer' }}>&times;</button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.75rem', marginBottom: '1.5rem' }}>
          {Object.entries(scores).map(([key, val]) => (
            <div key={key} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '0.75rem 1rem' }}>
              <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'capitalize' }}>{key}</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 700, color: val >= 70 ? '#34d399' : val >= 50 ? '#fbbf24' : '#f87171' }}>{val}%</div>
            </div>
          ))}
        </div>

        <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '1rem', marginBottom: '1rem' }}>
          <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Overall Score</div>
          <div style={{ fontSize: '2rem', fontWeight: 700, color: '#818cf8' }}>{report.overallScore}%</div>
        </div>

        {report.strengths?.length > 0 && (
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#34d399', marginBottom: '0.5rem' }}>Strengths</div>
            {report.strengths.map((s, i) => <div key={i} style={{ fontSize: '0.8rem', color: '#cbd5e1', padding: '2px 0' }}>+ {s}</div>)}
          </div>
        )}

        {report.weaknesses?.length > 0 && (
          <div style={{ marginBottom: '1rem' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#f87171', marginBottom: '0.5rem' }}>Weaknesses</div>
            {report.weaknesses.map((w, i) => <div key={i} style={{ fontSize: '0.8rem', color: '#cbd5e1', padding: '2px 0' }}>- {w}</div>)}
          </div>
        )}

        {detail.proctoring && (
          <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '1rem' }}>
            <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#94a3b8', marginBottom: '0.5rem' }}>Proctoring</div>
            <div style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>Integrity Score: {detail.proctoring.integrity_score || 100}%</div>
            <div style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>Status: {detail.proctoring.assessment_status || 'N/A'}</div>
          </div>
        )}
      </div>
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────────────
// Recruiter / Admin Portal
// ──────────────────────────────────────────────────────────────────────────────

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
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <div className="loading-spinner" />
        <p className="muted" style={{ marginTop: '1rem' }}>Loading recruiter portal...</p>
      </div>
    )
  }

  return (
    <div style={{ padding: '1.5rem', maxWidth: '1200px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#f1f5f9' }}>Recruiter Portal</h2>
          <p className="muted" style={{ fontSize: '0.85rem' }}>Manage candidates and review interview performance</p>
        </div>
        <button className="btn ghost" style={{ fontSize: '0.8rem' }} onClick={fetchData}>Refresh</button>
      </div>

      {/* Tab Navigation */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '1px solid rgba(255,255,255,0.06)', paddingBottom: '0.5rem' }}>
        {[
          { key: 'overview', label: 'Overview', icon: LayoutDashboard },
          { key: 'candidates', label: 'Candidates', icon: Users },
          { key: 'sessions', label: 'All Sessions', icon: BarChart2 },
        ].map(t => (
          <button key={t.key} onClick={() => { setTab(t.key); if (t.key !== 'sessions') handleClearCandidateFilter() }} style={{
            display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem', borderRadius: 8,
            background: tab === t.key ? 'rgba(129,140,248,0.15)' : 'transparent',
            color: tab === t.key ? '#818cf8' : '#94a3b8', border: 'none', cursor: 'pointer', fontSize: '0.85rem', fontWeight: 500,
            transition: 'all 0.15s ease'
          }}>
            <t.icon size={16} /> {t.label}
          </button>
        ))}
      </div>

      {/* Search Bar */}
      <div style={{ marginBottom: '1rem', position: 'relative' }}>
        <Search size={16} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: '#64748b' }} />
        <input value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder={selectedCandidate ? `Filtering by: ${selectedCandidate} (clear to show all)` : "Search candidates or companies..."}
          style={{ width: '100%', padding: '0.6rem 0.6rem 0.6rem 2.25rem', borderRadius: 8, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.04)', color: '#f1f5f9', fontSize: '0.85rem', outline: 'none' }} />
        {selectedCandidate && (
          <button onClick={handleClearCandidateFilter} style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'rgba(248,113,113,0.15)', color: '#f87171', border: 'none', borderRadius: 4, padding: '2px 8px', cursor: 'pointer', fontSize: '0.75rem' }}>
            Clear filter
          </button>
        )}
      </div>

      {tab === 'overview' && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
            {[
              { label: 'Total Candidates', value: stats?.total_candidates || 0, color: '#818cf8' },
              { label: 'Total Interviews', value: stats?.total_interviews || 0, color: '#34d399' },
              { label: 'Avg Platform Score', value: `${stats?.avg_platform_score || 0}%`, color: '#fbbf24' },
              { label: 'Top Score', value: `${stats?.top_score || 0}%`, color: '#f87171' },
            ].map((card, i) => (
              <div key={i} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, padding: '1.25rem', border: '1px solid rgba(255,255,255,0.06)' }}>
                <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '0.25rem' }}>{card.label}</div>
                <div style={{ fontSize: '1.75rem', fontWeight: 700, color: card.color }}>{card.value}</div>
              </div>
            ))}
          </div>

          {/* Recent Sessions */}
          <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, padding: '1.5rem', border: '1px solid rgba(255,255,255,0.06)' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#f1f5f9', marginBottom: '1rem' }}>Recent Interviews</h3>
            {allSessions.slice(0, 5).map(s => (
              <div key={s.session_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                <div>
                  <span style={{ color: '#f1f5f9', fontWeight: 500, fontSize: '0.85rem' }}>{s.company || 'N/A'}</span>
                  <span style={{ color: '#64748b', fontSize: '0.75rem', marginLeft: '0.75rem' }}>{new Date(s.date * 1000).toLocaleDateString()}</span>
                </div>
                <span style={{ color: s.overall_score >= 70 ? '#34d399' : '#fbbf24', fontWeight: 600, fontSize: '0.85rem' }}>{s.overall_score}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'candidates' && (
        <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, padding: '1.5rem', border: '1px solid rgba(255,255,255,0.06)' }}>
          {filteredCandidates.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
              <Users size={40} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
              <p>No candidates found</p>
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                  {['Name', 'Email', 'Interviews', 'Avg Score', 'Last Active', 'Action'].map(h => (
                    <th key={h} style={{ padding: '0.75rem', textAlign: 'left', color: '#94a3b8', fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredCandidates.map(c => (
                  <tr key={c.email} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                    <td style={{ padding: '0.75rem', color: '#f1f5f9', fontWeight: 500 }}>{c.name}</td>
                    <td style={{ padding: '0.75rem', color: '#94a3b8' }}>{c.email}</td>
                    <td style={{ padding: '0.75rem', color: '#cbd5e1' }}>{c.interview_count}</td>
                    <td style={{ padding: '0.75rem', color: c.avg_score >= 70 ? '#34d399' : '#fbbf24', fontWeight: 600 }}>{c.avg_score}%</td>
                    <td style={{ padding: '0.75rem', color: '#94a3b8' }}>{c.last_active ? new Date(c.last_active * 1000).toLocaleDateString() : 'N/A'}</td>
                    <td style={{ padding: '0.75rem' }}>
                      <button className="btn ghost" style={{ fontSize: '0.75rem', padding: '4px 12px' }} onClick={() => handleViewCandidateSessions(c.email)}>View Sessions</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {tab === 'sessions' && (
        <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 12, padding: '1.5rem', border: '1px solid rgba(255,255,255,0.06)' }}>
          {filteredSessions.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
              <BarChart2 size={40} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
              <p>No sessions found</p>
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                  {['Date', 'Company', 'Rounds', 'Score', 'Actions'].map(h => (
                    <th key={h} style={{ padding: '0.75rem', textAlign: 'left', color: '#94a3b8', fontWeight: 500 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredSessions.map(s => (
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
                    <td style={{ padding: '0.75rem', color: s.overall_score >= 70 ? '#34d399' : '#fbbf24', fontWeight: 600 }}>{s.overall_score}%</td>
                    <td style={{ padding: '0.75rem', display: 'flex', gap: '0.5rem' }}>
                      <button className="btn ghost" style={{ fontSize: '0.75rem', padding: '4px 12px' }} onClick={() => openModal(s.session_id, 'report')}>Report</button>
                      <button className="btn ghost" style={{ fontSize: '0.75rem', padding: '4px 12px', color: '#f87171' }} onClick={() => openModal(s.session_id, 'proctoring')}>Proctoring</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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

function AdminSessionModal({ sessionId, modalType = 'report', onClose }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/admin/sessions/${sessionId}`).then(r => { setDetail(r); setLoading(false) }).catch(() => setLoading(false))
  }, [sessionId])

  if (loading) return <div className="modal-overlay" onClick={onClose}><div className="modal-content" onClick={e => e.stopPropagation()} style={{ padding: '2rem', textAlign: 'center' }}><div className="loading-spinner" /></div></div>
  if (!detail?.session) return null

  const report = detail.session
  const scores = report.breakdown || report.scores || {}
  const proctoring = detail.proctoring

  return (
    <div className="modal-overlay" onClick={onClose} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
      <div className="modal-content" onClick={e => e.stopPropagation()} style={{ background: '#1e293b', borderRadius: 16, padding: '2rem', maxWidth: 650, width: '90%', maxHeight: '85vh', overflow: 'auto', border: '1px solid rgba(255,255,255,0.08)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#f1f5f9' }}>
            {modalType === 'proctoring' ? 'Proctoring Details' : 'Session Report'} — {report.candidateName || 'Candidate'}
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', fontSize: '1.25rem', cursor: 'pointer' }}>&times;</button>
        </div>

        {/* Report View */}
        {modalType === 'report' && (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.75rem', marginBottom: '1.5rem' }}>
              {Object.entries(scores).map(([key, val]) => (
                <div key={key} style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '0.75rem 1rem' }}>
                  <div style={{ fontSize: '0.75rem', color: '#94a3b8', textTransform: 'capitalize' }}>{key}</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: val >= 70 ? '#34d399' : val >= 50 ? '#fbbf24' : '#f87171' }}>{val}%</div>
                </div>
              ))}
            </div>

            <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '1rem', marginBottom: '1rem' }}>
              <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Overall Score</div>
              <div style={{ fontSize: '2rem', fontWeight: 700, color: '#818cf8' }}>{report.overallScore}%</div>
            </div>

            {report.feedback && (
              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#94a3b8', marginBottom: '0.5rem' }}>AI Feedback</div>
                <p style={{ fontSize: '0.8rem', color: '#cbd5e1', lineHeight: 1.5 }}>{typeof report.feedback === 'string' ? report.feedback : report.feedback.summary || ''}</p>
              </div>
            )}

            {report.recommendations?.length > 0 && (
              <div style={{ marginBottom: '1rem' }}>
                <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#38bdf8', marginBottom: '0.5rem' }}>Recommendations</div>
                {report.recommendations.map((r, i) => <div key={i} style={{ fontSize: '0.8rem', color: '#cbd5e1', padding: '2px 0' }}>+ {r}</div>)}
              </div>
            )}
          </>
        )}

        {/* Proctoring View */}
        {modalType === 'proctoring' && (
          <>
            {!proctoring ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
                <Shield size={40} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                <p>No proctoring data available for this session</p>
              </div>
            ) : (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1.5rem' }}>
                  <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '1rem' }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Integrity Score</div>
                    <div style={{ fontSize: '1.75rem', fontWeight: 700, color: (proctoring.integrity_score || 100) >= 80 ? '#34d399' : '#f87171' }}>
                      {proctoring.integrity_score || 100}%
                    </div>
                  </div>
                  <div style={{ background: 'rgba(255,255,255,0.04)', borderRadius: 10, padding: '1rem' }}>
                    <div style={{ fontSize: '0.75rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Status</div>
                    <div style={{ fontSize: '1rem', fontWeight: 600, color: '#f1f5f9' }}>{proctoring.assessment_status || 'N/A'}</div>
                  </div>
                </div>

                {proctoring.violations?.length > 0 && (
                  <div style={{ marginBottom: '1rem' }}>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#f87171', marginBottom: '0.5rem' }}>Violations ({proctoring.violations.length})</div>
                    {proctoring.violations.map((v, i) => (
                      <div key={i} style={{ fontSize: '0.8rem', color: '#fbbf24', padding: '4px 0', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                        {v.type || v.message || JSON.stringify(v)}
                        {v.timestamp && <span style={{ color: '#64748b', marginLeft: '0.5rem' }}>{new Date(v.timestamp * 1000).toLocaleTimeString()}</span>}
                      </div>
                    ))}
                  </div>
                )}

                {proctoring.snapshots?.length > 0 && (
                  <div>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#94a3b8', marginBottom: '0.5rem' }}>Snapshots ({proctoring.snapshots.length})</div>
                    <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                      {proctoring.snapshots.map((snap, i) => (
                        <div key={i} style={{ width: 80, height: 60, borderRadius: 8, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
                          {snap.image ? <img src={snap.image} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', fontSize: '0.6rem' }}>No img</div>}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default function App() {
  const [user, setUser] = useState(getStoredUser)
  const [proctoring, setProctoring] = usePersistentProctoring()
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

  useEffect(() => {
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
      setState((s) => ({ ...s, companies: {} }))
    })
  }, [])

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

  return (
    <Shell state={state} user={user} onLogout={logout} proctoring={proctoring}>
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
    </Shell>
  )
}
