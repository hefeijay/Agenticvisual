const BASE = '/api'

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(body.detail || res.statusText)
  }
  return res.json()
}

// ---------- health ----------
export const health = () => req('/health')

// ---------- files ----------
export function uploadCSV(file, onProgress) {
  const form = new FormData()
  form.append('file', file)
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE}/files/upload`)
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText))
      else reject(new Error(JSON.parse(xhr.responseText)?.detail || xhr.statusText))
    }
    xhr.onerror = () => reject(new Error('Upload failed'))
    if (onProgress) xhr.upload.onprogress = onProgress
    xhr.send(form)
  })
}

// ---------- sessions ----------
export const listSessions = () => req('/sessions')

export const createSession = (body) =>
  req('/sessions', { method: 'POST', body: JSON.stringify(body) })

export const getSession = (id) => req(`/sessions/${id}`)

export const deleteSession = (id) => req(`/sessions/${id}`, { method: 'DELETE' })

// ---------- session actions ----------
export const resetView = (id) => req(`/sessions/${id}/reset`, { method: 'POST' })

export const exportSession = (id) => {
  window.open(`${BASE}/sessions/${id}/export`, '_blank')
}

// ---------- SSE query stream ----------
/**
 * Submit a query and stream SSE events.
 * @param {string} sessionId
 * @param {string} query
 * @param {string} runMode  'cooperative' | 'autonomous'
 * @param {(event: {event: string, data: any}) => void} onEvent
 * @returns {() => void}  cancel function
 */
export function streamQuery(sessionId, query, runMode, onEvent) {
  let cancelled = false
  let controller = new AbortController()

  ;(async () => {
    let res
    try {
      res = await fetch(`${BASE}/sessions/${sessionId}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, run_mode: runMode }),
        signal: controller.signal,
      })
    } catch (err) {
      if (!cancelled) onEvent({ event: 'error', data: { message: err.message } })
      return
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      onEvent({ event: 'error', data: { message: body.detail || res.statusText } })
      return
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (!cancelled) {
      let chunk
      try {
        chunk = await reader.read()
      } catch {
        break
      }
      if (chunk.done) break
      buffer += decoder.decode(chunk.value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const raw = line.slice(6).trim()
        if (!raw || raw === '[DONE]') continue
        try {
          const msg = JSON.parse(raw)
          if (msg.event !== 'ping') onEvent(msg)
        } catch {
          // ignore malformed
        }
      }
    }
  })()

  return () => {
    cancelled = true
    controller.abort()
  }
}
