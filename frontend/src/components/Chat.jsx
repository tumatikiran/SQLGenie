import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { chat as chatApi } from '../api'
import Message from './Message'

function uid() {
  return Math.random().toString(16).slice(2) + Date.now().toString(16)
}

const LS_CHAT_KEY = 'db_chatbot_gemini_chat_history_v1'

export default function Chat({ apiBaseUrl }) {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState(() => {
    try {
      const raw = localStorage.getItem(LS_CHAT_KEY)
      const parsed = raw ? JSON.parse(raw) : null
      return Array.isArray(parsed) ? parsed : []
    } catch {
      return []
    }
  })
  const [busy, setBusy] = useState(false)
  const endRef = useRef(null)

  useEffect(() => {
    try {
      localStorage.setItem(LS_CHAT_KEY, JSON.stringify(messages))
    } catch {
      // ignore write errors (e.g. storage full)
    }
  }, [messages])

  const scrollToBottom = useCallback(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [])

  const canSend = useMemo(() => !busy && input.trim().length > 0, [busy, input])

  const onClear = useCallback(() => {
    if (busy || messages.length === 0) return
    const ok = window.confirm('Clear chat history?')
    if (!ok) return
    setInput('')
    setMessages([])
    try {
      localStorage.removeItem(LS_CHAT_KEY)
    } catch {
      // ignore
    }
  }, [busy, messages.length])

  const onSend = useCallback(async () => {
    const q = input.trim()
    if (!q || busy) return

    setBusy(true)
    setInput('')

    const userMsg = { id: uid(), role: 'user', text: q }
    setMessages((prev) => [...prev, userMsg])

    try {
      const resp = await chatApi(apiBaseUrl, q)
      const assistantMsg = {
        id: uid(),
        role: 'assistant',
        text: 'Query executed successfully.',
        sql: resp.sql,
        columns: resp.columns,
        rows: resp.rows
      }
      setMessages((prev) => [...prev, assistantMsg])
    } catch (e) {
      const assistantMsg = {
        id: uid(),
        role: 'assistant',
        text: 'Request failed.',
        error: e?.message || String(e)
      }
      setMessages((prev) => [...prev, assistantMsg])
    } finally {
      setBusy(false)
      setTimeout(scrollToBottom, 50)
    }
  }, [apiBaseUrl, busy, input, scrollToBottom])

  const onKeyDown = useCallback(
    (e) => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault()
        onSend()
      }
    },
    [onSend]
  )

  return (
    <div className="chatWrap">
      <div className="chatHeader">
        <div className="chatHeaderTitle">Chat</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {busy ? <span className="badge">Running…</span> : null}
          <button className="btn btnGhost" type="button" onClick={onClear} disabled={busy || messages.length === 0}>
            Clear chat
          </button>
        </div>
      </div>

      <div className="chatHistory">
        {messages.length === 0 ? (
          <div className="emptyState">
            <div className="emptyTitle">Ask a question about your database</div>
            <div className="emptyHint">Tip: Press Ctrl+Enter to send.</div>
          </div>
        ) : null}

        {messages.map((m) => (
          <Message key={m.id} message={m} />
        ))}
        <div ref={endRef} />
      </div>

      <div className="composer">
        <textarea
          className="textarea"
          rows={3}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="e.g., Show top 10 customers by total order amount"
          disabled={busy}
        />

        <button className={`btn btnPrimary`} type="button" onClick={onSend} disabled={!canSend}>
          {busy ? 'Running…' : 'Send'}
        </button>
      </div>
    </div>
  )
}
