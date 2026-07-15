import { useCallback, useEffect, useRef, useState } from 'react'
import { VIOLATION_PENALTIES } from './proctoringState'
import * as faceapi from 'face-api.js'

const COOLDOWN_MS = 5000
const NO_FACE_LIMIT_MS = 2000
const DEVTOOLS_THRESHOLD = 160

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
  shortcut: 'Restricted Shortcut'
}

function nowLabel(date = new Date()) {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

async function postQuietly(path, body) {
  try {
    await fetch(`http://127.0.0.1:8000${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
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
  return canvas.toDataURL('image/jpeg', 0.76)
}

function hasVisibleFrame(video) {
  if (!video || video.readyState < 2 || !video.videoWidth || !video.videoHeight) return false
  const canvas = document.createElement('canvas')
  canvas.width = 80
  canvas.height = 60
  const context = canvas.getContext('2d', { willReadFrequently: true })
  context.drawImage(video, 0, 0, canvas.width, canvas.height)
  const data = context.getImageData(0, 0, canvas.width, canvas.height).data
  let litPixels = 0
  for (let i = 0; i < data.length; i += 16) {
    const brightness = (data[i] + data[i + 1] + data[i + 2]) / 3
    if (brightness > 28) litPixels += 1
  }
  return litPixels > 80
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

  const requestFullscreen = useCallback(async () => {
    if (document.fullscreenElement || !document.documentElement.requestFullscreen) return true
    try {
      await document.documentElement.requestFullscreen()
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
        snapshots: snapshot ? [...current.snapshots, snapshot] : current.snapshots
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
    const onBlur = () => registerViolation('tab_switch', 'Window focus was lost during the assessment.')
    const onFullscreen = () => {
      if (!document.fullscreenElement) registerViolation('fullscreen_exit', 'Fullscreen exited.')
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
      const blockedCtrl = event.ctrlKey && ['c', 'v', 'x', 'a', 's', 'p', 'u'].includes(key)
      const blockedDevTools = event.key === 'F12' || (event.ctrlKey && event.shiftKey && ['i', 'j', 'c'].includes(key))
      if (!blockedCtrl && !blockedDevTools) return
      event.preventDefault()
      registerViolation(blockedDevTools ? 'devtools' : 'shortcut', blockedDevTools ? 'Developer tools attempt detected.' : 'Restricted keyboard shortcut detected.')
    }

    document.addEventListener('visibilitychange', onVisibility)
    document.addEventListener('fullscreenchange', onFullscreen)
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
    if (!active || !webcamVideoRef?.current) return undefined
    let cancelled = false
    let faceModelsLoaded = false
    let objectModel = null

    const loadModels = async () => {
      try {
        await Promise.all([
          faceapi.nets.tinyFaceDetector.loadFromUri('/models'),
          faceapi.nets.faceLandmark68Net.loadFromUri('/models')
        ])
        faceModelsLoaded = true
      } catch (err) {
        console.error('Failed to load face-api models', err)
      }
      try {
        if (!window.objectModel) {
          const tf = await import('@tensorflow/tfjs')
          await tf.ready()
          const cocoSsd = await import('@tensorflow-models/coco-ssd')
          window.objectModel = await cocoSsd.load()
        }
        objectModel = window.objectModel
      } catch (err) {
        console.error('Failed to load object model', err)
      }
    }
    loadModels()

    const monitor = async () => {
      if (cancelled) return
      const video = webcamVideoRef.current
      try {
        if (objectModel && video?.readyState >= 2) {
          const predictions = await objectModel.detect(video, 20, 0.15)
        }

        if (faceModelsLoaded && video?.readyState >= 2) {
          const detections = await faceapi.detectAllFaces(video, new faceapi.TinyFaceDetectorOptions({ inputSize: 160, scoreThreshold: 0.3 })).withFaceLandmarks()
          if (detections.length > 1) {
            registerViolation('multiple_faces', 'Multiple faces detected.')
          } else if (detections.length === 0) {
            if (faceMissingSinceRef.current === null) faceMissingSinceRef.current = Date.now()
            else if (Date.now() - faceMissingSinceRef.current > NO_FACE_LIMIT_MS) {
              registerViolation('no_face', 'No face detected.')
            }
          } else {
            faceMissingSinceRef.current = null
            const face = detections[0]
            const { width, height, x, y } = face.detection.box
            
            if (x < -10 || y < -10 || x + width > video.videoWidth + 10 || y + height > video.videoHeight + 10) {
              registerViolation('half_face', 'Partial face detected.')
            }
          }
          return
        }

        if (!hasVisibleFrame(video)) {
          registerViolation('face_missing', 'Candidate not visible.')
        }
      } catch {
        // ignore
      }
    }

    const timer = window.setInterval(monitor, 300)
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
