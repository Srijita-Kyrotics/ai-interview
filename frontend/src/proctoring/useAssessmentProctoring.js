import { useCallback, useEffect, useRef, useState } from 'react'
import { VIOLATION_PENALTIES } from './proctoringState'
import * as faceapi from 'face-api.js'
import { API, getAuthToken } from '../api.js'

const COOLDOWN_MS = 5000
const NO_FACE_LIMIT_MS = 2000
const DEVTOOLS_THRESHOLD = 160
const FACE_DETECT_INTERVAL_MS = 400
const MODEL_RETRY_DELAY_MS = 5000
const MODEL_MAX_RETRIES = 3

const violationLabels = {
  tab_switch: 'Tab Switch',
  fullscreen_exit: 'Fullscreen Exit',
  screen_share_stop: 'Screen Share Stop',
  no_face: 'No Face',
  face_missing: 'Face Missing',
  multiple_faces: 'Multiple Faces',
  copy_paste: 'Copy/Paste',
  devtools: 'Developer Tools',
  right_click: 'Right Click',
  shortcut: 'Restricted Shortcut',
  half_face: 'Partial Face Detected',
  looking_away: 'Looking Away',
  head_turn: 'Head Turned',
  background_voice: 'Background Voice Detected',
  mouse_stationary: 'Mouse Inactivity',
  rapid_submit: 'Rapid Submission',
  suspicious_object: 'Suspicious Object'
}

function nowLabel(date = new Date()) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

async function postQuietly(path, body) {
  try {
    const token = getAuthToken()
    const headers = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`
    await fetch(`${API}${path}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body)
    })
  } catch {
    // Proctoring must remain usable if the local backend is temporarily unavailable.
  }
}

