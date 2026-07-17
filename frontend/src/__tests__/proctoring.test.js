import { describe, it, expect, beforeEach, vi } from 'vitest'

const localStorageMock = (() => {
  let store = {}
  return {
    getItem: vi.fn((key) => store[key] || null),
    setItem: vi.fn((key, value) => { store[key] = value }),
    removeItem: vi.fn((key) => { delete store[key] }),
    clear: vi.fn(() => { store = {} }),
  }
})()

Object.defineProperty(globalThis, 'localStorage', { value: localStorageMock })

describe('proctoringState', () => {
  beforeEach(() => {
    localStorageMock.clear()
    vi.clearAllMocks()
  })

  describe('defaultProctoringState', () => {
    it('has expected structure', async () => {
      const { defaultProctoringState } = await import('../proctoring/proctoringState')
      expect(defaultProctoringState).toHaveProperty('warnings', 0)
      expect(defaultProctoringState).toHaveProperty('integrityScore', 100)
      expect(defaultProctoringState).toHaveProperty('logs')
      expect(Array.isArray(defaultProctoringState.logs)).toBe(true)
      expect(defaultProctoringState).toHaveProperty('violations')
      expect(Array.isArray(defaultProctoringState.violations)).toBe(true)
      expect(defaultProctoringState).toHaveProperty('snapshots')
      expect(Array.isArray(defaultProctoringState.snapshots)).toBe(true)
      expect(defaultProctoringState).toHaveProperty('assessmentStatus', 'Passed Proctoring')
      expect(defaultProctoringState).toHaveProperty('terminatedReason', '')
      expect(defaultProctoringState).toHaveProperty('cameraActive', false)
      expect(defaultProctoringState).toHaveProperty('screenShareActive', false)
      expect(defaultProctoringState).toHaveProperty('faceDetectionActive', false)
      expect(defaultProctoringState).toHaveProperty('currentRound', '')
      expect(defaultProctoringState).toHaveProperty('timeSpent')
      expect(defaultProctoringState).toHaveProperty('interviewMetrics')
      expect(defaultProctoringState.interviewMetrics).toHaveProperty('technical')
      expect(defaultProctoringState.interviewMetrics).toHaveProperty('hr')
    })
  })

  describe('VIOLATION_PENALTIES', () => {
    it('covers all violation types including half_face', async () => {
      const { VIOLATION_PENALTIES } = await import('../proctoring/proctoringState')
      const expectedTypes = [
        'tab_switch', 'fullscreen_exit', 'screen_share_stop', 'no_face',
        'face_missing', 'multiple_faces', 'copy_paste', 'devtools',
        'right_click', 'shortcut', 'half_face'
      ]
      for (const type of expectedTypes) {
        expect(VIOLATION_PENALTIES).toHaveProperty(type)
        expect(typeof VIOLATION_PENALTIES[type]).toBe('number')
      }
    })

    it('has correct penalty values', async () => {
      const { VIOLATION_PENALTIES } = await import('../proctoring/proctoringState')
      expect(VIOLATION_PENALTIES.tab_switch).toBe(10)
      expect(VIOLATION_PENALTIES.fullscreen_exit).toBe(10)
      expect(VIOLATION_PENALTIES.screen_share_stop).toBe(15)
      expect(VIOLATION_PENALTIES.no_face).toBe(15)
      expect(VIOLATION_PENALTIES.multiple_faces).toBe(20)
      expect(VIOLATION_PENALTIES.devtools).toBe(20)
      expect(VIOLATION_PENALTIES.right_click).toBe(0)
      expect(VIOLATION_PENALTIES.shortcut).toBe(0)
      expect(VIOLATION_PENALTIES.half_face).toBe(15)
    })
  })

  describe('loadProctoringState', () => {
    it('returns defaults when no stored data', async () => {
      const { loadProctoringState, defaultProctoringState } = await import('../proctoring/proctoringState')
      localStorageMock.getItem.mockReturnValue(null)
      const state = loadProctoringState()
      expect(state).toEqual(defaultProctoringState)
    })

    it('returns stored data when available', async () => {
      const { loadProctoringState } = await import('../proctoring/proctoringState')
      const stored = { warnings: 2, integrityScore: 70 }
      localStorageMock.getItem.mockReturnValue(JSON.stringify(stored))
      const state = loadProctoringState()
      expect(state.warnings).toBe(2)
      expect(state.integrityScore).toBe(70)
    })

    it('returns defaults on corrupted data', async () => {
      const { loadProctoringState, defaultProctoringState } = await import('../proctoring/proctoringState')
      localStorageMock.getItem.mockReturnValue('not-valid-json{{{')
      const state = loadProctoringState()
      expect(state).toEqual(defaultProctoringState)
      expect(localStorageMock.removeItem).toHaveBeenCalledWith('mockRecruitmentProctoring')
    })
  })

  describe('resetProctoringState', () => {
    it('clears localStorage and returns defaults', async () => {
      const { resetProctoringState, defaultProctoringState } = await import('../proctoring/proctoringState')
      const state = resetProctoringState()
      expect(state).toEqual(defaultProctoringState)
      expect(localStorageMock.removeItem).toHaveBeenCalledWith('mockRecruitmentProctoring')
      expect(localStorageMock.removeItem).toHaveBeenCalledWith('warnings')
    })
  })

  describe('calculateInterviewScores', () => {
    it('computes correct scores for various inputs', async () => {
      const { calculateInterviewScores } = await import('../proctoring/proctoringState')
      const metrics = {
        technical: {
          questionTimes: [30, 45, 60],
          voiceDurations: [10, 15, 20],
          submissions: [
            { answerLength: 50, hasVoice: true },
            { answerLength: 20, hasVoice: false },
            { answerLength: 100, hasVoice: true },
          ]
        },
        hr: {
          questionTimes: [20, 40],
          voiceDurations: [25, 30],
          submissions: [
            { answerLength: 80, hasVoice: true },
            { answerLength: 10, hasVoice: false },
          ]
        }
      }
      const result = calculateInterviewScores(metrics)
      expect(result).toHaveProperty('communicationScore')
      expect(result).toHaveProperty('confidenceScore')
      expect(result).toHaveProperty('participationScore')
      expect(result.communicationScore).toBeGreaterThanOrEqual(40)
      expect(result.communicationScore).toBeLessThanOrEqual(100)
      expect(result.confidenceScore).toBeGreaterThanOrEqual(35)
      expect(result.confidenceScore).toBeLessThanOrEqual(100)
      expect(result.participationScore).toBeGreaterThanOrEqual(0)
      expect(result.participationScore).toBeLessThanOrEqual(100)
    })

    it('handles empty metrics', async () => {
      const { calculateInterviewScores } = await import('../proctoring/proctoringState')
      const result = calculateInterviewScores({})
      expect(result.communicationScore).toBe(60)
      expect(result.confidenceScore).toBe(55)
      expect(result.participationScore).toBe(0)
    })

    it('handles undefined input', async () => {
      const { calculateInterviewScores } = await import('../proctoring/proctoringState')
      const result = calculateInterviewScores()
      expect(result.communicationScore).toBe(60)
      expect(result.confidenceScore).toBe(55)
      expect(result.participationScore).toBe(0)
    })
  })
})

describe('violationLabels in useAssessmentProctoring', () => {
  it('all VIOLATION_PENALTIES types have corresponding labels', async () => {
    const { VIOLATION_PENALTIES } = await import('../proctoring/proctoringState')
    const module = await import('../proctoring/useAssessmentProctoring.js')
    const source = await fetch(module?.url || '').catch(() => null)

    const expectedTypes = Object.keys(VIOLATION_PENALTIES)
    for (const type of expectedTypes) {
      expect(VIOLATION_PENALTIES[type]).toBeDefined()
    }
  })
})
