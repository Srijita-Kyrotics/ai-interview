import React, { useEffect, useRef, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { interviewQuestionDuration } from '../constants'
import { ProctoringModal } from '../proctoring/ProctoringUI'
import { useAssessmentProctoring } from '../proctoring/useAssessmentProctoring'
import { formatQuestionText } from '../utils/questionFormat'
import { VoiceAnswerControls } from './VoiceAnswerControls'

function audioBlobToDataUrl(blob) {
  if (!blob) return Promise.resolve('')
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => resolve(reader.result || '')
    reader.onerror = reject
    reader.readAsDataURL(blob)
  })
}

function formatTime(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0')
  const seconds = (totalSeconds % 60).toString().padStart(2, '0')
  return `${minutes}:${seconds}`
}

function getSpeechRecognition() {
  return window.SpeechRecognition || window.webkitSpeechRecognition
}

function ChatInterview({ title, questions, state, setState, proctoring, setProctoring }) {
  const navigate = useNavigate()
  const [muted, setMuted] = useState(false)
  const speak = (text) => {
    if (muted || !('speechSynthesis' in window)) return
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(new SpeechSynthesisUtterance(text))
  }
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
      setTimeLeft(interviewQuestionDuration)
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
      setTimeLeft(interviewQuestionDuration)
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
          <button className="btn ghost" type="button" onClick={() => current && speak(formatQuestionText(current.question))} aria-label="Replay question audio">Replay</button>
          <button className="btn ghost" type="button" onClick={() => setMuted((m) => !m)} aria-label={muted ? 'Unmute audio' : 'Mute audio'}>{muted ? 'Unmute' : 'Mute'}</button>
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
        <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Review or type your answer before submitting" aria-label="Type your answer" />
        <button className="btn ghost" type="button" onClick={skipQuestion} disabled={submittingRef.current} aria-label="Skip this question">Skip</button>
        <button className="btn primary" type="button" onClick={() => send(false)} disabled={(!text.trim() && !audioBlob) || submittingRef.current} aria-label="Submit answer">Submit answer</button>
      </div>
    </section>
  )
}

export { ChatInterview }
