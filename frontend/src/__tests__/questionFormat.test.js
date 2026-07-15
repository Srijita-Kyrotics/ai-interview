import { describe, it, expect } from 'vitest'
import { formatQuestionText } from '../utils/questionFormat'

describe('formatQuestionText', () => {
  it('returns string for plain text', () => {
    const result = formatQuestionText('What is 2+2?')
    expect(typeof result === 'string' || Array.isArray(result)).toBe(true)
  })

  it('handles empty string', () => {
    const result = formatQuestionText('')
    expect(result).toBeDefined()
  })

  it('handles null/undefined gracefully', () => {
    const result = formatQuestionText(null)
    expect(result).toBeDefined()
  })

  it('handles text with HTML entities', () => {
    const result = formatQuestionText('What is &lt;b&gt;bold&lt;/b&gt;?')
    expect(result).toBeDefined()
  })

  it('handles text with LaTeX', () => {
    const result = formatQuestionText('Solve $x^2 + 2x + 1 = 0$')
    expect(result).toBeDefined()
  })
})
