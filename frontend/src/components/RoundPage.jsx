import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Mic, Square, Play, RotateCcw } from 'lucide-react'
import { api } from '../api'
import { roundDurations } from '../constants'
import { ProctoringModal } from '../proctoring/ProctoringUI'
import { useAssessmentProctoring } from '../proctoring/useAssessmentProctoring'
import { formatQuestionText } from '../utils/questionFormat'
import { CodeEditor } from './CodeEditor'

function formatTime(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0')
  const seconds = (totalSeconds % 60).toString().padStart(2, '0')
  return `${minutes}:${seconds}`
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

function getNextStage(type) {
  if (type === 'aptitude') return 'coding'
  if (type === 'coding') return 'technical'
  if (type === 'technical') return 'hr'
  return 'report'
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
  const [audioUrl, setAudioUrl] = useState(null)
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
    if (!audioBlob) { setAudioUrl(null); return }
    const url = URL.createObjectURL(audioBlob)
    setAudioUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [audioBlob])

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
                          <Mic size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} /> Start Recording
                        </button>
                      ) : (
                        <button className="btn danger record-btn" type="button" onClick={stopRecording}>
                          <Square size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} /> Stop Recording
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
                        <Play size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} /> Play
                      </button>
                      <button className="btn ghost" type="button" onClick={reRecord}>
                        <RotateCcw size={16} style={{ verticalAlign: 'middle', marginRight: '6px' }} /> Re-record
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

export { RoundPage, processAptitudeText }
