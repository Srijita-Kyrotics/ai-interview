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
  half_face: 15
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

export function loadProctoringState() {
  try {
    const stored = localStorage.getItem(PROCTORING_STORAGE_KEY)
    return stored ? { ...defaultProctoringState, ...JSON.parse(stored) } : defaultProctoringState
  } catch {
    localStorage.removeItem(PROCTORING_STORAGE_KEY)
    return defaultProctoringState
  }
}

export function resetProctoringState() {
  localStorage.removeItem(PROCTORING_STORAGE_KEY)
  localStorage.removeItem('warnings')
  return defaultProctoringState
}

export function usePersistentProctoring() {
  const [proctoring, setProctoring] = useState(loadProctoringState)

  useEffect(() => {
    localStorage.setItem(PROCTORING_STORAGE_KEY, JSON.stringify(proctoring))
    localStorage.setItem('warnings', String(proctoring.warnings || 0))
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
  const answered = submissions.filter((item) => item.answerLength > 10 || item.hasVoice).length
  const communicationScore = Math.max(40, Math.min(100, Math.round(60 + averageVoice * 1.6 + answered * 4)))
  const confidenceScore = Math.max(35, Math.min(100, Math.round(55 + averageVoice * 1.2 - Math.max(0, averageQuestionTime - 180) / 12)))
  const participationScore = submissions.length
    ? Math.round((answered / submissions.length) * 100)
    : 0

  return { communicationScore, confidenceScore, participationScore }
}
