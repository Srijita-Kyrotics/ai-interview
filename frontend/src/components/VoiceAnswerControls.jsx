import React, { useEffect, useRef, useState } from 'react'

function getSpeechRecognition() {
  return window.SpeechRecognition || window.webkitSpeechRecognition
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

export { VoiceAnswerControls }
