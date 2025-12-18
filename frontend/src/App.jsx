import { useCallback, useEffect, useMemo, useState } from 'react'
import Sidebar from './components/Sidebar'
import Chat from './components/Chat'
import { getDefaultApiBaseUrl } from './api'

const LS_KEY = 'db_chatbot_gemini_api_base_url'
const LS_THEME_KEY = 'db_chatbot_gemini_theme'

function getInitialTheme() {
  try {
    const saved = localStorage.getItem(LS_THEME_KEY)
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    // ignore
  }

  try {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export default function App() {
  const defaultBase = useMemo(() => getDefaultApiBaseUrl(), [])
  const [apiBaseUrl, setApiBaseUrl] = useState(() => {
    const saved = localStorage.getItem(LS_KEY)
    return saved || defaultBase
  })

  const [theme, setTheme] = useState(() => getInitialTheme())

  useEffect(() => {
    localStorage.setItem(LS_KEY, apiBaseUrl)
  }, [apiBaseUrl])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try {
      localStorage.setItem(LS_THEME_KEY, theme)
    } catch {
      // ignore
    }
  }, [theme])

  const toggleTheme = useCallback(() => {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'))
  }, [])

  return (
    <div className="appShell">
      <Sidebar apiBaseUrl={apiBaseUrl} setApiBaseUrl={setApiBaseUrl} />
      <main className="main">
        <header className="topbar">
          <div className="topbarTitle">
            <div className="h1">SQLGenie</div>
            <div className="sub">Ask questions in natural language, run safe read-only SQL.</div>
          </div>

          <div className="topbarActions">
            <button className="btn btnGhost" type="button" onClick={toggleTheme} aria-pressed={theme === 'dark'}>
              {theme === 'dark' ? 'Light mode' : 'Dark mode'}
            </button>
          </div>
        </header>
        <Chat apiBaseUrl={apiBaseUrl} />
      </main>
    </div>
  )
}
