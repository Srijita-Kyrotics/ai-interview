const API = import.meta.env.VITE_API_URL || '/api'

function getAuthToken() {
  try {
    const stored = localStorage.getItem('mockRecruitmentUser')
    if (stored) {
      const user = JSON.parse(stored)
      return user?.token || ''
    }
  } catch (_e) {
    return ''
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
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    let data = null
    try { data = JSON.parse(text) } catch (_) { /* not JSON */ }
    const msg = data?.detail || data?.message || text || `Request failed (${res.status})`
    const err = new Error(msg)
    err.status = res.status
    throw err
  }
  return res.json()
}

const api = {
  get: (path) => request('GET', path),
  post: (path, body, isForm = false) => request('POST', path, body, isForm)
}

export { API, getAuthToken, api }