function captureFrame(video) {
  if (!video || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return ''
  const canvas = document.createElement('canvas')
  canvas.width = Math.min(video.videoWidth, 640)
  canvas.height = Math.round((canvas.width / video.videoWidth) * video.videoHeight)
  const context = canvas.getContext('2d')
  context.drawImage(video, 0, 0, canvas.width, canvas.height)
  const dataUrl = canvas.toDataURL('image/jpeg', 0.76)
  canvas.width = 0
  canvas.height = 0
  return dataUrl
}

function hasVisibleFrame(video) {
  if (!video || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return false
  const canvas = document.createElement('canvas')
  canvas.width = 80
  canvas.height = 60
  const context = canvas.getContext('2d', { willReadFrequently: true })
  context.drawImage(video, 0, 0, canvas.width, canvas.height)
  const data = context.getImageData(0, 0, canvas.width, canvas.height).data
  canvas.width = 0
  canvas.height = 0
  let litPixels = 0
  for (let i = 0; i < data.length; i += 16) {
    const brightness = (data[i] + data[i + 1] + data[i + 2]) / 3
    if (brightness > 20) litPixels += 1
  }
  return litPixels > 60
}

function getPreferredMime() {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
  if (typeof MediaRecorder === 'undefined') return ''
  for (const type of types) {
    if (MediaRecorder.isTypeSupported(type)) return type
  }
  return ''
}

export function useAssessmentProctoring({
  active,
  round,
  sessionId,
  navigate,
  setState,
  proctoring,
  setProctoring,
  webcamVideoRef,
  webcamStream,
  screenStream
}) {
  const [modal, setModal] = useState(null)
  const lastViolationAtRef = useRef(0)
  const faceMissingSinceRef = useRef(null)
  const devtoolsOpenRef = useRef(false)
  const detectingRef = useRef(false)
  const modelRetriesRef = useRef(0)
  const faceModelsLoadedRef = useRef(false)
  const objectModelRef = useRef(null)
  const lastMousePosRef = useRef({ x: 0, y: 0, time: Date.now() })
  const lastSubmitTimeRef = useRef(0)
  const lookingAwaySinceRef = useRef(null)
  const headTurnSinceRef = useRef(null)

  const requestFullscreen = useCallback(async () => {
    const el = document.documentElement
    if (document.fullscreenElement || document.webkitFullscreenElement) return true
    if (!el.requestFullscreen && !el.webkitRequestFullscreen) return true
    try {
      if (el.requestFullscreen) {
        await el.requestFullscreen()
      } else if (el.webkitRequestFullscreen) {
        el.webkitRequestFullscreen()
      }
      return true
    } catch {
      return false
    }
  }, [])

  const terminate = useCallback((reason, nextState) => {
    setModal({ type: 'terminated', reason })
    setState((current) => ({ ...current, stage: 'terminated' }))
    window.setTimeout(() => navigate('/terminated', { replace: true }), 1200)
    return {
      ...nextState,
      assessmentStatus: 'Terminated Due To Malpractice',
      terminatedReason: reason
    }
  }, [navigate, setState])

  const registerViolation = useCallback((kind, reason) => {
    const now = Date.now()
    if (now - lastViolationAtRef.current < COOLDOWN_MS) return
    lastViolationAtRef.current = now

    const timestamp = new Date().toISOString()
    const label = violationLabels[kind] || reason
    const snapshotImage = captureFrame(webcamVideoRef?.current)
    const event = { time: nowLabel(new Date(timestamp)), event: label, reason, round }
    const violation = { timestamp, kind, reason, round }
    const snapshot = snapshotImage ? { timestamp, reason, image: snapshotImage } : null

    setProctoring((current) => {
      const nextWarnings = current.warnings + 1
      const penalty = VIOLATION_PENALTIES[kind] ?? 10
      const nextIntegrity = Math.max(0, current.integrityScore - penalty)
      const baseState = {
        ...current,
        warnings: nextWarnings,
        integrityScore: nextIntegrity,
        logs: [...current.logs, event],
        violations: [...current.violations, violation],
        snapshots: snapshot ? [...current.snapshots.slice(-4), snapshot] : current.snapshots
      }
      const nextState = nextWarnings > 3
        ? terminate('Repeated malpractice detected.', baseState)
        : baseState

      if (nextWarnings <= 3) {
        setModal({ type: 'warning', warning: nextWarnings, reason })
      }

      postQuietly('/proctoring/violation', {
        session_id: sessionId,
        violation,
        warnings: nextState.warnings,
        integrity_score: nextState.integrityScore,
        assessment_status: nextState.assessmentStatus
      })
      if (snapshot) {
        postQuietly('/proctoring/snapshot', { session_id: sessionId, snapshot })
      }
      return nextState
    })
  }, [round, sessionId, setProctoring, terminate, webcamVideoRef])

  useEffect(() => {
    setProctoring((current) => ({
      ...current,
      currentRound: active ? round : current.currentRound,
      cameraActive: Boolean(webcamStream?.getVideoTracks?.().some((track) => track.readyState === 'live')),
      screenShareActive: Boolean(screenStream?.getVideoTracks?.().some((track) => track.readyState === 'live')),
      faceDetectionActive: Boolean(active && webcamStream)
    }))
  }, [active, round, screenStream, setProctoring, webcamStream])

  useEffect(() => {
    if (!active) return undefined
    requestFullscreen()

    const onVisibility = () => {
      if (document.hidden) registerViolation('tab_switch', 'You switched away from the assessment window.')
    }
    const onBlur = () => {
      if (!document.hidden) registerViolation('tab_switch', 'Window focus was lost during the assessment.')
    }
    const onFullscreen = () => {
      const isFs = document.fullscreenElement || document.webkitFullscreenElement
      if (!isFs) registerViolation('fullscreen_exit', 'Fullscreen exited.')
    }
    const onFullscreenError = () => {
      // Fullscreen request failed — do not penalize, just log
    }
    const onClipboard = (event) => {
      event.preventDefault()
      registerViolation('copy_paste', 'Copy/Paste activity detected.')
    }
    const onContextMenu = (event) => {
      event.preventDefault()
      registerViolation('right_click', 'Right click is disabled during assessment.')
    }
    const onKeyDown = (event) => {
      const key = event.key.toLowerCase()
      const isMeta = event.metaKey || event.ctrlKey
      const blockedMeta = isMeta && ['c', 'v', 'x', 'a', 's', 'p', 'u'].includes(key)
      const blockedDevTools = event.key === 'F12' || (isMeta && event.shiftKey && ['i', 'j', 'c'].includes(key))
      if (!blockedMeta && !blockedDevTools) return
      event.preventDefault()
      registerViolation(blockedDevTools ? 'devtools' : 'shortcut', blockedDevTools ? 'Developer tools attempt detected.' : 'Restricted keyboard shortcut detected.')
    }

    document.addEventListener('visibilitychange', onVisibility)
    document.addEventListener('fullscreenchange', onFullscreen)
    document.addEventListener('fullscreenerror', onFullscreenError)
    document.addEventListener('copy', onClipboard)
    document.addEventListener('paste', onClipboard)
    document.addEventListener('cut', onClipboard)
    document.addEventListener('contextmenu', onContextMenu)
    window.addEventListener('blur', onBlur)
    window.addEventListener('keydown', onKeyDown, true)

    const devtoolsTimer = window.setInterval(() => {
      const open = window.outerWidth - window.innerWidth > DEVTOOLS_THRESHOLD || window.outerHeight - window.innerHeight > DEVTOOLS_THRESHOLD
      if (open && !devtoolsOpenRef.current) registerViolation('devtools', 'Developer tools attempt detected.')
      devtoolsOpenRef.current = open
    }, 1500)

    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      document.removeEventListener('fullscreenchange', onFullscreen)
      document.removeEventListener('fullscreenerror', onFullscreenError)
      document.removeEventListener('copy', onClipboard)
      document.removeEventListener('paste', onClipboard)
      document.removeEventListener('cut', onClipboard)
      document.removeEventListener('contextmenu', onContextMenu)
      window.removeEventListener('blur', onBlur)
      window.removeEventListener('keydown', onKeyDown, true)
      window.clearInterval(devtoolsTimer)
    }
  }, [active, registerViolation, requestFullscreen])

  useEffect(() => {
    if (!active || !screenStream) return undefined
    const tracks = screenStream.getVideoTracks()
    const onEnded = () => registerViolation('screen_share_stop', 'Screen sharing stopped.')
    tracks.forEach((track) => track.addEventListener('ended', onEnded))
    return () => tracks.forEach((track) => track.removeEventListener('ended', onEnded))
  }, [active, registerViolation, screenStream])

  useEffect(() => {
    if (!active) return undefined
    let mouseTimeout = null

    const onMouseMove = (e) => {
      const now = Date.now()
      const dx = Math.abs(e.clientX - lastMousePosRef.current.x)
      const dy = Math.abs(e.clientY - lastMousePosRef.current.y)
      const dt = now - lastMousePosRef.current.time
      if (dx > 5 || dy > 5) {
        lastMousePosRef.current = { x: e.clientX, y: e.clientY, time: now }
        if (mouseTimeout) { clearTimeout(mouseTimeout); mouseTimeout = null }
      }
    }

    mouseTimeout = window.setTimeout(() => {
      registerViolation('mouse_stationary', 'No mouse movement for extended period.')
    }, 120000)

    const onMouse = () => {
      if (mouseTimeout) { clearTimeout(mouseTimeout); mouseTimeout = null }
      mouseTimeout = window.setTimeout(() => {
        registerViolation('mouse_stationary', 'No mouse movement for extended period.')
      }, 120000)
    }

    document.addEventListener('mousemove', onMouseMove)
    document.addEventListener('mousedown', onMouse)
    document.addEventListener('keydown', onMouse)

    return () => {
      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mousedown', onMouse)
      document.removeEventListener('keydown', onMouse)
      if (mouseTimeout) clearTimeout(mouseTimeout)
    }
  }, [active, registerViolation])

  useEffect(() => {
    if (!active || !webcamStream) return undefined
    let audioContext = null
    let analyser = null
    let audioTimeout = null
    let cancelled = false

    const startAudioDetection = async () => {
      try {
        audioContext = new (window.AudioContext || window.webkitAudioContext)()
        const source = audioContext.createMediaStreamSource(webcamStream)
        analyser = audioContext.createAnalyser()
        analyser.fftSize = 512
        source.connect(analyser)

        const dataArray = new Uint8Array(analyser.frequencyBinCount)
        let voiceActiveSince = null

        const checkAudio = () => {
          if (cancelled) return
          analyser.getByteFrequencyData(dataArray)
          let sum = 0
          for (let i = 0; i < dataArray.length; i++) sum += dataArray[i]
          const average = sum / dataArray.length

          if (average > 15) {
            if (voiceActiveSince === null) {
              voiceActiveSince = Date.now()
            } else if (Date.now() - voiceActiveSince > 5000) {
              registerViolation('background_voice', 'Sustained background voice detected.')
              voiceActiveSince = null
            }
          } else {
            voiceActiveSince = null
          }
          audioTimeout = window.setTimeout(checkAudio, 1000)
        }
        checkAudio()
      } catch {
        // AudioContext not available
      }
    }

    startAudioDetection()

    return () => {
      cancelled = true
      if (audioTimeout) clearTimeout(audioTimeout)
      if (audioContext) {
        try { audioContext.close() } catch { /* ignore */ }
      }
    }
  }, [active, registerViolation, webcamStream])

  useEffect(() => {
    if (!active || !webcamVideoRef?.current) return undefined
    let cancelled = false

    const loadModels = async (retryCount = 0) => {
      if (faceModelsLoadedRef.current) return true
      try {
        await Promise.all([
          faceapi.nets.tinyFaceDetector.loadFromUri('/models'),
          faceapi.nets.faceLandmark68Net.loadFromUri('/models')
        ])
        faceModelsLoadedRef.current = true
        modelRetriesRef.current = 0
        return true
      } catch (err) {
        console.error('Failed to load face-api models', err)
        if (retryCount < MODEL_MAX_RETRIES && !cancelled) {
          await new Promise((r) => setTimeout(r, MODEL_RETRY_DELAY_MS))
          return loadModels(retryCount + 1)
        }
        return false
      }
    }

    const loadObjectModel = async () => {
      if (objectModelRef.current) return objectModelRef.current
      try {
        if (!window.objectModel) {
          const tf = await import('@tensorflow/tfjs')
          await tf.ready()
          const cocoSsd = await import('@tensorflow-models/coco-ssd')
          window.objectModel = await cocoSsd.load()
        }
        objectModelRef.current = window.objectModel
        return objectModelRef.current
      } catch (err) {
        console.error('Failed to load object model', err)
        return null
      }
    }

    const init = async () => {
      await Promise.all([loadModels(), loadObjectModel()])
    }
    init()

    const monitor = async () => {
      if (cancelled || detectingRef.current) return
      detectingRef.current = true
      const video = webcamVideoRef.current
      try {
        if (objectModelRef.current && video?.readyState >= 2) {
          const detections = await objectModelRef.current.detect(video, 20, 0.15)
          if (detections?.length) {
            const suspicious = detections.filter((d) => ['cell phone', 'laptop', 'tv', 'remote'].includes(d.class))
            if (suspicious.length > 0) {
              registerViolation('suspicious_object', `Suspicious object detected: ${suspicious[0].class}`)
            }
          }
        }

        if (faceModelsLoadedRef.current && video?.readyState >= 2) {
          const detections = await faceapi.detectAllFaces(video, new faceapi.TinyFaceDetectorOptions({ inputSize: 160, scoreThreshold: 0.3 })).withFaceLandmarks()
          if (detections.length > 1) {
            registerViolation('multiple_faces', 'Multiple faces detected.')
          } else if (detections.length === 0) {
            if (faceMissingSinceRef.current === null) {
              faceMissingSinceRef.current = Date.now()
            } else if (Date.now() - faceMissingSinceRef.current > NO_FACE_LIMIT_MS) {
              registerViolation('no_face', 'No face detected.')
              faceMissingSinceRef.current = null
            }
          } else {
            faceMissingSinceRef.current = null
            const face = detections[0]
            const { width, height, x, y } = face.detection.box
            const marginX = video.videoWidth * 0.02
            const marginY = video.videoHeight * 0.02
            if (x < -marginX || y < -marginY || x + width > video.videoWidth + marginX || y + height > video.videoHeight + marginY) {
              registerViolation('half_face', 'Partial face detected.')
            }

            const landmarks = face.landmarks
            if (landmarks) {
              const positions = landmarks.positions
              const noseTip = positions[30]
              const leftEye = positions[36]
              const rightEye = positions[45]
              const chin = positions[8]
              const forehead = positions[19]

              const eyeCenter = {
                x: (leftEye.x + rightEye.x) / 2,
                y: (leftEye.y + rightEye.y) / 2
              }
              const horizontalRatio = (noseTip.x - eyeCenter.x) / width
              if (Math.abs(horizontalRatio) > 0.18) {
                if (headTurnSinceRef.current === null) {
                  headTurnSinceRef.current = Date.now()
                } else if (Date.now() - headTurnSinceRef.current > 3000) {
                  registerViolation('head_turn', 'Head turned away from camera.')
                  headTurnSinceRef.current = null
                }
              } else {
                headTurnSinceRef.current = null
              }

              const verticalRatio = (noseTip.y - forehead.y) / (chin.y - forehead.y)
              if (verticalRatio < 0.35 || verticalRatio > 0.65) {
                if (lookingAwaySinceRef.current === null) {
                  lookingAwaySinceRef.current = Date.now()
                } else if (Date.now() - lookingAwaySinceRef.current > 4000) {
                  registerViolation('looking_away', 'Looking away from screen.')
                  lookingAwaySinceRef.current = null
                }
              } else {
                lookingAwaySinceRef.current = null
              }
            }
          }
          return
        }

        if (!hasVisibleFrame(video)) {
          registerViolation('face_missing', 'Candidate not visible.')
        }
      } catch {
        // Detection error — will retry on next interval
      } finally {
        detectingRef.current = false
      }
    }

    const timer = window.setInterval(monitor, FACE_DETECT_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [active, registerViolation, webcamVideoRef])

  return {
    modal,
    dismissModal: () => setModal(null),
    requestFullscreen,
    registerViolation,
    status: proctoring
  }
}
