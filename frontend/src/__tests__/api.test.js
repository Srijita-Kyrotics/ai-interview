import { describe, it, expect, vi, beforeEach } from 'vitest'
import { getAuthToken, api } from '../api'

describe('getAuthToken', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('returns empty string when no stored user', () => {
    expect(getAuthToken()).toBe('')
  })

  it('returns token from stored user', () => {
    localStorage.setItem('mockRecruitmentUser', JSON.stringify({ token: 'abc123' }))
    expect(getAuthToken()).toBe('abc123')
  })

  it('returns empty string when stored data has no token', () => {
    localStorage.setItem('mockRecruitmentUser', JSON.stringify({ email: 'test@test.com' }))
    expect(getAuthToken()).toBe('')
  })

  it('returns empty string when stored data is invalid JSON', () => {
    localStorage.setItem('mockRecruitmentUser', 'not-json')
    expect(getAuthToken()).toBe('')
  })
})

describe('api.get', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('calls fetch with correct path', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ ok: true }),
    })
    vi.stubGlobal('fetch', mockFetch)

    await api.get('/test-endpoint')
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining('/test-endpoint'),
      expect.objectContaining({ headers: {} })
    )
  })

  it('includes Authorization header when token exists', async () => {
    localStorage.setItem('mockRecruitmentUser', JSON.stringify({ token: 'mytoken' }))
    const mockFetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ ok: true }),
    })
    vi.stubGlobal('fetch', mockFetch)

    await api.get('/protected')
    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: { Authorization: 'Bearer mytoken' },
      })
    )
  })
})

describe('api.post', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('sends JSON body by default', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ ok: true }),
    })
    vi.stubGlobal('fetch', mockFetch)

    await api.post('/submit', { answer: 'A' })
    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answer: 'A' }),
      })
    )
  })

  it('sends form data when isForm is true', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      json: () => Promise.resolve({ ok: true }),
    })
    vi.stubGlobal('fetch', mockFetch)

    const formData = new FormData()
    await api.post('/upload', formData, true)
    expect(mockFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        method: 'POST',
        body: formData,
      })
    )
  })
})
