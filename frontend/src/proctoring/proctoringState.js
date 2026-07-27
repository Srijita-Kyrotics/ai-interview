import { useEffect, useState } from 'react'

export const PROCTORING_STORAGE_KEY = 'mockRecruitmentProctoring'

export const VIOLATION_PENALTIES = {
  tab_switch: 10,
  fullscreen_exit: 10,
  screen_share_stop: 15,
  no_face: 15,
  face_missing: 15,
  multiple_faces: 20,
  copy_paste: 15,
  devtools: 20,
  right_click: 0,
  shortcut: 0,
  half_face: 15,
  looking_away: 5,
  head_turn: 5,
  background_voice: 10,
  mouse_stationary: 5,
  rapid_submit: 10,
  suspicious_object: 15
}

const SCORE_WEIGHTS = {
  baseCommunication: 60,
  baseConfidence: 55,
  voiceMultiplier: 1.6,
  confidenceVoiceMultiplier: 1.2,
  questionTimeThreshold: 180,
  questionTimePenaltyDivisor: 12,
  answeredBonus: 4,
  minCommunication: 40,
  minConfidence: 35,
  maxScore: 100,
  minAnswerLength: 10,
}

export const defaultProctoringState = {
  warnings: 0,
  integrityScore: 100,
  logs: [],
  violations: [],
  snapshots: [],
  assessmentStatus: 'Passed Proctoring',
  terminatedReason: '',
  cameraActive: false,
  screenShareActive: false,
  faceDetectionActive: false,
  currentRound: '',
  timeSpent: {},
  interviewMetrics: {
    technical: { questionTimes: [], voiceDurations: [], submissions: [] },
    hr: { questionTimes: [], voiceDurations: [], submissions: [] }
  }
}

function deepMerge(defaults, stored) {
  if (!stored || typeof stored !== 'object') return { ...defaults }
  const result = { ...defaults }
  for (const key of Object.keys(stored)) {
    if (stored[key] === undefined) continue
    if (
      defaults[key] &&
      typeof defaults[key] === 'object' &&
      !Array.isArray(defaults[key]) &&
      typeof stored[key] === 'object' &&
      !Array.isArray(stored[key])
    ) {
      result[key] = deepMerge(defaults[key], stored[key])
    } else {
      result[key] = stored[key]
    }
  }
  return result
}

function createDefault() {
  return deepMerge(defaultProctoringState, null)
}

export function loadProctoringState() {
  try {
    const stored = localStorage.getItem(PROCTORING_STORAGE_KEY)
    return stored ? deepMerge(defaultProctoringState, JSON.parse(stored)) : createDefault()
  } catch {
    try { localStorage.removeItem(PROCTORING_STORAGE_KEY) } catch { /* quota */ }
    return createDefault()
  }
}

export function resetProctoringState() {
  try { localStorage.removeItem(PROCTORING_STORAGE_KEY) } catch { /* quota */ }
  return createDefault()
}

export function usePersistentProctoring() {
  const [proctoring, setProctoring] = useState(loadProctoringState)

  useEffect(() => {
    try {
      const serializable = {
        ...proctoring,
        snapshots: proctoring.snapshots.slice(-5)
      }
      localStorage.setItem(PROCTORING_STORAGE_KEY, JSON.stringify(serializable))
    } catch {
      // localStorage quota exceeded — discard oldest snapshots and retry
      try {
        const reduced = { ...proctoring, snapshots: [] }
        localStorage.setItem(PROCTORING_STORAGE_KEY, JSON.stringify(reduced))
      } catch {
        // Still failing — clear everything and start fresh
        try { localStorage.removeItem(PROCTORING_STORAGE_KEY) } catch { /* ignore */ }
      }
    }
  }, [proctoring])

  return [proctoring, setProctoring]
}

export function calculateInterviewScores(metrics = {}) {
  const rounds = ['technical', 'hr']
  const questionTimes = rounds.flatMap((round) => metrics[round]?.questionTimes || [])
  const voiceDurations = rounds.flatMap((round) => metrics[round]?.voiceDurations || [])
  const submissions = rounds.flatMap((round) => metrics[round]?.submissions || [])
  const averageVoice = voiceDurations.length
    ? voiceDurations.reduce((sum, value) => sum + value, 0) / voiceDurations.length
    : 0
  const averageQuestionTime = questionTimes.length
    ? questionTimes.reduce((sum, value) => sum + value, 0) / questionTimes.length
    : 0
  const answered = submissions.filter((item) => item.answerLength > SCORE_WEIGHTS.minAnswerLength || item.hasVoice).length
  const communicationScore = Math.max(SCORE_WEIGHTS.minCommunication, Math.min(SCORE_WEIGHTS.maxScore, Math.round(SCORE_WEIGHTS.baseCommunication + averageVoice * SCORE_WEIGHTS.voiceMultiplier + answered * SCORE_WEIGHTS.answeredBonus)))
  const confidenceScore = Math.max(SCORE_WEIGHTS.minConfidence, Math.min(SCORE_WEIGHTS.maxScore, Math.round(SCORE_WEIGHTS.baseConfidence + averageVoice * SCORE_WEIGHTS.confidenceVoiceMultiplier - Math.max(0, averageQuestionTime - SCORE_WEIGHTS.questionTimeThreshold) / SCORE_WEIGHTS.questionTimePenaltyDivisor)))
  const participationScore = submissions.length
    ? Math.round((answered / submissions.length) * 100)
    : 0

  return { communicationScore, confidenceScore, participationScore }
}
