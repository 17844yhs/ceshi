const BASE = '/api'

async function request(path, options = {}) {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}))
    throw new Error(body.error || `HTTP ${resp.status}`)
  }
  return resp.json()
}

export const api = {
  health: () => request('/health'),
  detectSingle: (payload) => request('/detect', { method: 'POST', body: JSON.stringify(payload) }),
  batch: () => request('/batch', { method: 'POST' }),
  eval: () => request('/eval'),
}
