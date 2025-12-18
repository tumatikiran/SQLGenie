import { useCallback, useEffect, useMemo, useState } from 'react'
import { fetchSchema } from '../api'

function fullTableName(t) {
  return `${t.schema}.${t.name}`
}

function formatDataType(c) {
  const dt = String(c?.data_type || '')
  const lower = dt.toLowerCase()

  if (['varchar', 'nvarchar', 'char', 'nchar', 'varbinary', 'binary'].includes(lower)) {
    const ml = c?.max_length
    if (ml === -1) return `${dt}(MAX)`
    if (typeof ml === 'number') return `${dt}(${ml})`
    return dt
  }

  if (['decimal', 'numeric'].includes(lower)) {
    const p = c?.precision
    const s = c?.scale
    if (typeof p === 'number' && typeof s === 'number') return `${dt}(${p},${s})`
    return dt
  }

  return dt
}

export default function Sidebar({ apiBaseUrl, setApiBaseUrl }) {
  const [tables, setTables] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('')
  const [expanded, setExpanded] = useState(() => new Set())

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const t = await fetchSchema(apiBaseUrl)
      setTables(t)
    } catch (e) {
      setError(e?.message || String(e))
    } finally {
      setLoading(false)
    }
  }, [apiBaseUrl])

  useEffect(() => {
    let cancelled = false
    async function run() {
      setLoading(true)
      setError('')
      try {
        const t = await fetchSchema(apiBaseUrl)
        if (!cancelled) setTables(t)
      } catch (e) {
        if (!cancelled) setError(e?.message || String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    run()
    return () => {
      cancelled = true
    }
  }, [apiBaseUrl])

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase()
    if (!q) return tables

    return tables.filter((t) => {
      const name = fullTableName(t).toLowerCase()
      if (name.includes(q)) return true

      const cols = Array.isArray(t.columns) ? t.columns : []
      return cols.some((c) => {
        const cn = String(c?.name || '').toLowerCase()
        const ct = formatDataType(c).toLowerCase()
        return cn.includes(q) || ct.includes(q)
      })
    })
  }, [filter, tables])

  const toggle = useCallback((key) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  return (
    <aside className="sidebar">
      <div className="sidebarBrand">
        <div className="sidebarBrandTitle">Schema</div>
        <div className="badge">{loading ? 'Loading…' : `${tables.length} tables`}</div>
      </div>

      <div className="card cardInset">
        <div className="label">Backend API URL</div>
        <input
          className="input"
          value={apiBaseUrl}
          onChange={(e) => setApiBaseUrl(e.target.value)}
          placeholder="http://localhost:8000"
        />
        <div className="hint">Changing this reloads the schema.</div>
      </div>

      <div className="card cardInset" style={{ overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
          <div className="label" style={{ marginBottom: 0 }}>Tables</div>
          <button className="btn btnGhost" type="button" onClick={refresh} disabled={loading}>
            Refresh
          </button>
        </div>

        <div style={{ marginTop: 10 }}>
          <input
            className="input"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter tables / columns…"
          />
        </div>

        {error ? <div className="error">{error}</div> : null}

        <div className="schemaList">
          {filtered.map((t) => {
            const key = fullTableName(t)
            const isOpen = expanded.has(key)
            const cols = Array.isArray(t.columns) ? t.columns : []

            return (
              <div key={key} className="schemaTable">
                <div
                  className="schemaTableHeader"
                  role="button"
                  tabIndex={0}
                  onClick={() => toggle(key)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault()
                      toggle(key)
                    }
                  }}
                  title={key}
                >
                  <div className="schemaTableHeaderTop">
                    <div className="schemaTableTitle">
                      <span className="badge schemaSchemaBadge">{t.schema}</span>
                      <div className="schemaTableName" title={t.name}>{t.name}</div>
                    </div>

                    <div className="schemaTableTopRight">
                      <span className="badge badgeStrong">{cols.length} columns</span>
                      <span className="badge">{isOpen ? 'Hide' : 'Show'}</span>
                    </div>
                  </div>

                  <div className="schemaTableHeaderBottom">
                    <div className="schemaTableSub" title={key}>{key}</div>
                    <div className="schemaTableBadges">
                      <span className="badge">{t.type || 'TABLE'}</span>
                    </div>
                  </div>
                </div>

                {isOpen ? (
                  <div className="schemaColumns">
                    {cols.map((c) => (
                      <div key={c.name} className="schemaColumnRow">
                        <div className="schemaColumnName" title={c.name}>{c.name}</div>
                        <div className="schemaColumnType" title={formatDataType(c)}>
                          {formatDataType(c)}
                        </div>
                      </div>
                    ))}
                    {cols.length === 0 ? <div className="meta">No columns found.</div> : null}
                  </div>
                ) : null}
              </div>
            )
          })}

          {(!loading && !error && filtered.length === 0) ? (
            <div className="meta">No matches.</div>
          ) : null}
        </div>
      </div>

      <div className="sidebarFooter">
        <div className="sidebarFooterTitle">Shortcuts</div>
        <div>Ctrl+Enter: Send</div>
      </div>
    </aside>
  )
}
