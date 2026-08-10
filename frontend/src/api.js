const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

const AUTH_EVENT = 'auth:expired'

function getStoredUser() {
  try {
    const stored = localStorage.getItem('mockRecruitmentUser')
    return stored ? JSON.parse(stored) : null
  } catch (_e) {
    return null
  }
}

function getAuthToken() {
  const user = getStoredUser()
  return user?.token || ''
}

function decodeJwtPayload(token) {
  try {
    const [, payloadB64] = token.split('.')
    const normalized = payloadB64.replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(normalized))
  } catch (_e) {
    return null
  }
}

function isTokenExpired() {
  const user = getStoredUser()
  if (!user?.token) return false
  const payload = decodeJwtPayload(user.token)
  if (!payload || typeof payload.exp !== 'number') return false
  return payload.exp * 1000 < Date.now()
}

function clearStoredUser() {
  try {
    localStorage.removeItem('mockRecruitmentUser')
  } catch (_e) {
    /* ignore */
  }
  try {
    window.dispatchEvent(new CustomEvent(AUTH_EVENT))
  } catch (_e) {
    /* ignore */
  }
}

async function request(method, path, body, isForm = false) {
  const token = getAuthToken()
  const headers = isForm ? {} : { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${API}${path}`, {
    method,
    headers,
    body: isForm ? body : (body !== undefined ? JSON.stringify(body) : undefined)
  })

  let text = ''
  if (typeof res.text === 'function') {
    text = await res.text().catch(() => '')
  }

  let data = null
  if (text) {
    try { data = JSON.parse(text) } catch (_) { /* not JSON */ }
  } else if (typeof res.json === 'function') {
    try { data = await res.json().catch(() => null) } catch (_) { /* not JSON */ }
  }

  if (!res.ok) {
    const msg = data?.detail || data?.message || data?.error || text || `Request failed (${res.status})`
    if (res.status === 401) {
      clearStoredUser()
      const err = new Error(msg)
      err.status = res.status
      err.authRequired = true
      throw err
    }
    const err = new Error(msg)
    err.status = res.status
    throw err
  }

  if (data && typeof data === 'object') {
    return { ...data, ok: data.ok ?? true }
  }

  return { ok: true, data }
}

const api = {
  get: (path) => request('GET', path),
  post: (path, body, isForm = false) => request('POST', path, body, isForm)
}

export { API, getAuthToken, isTokenExpired, clearStoredUser, AUTH_EVENT, api }
