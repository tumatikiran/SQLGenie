export default function Message({ message }) {
  const isUser = message.role === 'user'

  return (
    <div className="msgRow" style={{ justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
      <div className={`msgBubble ${isUser ? 'msgUser' : 'msgAssistant'}`}>
        <div className="msgText">{message.text}</div>

        {message.error ? (
          <div className="errorBox">{message.error}</div>
        ) : null}

        {message.sql ? (
          <div className="msgBlock">
            <div className="msgBlockTitle">Generated SQL</div>
            <pre className="pre">{message.sql}</pre>
          </div>
        ) : null}

        {Array.isArray(message.columns) && message.columns.length > 0 ? (
          <div className="msgBlock">
            <div className="msgBlockTitle">Results (first {Math.min(message.rows?.length || 0, 100)} rows)</div>
            <div className="tableWrap">
              <table className="resultTable">
                <thead>
                  <tr>
                    {message.columns.map((c) => (
                      <th key={c}>{c}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(message.rows || []).map((r, idx) => (
                    <tr key={idx}>
                      {r.map((cell, j) => (
                        <td key={j}>{formatCell(cell)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}

function formatCell(v) {
  if (v === null || v === undefined) return ''
  if (typeof v === 'object') {
    try {
      return JSON.stringify(v)
    } catch {
      return String(v)
    }
  }
  return String(v)
}
