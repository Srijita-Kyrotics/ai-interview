import React, { useCallback, useEffect, useRef, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Mic, MicOff, Send, Code2, MessageSquare, Volume2, VolumeX, PhoneOff, Clock, AlertTriangle } from 'lucide-react'
import { api } from '../api'
import { useInterviewWebSocket } from '../hooks/useInterviewWebSocket'
import { useAssessmentProctoring } from '../proctoring/useAssessmentProctoring'
import { ProctoringModal, ProctoringPanel } from '../proctoring/ProctoringUI'
import { speak, stopSpeaking, playChime } from '../utils/speak'
import { CodeEditor } from './CodeEditor'

const SPEECH_SUPPORTED = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition)
const RESTART_DELAY_MS = 600
const SILENCE_AUTO_SEND_MS = 4000
const QUESTION_TIMEOUT_MS = 180000

function LiveInterview({ title, questions, state, setState, proctoring, setProctoring }) {
  const navigate = useNavigate()

  // ── Proctoring ────────────────────────────────────────────────────────
  const [hasPermissions, setHasPermissions] = useState(false)
  const [isStarted, setIsStarted] = useState(false)
  const [proctorError, setProctorError] = useState('')
  const [userStream, setUserStream] = useState(null)
  const [screenStream, setScreenStream] = useState(null)
  const videoRef = useRef(null)
  const screenRef = useRef(null)

  // ── Conversation ──────────────────────────────────────────────────────
  const [messages, setMessages] = useState([])
  const [inputText, setInputText] = useState('')
  const [isAiSpeaking, setIsAiSpeaking] = useState(false)
  const [isThinking, setIsThinking] = useState(false)

  // ── Voice state ───────────────────────────────────────────────────────
  const [voiceMode, setVoiceMode] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const [muted, setMuted] = useState(false)
  const [speechError, setSpeechError] = useState('')
  const [audioLevel, setAudioLevel] = useState(0)

  // ── Code ──────────────────────────────────────────────────────────────
  const [code, setCode] = useState('')
  const [language, setLanguage] = useState('javascript')
  const [activeTab, setActiveTab] = useState('chat')
  const [completed, setCompleted] = useState(false)

  // ── Interview metrics ─────────────────────────────────────────────────
  const questionStartTimeRef = useRef(Date.now())
  const voiceActiveSinceRef = useRef(null)
  const totalVoiceDurationRef = useRef(0)
  const questionCountRef = useRef(0)

  // ── Refs ──────────────────────────────────────────────────────────────
  const scrollerRef = useRef(null)
  const recognitionRef = useRef(null)
  const submittingRef = useRef(false)
  const mutedRef = useRef(false)
  const voiceModeRef = useRef(false)
  const isAiSpeakingRef = useRef(false)
  const isThinkingRef = useRef(false)
  const inputTextRef = useRef('')
  const languageRef = useRef('javascript')
  const autoRestartRef = useRef(false)
  const ttsRef = useRef(null)
  const silenceTimerRef = useRef(null)
  const restartTimeoutRef = useRef(null)
  const audioLevelTimerRef = useRef(null)

  const roleKey = title.toLowerCase().includes('hr') ? 'hr' : 'technical'

  // ── Keep refs in sync ─────────────────────────────────────────────────
  useEffect(() => { mutedRef.current = muted }, [muted])
  useEffect(() => { voiceModeRef.current = voiceMode }, [voiceMode])
  useEffect(() => { isAiSpeakingRef.current = isAiSpeaking }, [isAiSpeaking])
  useEffect(() => { isThinkingRef.current = isThinking }, [isThinking])
  useEffect(() => { inputTextRef.current = inputText }, [inputText])
  useEffect(() => { languageRef.current = language }, [language])

  // ── Proctoring ────────────────────────────────────────────────────────
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

  // ── Track voice activity duration ─────────────────────────────────────
  const startVoiceTracking = useCallback(() => {
    voiceActiveSinceRef.current = Date.now()
  }, [])

  const stopVoiceTracking = useCallback(() => {
    if (voiceActiveSinceRef.current) {
      const duration = (Date.now() - voiceActiveSinceRef.current) / 1000
      totalVoiceDurationRef.current += Math.min(duration, 300)
      voiceActiveSinceRef.current = null
    }
  }, [])

  // ── Record question metric ────────────────────────────────────────────
  const recordQuestionMetric = useCallback((answerText, hasVoice) => {
    const timeSpent = Math.round((Date.now() - questionStartTimeRef.current) / 1000)
    questionStartTimeRef.current = Date.now()
    questionCountRef.current += 1

    const voiceDuration = Math.round(totalVoiceDurationRef.current)
    totalVoiceDurationRef.current = 0

    setProctoring((prev) => ({
      ...prev,
      timeSpent: {
        ...prev.timeSpent,
        [roleKey]: (prev.timeSpent?.[roleKey] || 0) + timeSpent
      },
      interviewMetrics: {
        ...prev.interviewMetrics,
        [roleKey]: {
          questionTimes: [...(prev.interviewMetrics?.[roleKey]?.questionTimes || []), timeSpent],
          voiceDurations: [...(prev.interviewMetrics?.[roleKey]?.voiceDurations || []), voiceDuration],
          submissions: [
            ...(prev.interviewMetrics?.[roleKey]?.submissions || []),
            {
              questionIndex: questionCountRef.current,
              submittedAt: new Date().toISOString(),
              answerLength: answerText.length,
              hasVoice
            }
          ]
        }
      }
    }))
  }, [roleKey, setProctoring])

  // ── Clear silence auto-send timer ─────────────────────────────────────
  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
  }, [])

  // ── Audio level monitor ───────────────────────────────────────────────
  const startAudioLevelMonitor = useCallback(() => {
    if (audioLevelTimerRef.current) return
    const stream = userStream
    if (!stream) return

    let audioCtx = null
    let analyser = null
    let source = null

    try {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)()
      source = audioCtx.createMediaStreamSource(stream)
      analyser = audioCtx.createAnalyser()
      analyser.fftSize = 256
      source.connect(analyser)

      const dataArray = new Uint8Array(analyser.frequencyBinCount)
      const updateLevel = () => {
        analyser.getByteFrequencyData(dataArray)
        let sum = 0
        for (let i = 0; i < dataArray.length; i++) sum += dataArray[i]
        const avg = sum / dataArray.length
        setAudioLevel(Math.min(100, Math.round(avg * 2)))
      }

      audioLevelTimerRef.current = { timer: setInterval(updateLevel, 150), audioCtx }
    } catch {
      // AudioContext not available
    }
  }, [userStream])

  const stopAudioLevelMonitor = useCallback(() => {
    if (audioLevelTimerRef.current) {
      clearInterval(audioLevelTimerRef.current.timer)
      try { audioLevelTimerRef.current.audioCtx?.close() } catch {}
      audioLevelTimerRef.current = null
    }
    setAudioLevel(0)
  }, [])

  useEffect(() => {
    if (isStarted && userStream) startAudioLevelMonitor()
    return () => stopAudioLevelMonitor()
  }, [isStarted, userStream, startAudioLevelMonitor, stopAudioLevelMonitor])

  // ── Speech recognition helpers ────────────────────────────────────────
  const stopListening = useCallback(() => {
    autoRestartRef.current = false
    clearSilenceTimer()
    if (restartTimeoutRef.current) {
      clearTimeout(restartTimeoutRef.current)
      restartTimeoutRef.current = null
    }
    if (recognitionRef.current) {
      try { recognitionRef.current.stop() } catch {}
      recognitionRef.current = null
    }
    stopVoiceTracking()
    setIsListening(false)
  }, [clearSilenceTimer, stopVoiceTracking])

  const startListening = useCallback(() => {
    if (!SPEECH_SUPPORTED) {
      setSpeechError('Speech recognition is not supported in this browser. Please use Chrome or Edge.')
      return
    }

    if (recognitionRef.current || isThinkingRef.current) return

    if (isAiSpeakingRef.current) {
      ttsRef.current?.cancel()
      stopSpeaking()
      setIsAiSpeaking(false)
    }

    setSpeechError('')

    const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)()
    recognition.continuous = true
    recognition.interimResults = true
    recognition.lang = 'en-US'
    recognition.maxAlternatives = 1

    recognition.onstart = () => {
      setIsListening(true)
      startVoiceTracking()
    }

    recognition.onresult = (event) => {
      let final = ''
      let interim = ''
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript
        if (event.results[i].isFinal) {
          final += transcript
        } else {
          interim += transcript
        }
      }

      if (interim) {
        setInputText(interim)
        inputTextRef.current = interim
        clearSilenceTimer()
      }

      if (final) {
        stopVoiceTracking()
        startVoiceTracking()
        setInputText(prev => {
          const base = prev && !prev.endsWith(' ') ? prev + ' ' : prev || ''
          return base + final
        })
        clearSilenceTimer()

        if (autoRestartRef.current) {
          silenceTimerRef.current = setTimeout(() => {
            const text = inputTextRef.current.trim()
            if (text && autoRestartRef.current && !isThinkingRef.current) {
              autoRestartRef.current = false
              setIsListening(false)
              recognitionRef.current = null
              stopVoiceTracking()
              sendMessage(text)
              setMessages(prev => [...prev, { role: 'candidate', text }])
              recordQuestionMetric(text, true)
              setInputText('')
              inputTextRef.current = ''
            }
          }, SILENCE_AUTO_SEND_MS)
        }
      }
    }

    recognition.onerror = (event) => {
      if (event.error === 'no-speech' || event.error === 'aborted') {
        if (autoRestartRef.current && !isThinkingRef.current) {
          restartTimeoutRef.current = setTimeout(() => {
            try { recognition.start() } catch {}
          }, RESTART_DELAY_MS)
        }
        return
      }

      if (event.error === 'not-allowed') {
        setIsListening(false)
        autoRestartRef.current = false
        setSpeechError('Microphone access denied. Please allow microphone access and try again.')
        return
      }

      if (event.error === 'network') {
        setSpeechError('Network error during speech recognition. Retrying...')
        if (autoRestartRef.current && !isThinkingRef.current) {
          restartTimeoutRef.current = setTimeout(() => {
            try { recognition.start() } catch {}
          }, 2000)
        }
        return
      }

      if (event.error === 'service-not-allowed') {
        setSpeechError('Speech service not available. Please try a different browser.')
        setIsListening(false)
        autoRestartRef.current = false
        return
      }

      if (autoRestartRef.current && !isThinkingRef.current) {
        restartTimeoutRef.current = setTimeout(() => {
          try { recognition.start() } catch {}
        }, RESTART_DELAY_MS)
      }
    }

    recognition.onend = () => {
      const text = inputTextRef.current.trim()
      if (text && autoRestartRef.current && !isThinkingRef.current && !silenceTimerRef.current) {
        autoRestartRef.current = false
        setIsListening(false)
        recognitionRef.current = null
        stopVoiceTracking()
        sendMessage(text)
        setMessages(prev => [...prev, { role: 'candidate', text }])
        recordQuestionMetric(text, true)
        setInputText('')
        inputTextRef.current = ''
        return
      }

      if (autoRestartRef.current && !isThinkingRef.current) {
        restartTimeoutRef.current = setTimeout(() => {
          try {
            recognition.start()
          } catch {
            setIsListening(false)
            recognitionRef.current = null
          }
        }, RESTART_DELAY_MS)
      } else {
        setIsListening(false)
        recognitionRef.current = null
        stopVoiceTracking()
      }
    }

    recognitionRef.current = recognition
    try {
      recognition.start()
    } catch {
      setIsListening(false)
      recognitionRef.current = null
      setSpeechError('Failed to start speech recognition. Please try again.')
    }
  }, [stopListening, startVoiceTracking, stopVoiceTracking, sendMessage, recordQuestionMetric, clearSilenceTimer])

  // ── Voice mode toggle ─────────────────────────────────────────────────
  const toggleVoiceMode = useCallback(() => {
    if (voiceModeRef.current) {
      autoRestartRef.current = false
      stopListening()
      setVoiceMode(false)
    } else {
      if (!SPEECH_SUPPORTED) {
        setSpeechError('Speech recognition is not supported in this browser. Please use Chrome or Edge.')
        return
      }
      autoRestartRef.current = true
      setVoiceMode(true)
      setSpeechError('')
      startListening()
    }
  }, [startListening, stopListening])

  // ── Manual speak toggle (one-shot) ────────────────────────────────────
  const toggleManualListen = useCallback(() => {
    if (isListening) {
      stopListening()
    } else {
      autoRestartRef.current = false
      startListening()
    }
  }, [isListening, startListening, stopListening])

  // ── WebSocket ─────────────────────────────────────────────────────────
  const onMessage = useCallback((data) => {
    const msg = { role: 'interviewer', text: data.text, timestamp: data.timestamp }
    setMessages(prev => [...prev, msg])
    questionStartTimeRef.current = Date.now()

    if (!mutedRef.current) {
      playChime()
      setTimeout(() => {
        setIsAiSpeaking(true)
        const ref = speak(data.text, {
          onEnd: () => {
            setIsAiSpeaking(false)
            if (voiceModeRef.current && !isThinkingRef.current) {
              restartTimeoutRef.current = setTimeout(() => startListening(), 300)
            }
          }
        })
        ttsRef.current = ref
      }, 400)
    } else {
      if (voiceModeRef.current && !isThinkingRef.current) {
        restartTimeoutRef.current = setTimeout(() => startListening(), 300)
      }
    }
  }, [startListening])

  const onCodeReview = useCallback((data) => {
    const msg = { role: 'reviewer', text: data.text, timestamp: data.timestamp }
    setMessages(prev => [...prev, msg])

    if (!mutedRef.current) {
      playChime()
      setTimeout(() => {
        setIsAiSpeaking(true)
        const ref = speak(`Code review. ${data.text}`, {
          onEnd: () => {
            setIsAiSpeaking(false)
            if (voiceModeRef.current && !isThinkingRef.current) {
              restartTimeoutRef.current = setTimeout(() => startListening(), 300)
            }
          }
        })
        ttsRef.current = ref
      }, 400)
    }
  }, [startListening])

  const onComplete = useCallback(() => {
    setCompleted(true)
    stopListening()
  }, [stopListening])

  const onError = useCallback((msg) => {
    setMessages(prev => [...prev, { role: 'system', text: msg }])
  }, [])

  const onThinkingChange = useCallback((thinking) => {
    setIsThinking(thinking)
    if (thinking) {
      ttsRef.current?.cancel()
      stopSpeaking()
      setIsAiSpeaking(false)
      clearSilenceTimer()
    }
  }, [clearSilenceTimer])

  const {
    status: wsStatus,
    codeReview,
    sendMessage,
    sendCodeUpdate,
    requestCodeReview,
    endInterview,
    disconnect,
    sendMetrics,
  } = useInterviewWebSocket({
    sessionId: state.sessionId,
    roundKey: roleKey,
    onMessage,
    onCodeReview,
    onComplete,
    onError,
    onThinking: onThinkingChange,
  })

  // ── Stream tracks ─────────────────────────────────────────────────────
  useEffect(() => {
    if (hasPermissions || isStarted) {
      if (videoRef.current && userStream) videoRef.current.srcObject = userStream
      if (screenRef.current && screenStream) screenRef.current.srcObject = screenStream
    }
  }, [hasPermissions, isStarted, userStream, screenStream])

  useEffect(() => {
    return () => {
      stopListening()
      userStream?.getTracks().forEach(t => t.stop())
      screenStream?.getTracks().forEach(t => t.stop())
      stopSpeaking()
      ttsRef.current?.cancel()
      clearSilenceTimer()
      stopAudioLevelMonitor()
      if (restartTimeoutRef.current) clearTimeout(restartTimeoutRef.current)
    }
  }, [])

  // ── Auto-scroll ───────────────────────────────────────────────────────
  useEffect(() => {
    if (scrollerRef.current) {
      scrollerRef.current.scrollTo({ top: scrollerRef.current.scrollHeight, behavior: 'smooth' })
    }
  }, [messages])

  // ── Start proctoring ──────────────────────────────────────────────────
  const startProctoring = async () => {
    let uMedia = null
    let dMedia = null
    try {
      setProctorError('')
      uMedia = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
      dMedia = await navigator.mediaDevices.getDisplayMedia({ video: true })
      setUserStream(uMedia)
      setScreenStream(dMedia)
      setHasPermissions(true)
    } catch (err) {
      const msg = err?.name === 'NotAllowedError'
        ? 'Permission denied. Please allow webcam, microphone, and screen sharing.'
        : 'Failed to access webcam, microphone, or screen share.'
      setProctorError(msg)
      uMedia?.getTracks().forEach(t => t.stop())
      dMedia?.getTracks().forEach(t => t.stop())
    }
  }

  // ── Begin interview ───────────────────────────────────────────────────
  const beginInterview = async () => {
    try {
      await proctor.requestFullscreen()
      const res = await api.post('/start-round', { session_id: state.sessionId, company: state.company, round_key: roleKey })
      if (!res.ok && res.error) {
        setProctorError(res.error)
        return
      }
      questionStartTimeRef.current = Date.now()
      setIsStarted(true)
    } catch {
      setProctorError('Failed to start the interview.')
    }
  }

  // ── Manual send ───────────────────────────────────────────────────────
  const handleSend = useCallback(() => {
    const text = inputTextRef.current.trim()
    if (!text || submittingRef.current || isThinkingRef.current) return
    submittingRef.current = true

    stopListening()
    stopVoiceTracking()
    sendMessage(text)
    setMessages(prev => [...prev, { role: 'candidate', text }])
    recordQuestionMetric(text, false)
    setInputText('')
    inputTextRef.current = ''
    submittingRef.current = false
  }, [sendMessage, stopListening, stopVoiceTracking, recordQuestionMetric])

  // ── Code handlers ─────────────────────────────────────────────────────
  const handleCodeChange = useCallback((newCode) => {
    setCode(newCode)
    sendCodeUpdate(newCode, languageRef.current)
  }, [sendCodeUpdate])

  const handleLanguageChange = useCallback((newLang) => {
    setLanguage(newLang)
    languageRef.current = newLang
    sendCodeUpdate(code, newLang)
  }, [code, sendCodeUpdate])

  const handleSubmitCode = useCallback(async () => {
    if (!code.trim()) return
    try {
      await api.post('/submit-code', {
        session_id: state.sessionId,
        round_key: roleKey,
        question_index: 0,
        language,
        code,
      })
      requestCodeReview()
    } catch {}
  }, [code, language, state.sessionId, roleKey, requestCodeReview])

  // ── End / skip ────────────────────────────────────────────────────────
  const handleEndInterview = useCallback(() => {
    stopListening()
    stopVoiceTracking()
    sendMetrics({
      questionTimes: proctoring.interviewMetrics?.[roleKey]?.questionTimes || [],
      voiceDurations: proctoring.interviewMetrics?.[roleKey]?.voiceDurations || [],
      submissions: proctoring.interviewMetrics?.[roleKey]?.submissions || [],
    })
    endInterview()
    disconnect()
    stopSpeaking()
    ttsRef.current?.cancel()
    const nextStage = roleKey === 'hr' ? 'report' : 'hr'
    setState(s => ({ ...s, stage: nextStage, roundTransition: true }))
    navigate(`/${nextStage}`)
  }, [endInterview, disconnect, roleKey, setState, navigate, stopListening, stopVoiceTracking, sendMetrics, proctoring])

  const handleSkip = useCallback(() => {
    stopListening()
    stopVoiceTracking()
    disconnect()
    stopSpeaking()
    ttsRef.current?.cancel()
    const nextStage = roleKey === 'hr' ? 'report' : 'hr'
    setState(s => ({ ...s, stage: nextStage, roundTransition: true }))
    navigate(`/${nextStage}`)
  }, [disconnect, roleKey, setState, navigate, stopListening, stopVoiceTracking])

  // ── Guards ────────────────────────────────────────────────────────────
  if (!state.sessionId) return <Navigate to="/resume" replace />
  if (!state.company) return <Navigate to="/company" replace />

  // ── Pre-start screen ──────────────────────────────────────────────────
  if (!isStarted) {
    return (
      <section className="panel main-panel">
        <div className="section-head">
          <div>
            <p className="eyebrow">{state.company} live room</p>
            <h2>{title} - Live Interview</h2>
            <p className="muted">
              Grant webcam, microphone, and screen sharing permissions.
              Obi, your AI interviewer, will speak to you in real-time and watch your code as you write it.
            </p>
          </div>
        </div>
        {proctorError ? <div className="notice danger">{proctorError}</div> : null}
        {!SPEECH_SUPPORTED && (
          <div className="notice warning">
            <AlertTriangle size={14} /> Speech recognition is not supported in this browser. Voice mode will be disabled. Please use Chrome or Edge for full voice support.
          </div>
        )}
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

  // ── Active interview ──────────────────────────────────────────────────
  const languages = ['javascript', 'python', 'java', 'c', 'csharp']
  const langLabels = { javascript: 'JavaScript', python: 'Python', java: 'Java', c: 'C', csharp: 'C#' }

  return (
    <section className="panel main-panel interview-panel live-interview">
      <ProctoringModal modal={proctor.modal} onClose={proctor.dismissModal} />

      <div className="section-head">
        <div>
          <p className="eyebrow">{state.company} live room</p>
          <h2>{title}</h2>
        </div>
        <div className="status-pills">
          <span className={`ws-status ws-${wsStatus}`}>{wsStatus === 'connected' ? 'Connected' : 'Connecting...'}</span>
          <span>{title}</span>
        </div>
        <div className="action-row compact">
          <button className="btn ghost" type="button" onClick={() => setMuted(m => !m)}>
            {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
            {muted ? 'Unmute' : 'Mute'}
          </button>
          <button className="btn ghost" type="button" onClick={handleSkip}>Skip Round</button>
          {completed ? (
            <button className="btn primary" type="button" onClick={handleEndInterview}>Finish & Continue</button>
          ) : (
            <button className="btn danger" type="button" onClick={handleEndInterview}>
              <PhoneOff size={14} /> End
            </button>
          )}
        </div>
      </div>

      {/* Main layout: interview + proctoring sidebar */}
      <div className="interview-layout">
        {/* Left: interview content */}
        <div className="interview-main">
          <div className="video-preview-topright interview-webcam">
            <video ref={videoRef} autoPlay muted playsInline style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            <span className="live-indicator">Live</span>
            {isAiSpeaking && <span className="ai-speaking-indicator">Obi speaking...</span>}
          </div>

          {/* Tab bar */}
          <div className="live-interview-tabs">
            <button className={`tab-btn ${activeTab === 'chat' ? 'active' : ''}`} onClick={() => setActiveTab('chat')}>
              <MessageSquare size={14} /> Chat
            </button>
            <button className={`tab-btn ${activeTab === 'code' ? 'active' : ''}`} onClick={() => setActiveTab('code')}>
              <Code2 size={14} /> Code
            </button>
          </div>

          {/* Chat panel */}
          {activeTab === 'chat' && (
            <div className="chat-window" ref={scrollerRef}>
              {messages.map((msg, i) => (
                <div key={`${msg.role}-${i}`} className={`chat-bubble ${msg.role}`}>
                  <b>
                    {msg.role === 'interviewer' ? '🤖 Obi' :
                     msg.role === 'reviewer' ? '📝 Obi - Code Review' :
                     msg.role === 'candidate' ? '👤 You' : '⚡ System'}
                  </b>
                  <p>{msg.text}</p>
                </div>
              ))}
              {isThinking && (
                <div className="chat-bubble interviewer thinking-bubble">
                  <b>🤖 Obi</b>
                  <div className="typing-indicator">
                    <span></span><span></span><span></span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Code panel */}
          {activeTab === 'code' && (
            <div className="live-code-panel">
              <div className="language-tabs">
                {languages.map(lang => (
                  <button key={lang} className={language === lang ? 'active' : ''} onClick={() => handleLanguageChange(lang)}>
                    {langLabels[lang]}
                  </button>
                ))}
              </div>
              <CodeEditor
                value={code}
                onChange={handleCodeChange}
                language={langLabels[language]}
                questionTitle="Live Code"
              />
              {codeReview && (
                <div className="code-review-output">
                  <div className="output-title">AI Code Review</div>
                  <pre>{codeReview.text}</pre>
                </div>
              )}
              <div className="coding-actions">
                <button className="btn primary" type="button" onClick={handleSubmitCode} disabled={!code.trim()}>
                  Submit Code for Review
                </button>
              </div>
            </div>
          )}

          {/* Input area */}
          <div className="live-interview-input">
            {speechError && (
              <div className="speech-error-notice">
                <AlertTriangle size={12} /> {speechError}
              </div>
            )}

            <div className="voice-controls">
              {SPEECH_SUPPORTED && (
                <button
                  className={`btn ${voiceMode ? 'primary voice-active' : 'ghost'}`}
                  type="button"
                  onClick={toggleVoiceMode}
                  title={voiceMode ? 'Disable voice mode' : 'Enable voice mode (continuous listening)'}
                >
                  {voiceMode ? <Mic size={16} /> : <MicOff size={16} />}
                  {voiceMode ? 'Voice On' : 'Voice Off'}
                </button>
              )}

              {!voiceMode && SPEECH_SUPPORTED && (
                <button
                  className={`btn ${isListening ? 'danger recording' : 'ghost'}`}
                  type="button"
                  onClick={toggleManualListen}
                  title={isListening ? 'Stop listening' : 'Listen once'}
                >
                  {isListening ? <MicOff size={14} /> : <Mic size={14} />}
                </button>
              )}
            </div>

            {isListening && (
              <div className="listening-indicator">
                <span className="listening-dot"></span>
                <div className="audio-level-bar">
                  <div className="audio-level-fill" style={{ width: `${audioLevel}%` }} />
                </div>
                Listening...
              </div>
            )}

            <input
              className="input"
              value={inputText}
              onChange={e => { setInputText(e.target.value); inputTextRef.current = e.target.value }}
              onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
              placeholder={voiceMode ? "Listening... (speak or type)" : "Type your answer..."}
              aria-label="Type your answer"
              readOnly={isListening && voiceMode}
            />
            <button className="btn primary" type="button" onClick={handleSend} disabled={!inputText.trim() || isThinking}>
              <Send size={14} /> Send
            </button>
          </div>
        </div>

        {/* Right: proctoring sidebar */}
        <div className="interview-sidebar">
          <ProctoringPanel proctoring={proctoring} />
        </div>
      </div>
    </section>
  )
}

export { LiveInterview }
