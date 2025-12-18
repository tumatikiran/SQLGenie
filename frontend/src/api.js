function normalizeBaseUrl(baseUrl) {
  const v = (baseUrl || '').trim()
  if (!v) return ''
  return v.endsWith('/') ? v.slice(0, -1) : v
}

export function getDefaultApiBaseUrl() {
  const envUrl = import.meta.env.VITE_API_BASE_URL
  return normalizeBaseUrl(envUrl || 'http://localhost:8000')
}

async function readError(res) {
  const ct = res.headers.get('content-type') || ''
  if (ct.includes('application/json')) {
    const j = await res.json().catch(() => null)
    if (j && typeof j.detail === 'string') return j.detail
  }
  return `${res.status} ${res.statusText}`
}

export async function fetchTables(apiBaseUrl) {
  const base = normalizeBaseUrl(apiBaseUrl)
  const res = await fetch(`${base}/tables`)
  if (!res.ok) throw new Error(await readError(res))
  const data = await res.json()
  return Array.isArray(data.tables) ? data.tables : []
}

export async function fetchSchema(apiBaseUrl) {
  const base = normalizeBaseUrl(apiBaseUrl)
  const res = await fetch(`${base}/schema`)
  if (!res.ok) throw new Error(await readError(res))
  const data = await res.json()
  return Array.isArray(data.tables) ? data.tables : []
}

export async function chat(apiBaseUrl, question) {
  const base = normalizeBaseUrl(apiBaseUrl)
  const res = await fetch(`${base}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question })
  })
  if (!res.ok) throw new Error(await readError(res))
  return await res.json()
}
