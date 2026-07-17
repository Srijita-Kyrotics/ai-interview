const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

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

const api = {
  get: async (path) => {
    const token = getAuthToken()
    const headers = token ? { 'Authorization': `Bearer ${token}` } : {}
    return (await fetch(`${API}${path}`, { headers })).json()
  },
  post: async (path, body, isForm = false) => {
    const token = getAuthToken()
    const headers = isForm ? {} : { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`
    return (await fetch(`${API}${path}`, {
      method: 'POST',
      headers,
      body: isForm ? body : JSON.stringify(body)
    })).json()
  }
}

export { API, getAuthToken, api }
