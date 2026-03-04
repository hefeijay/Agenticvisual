import { useEffect, useRef, useState } from 'react'
import { streamQuery, resetView, exportSession } from '../api/client.js'

function ChatMessage({ msg }) {
  const cls = msg.role === 'user' ? 'bubble bubble-user'
    : msg.role === 'error' ? 'bubble bubble-error'
    : msg.role === 'system' ? 'bubble bubble-system'
    : 'bubble bubble-assistant'
  return (
    <div className="flex" style={{ flexDirection: msg.role === 'user' ? 'row-reverse' : 'row' }}>
      <div className={cls} style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
    </div>
  )
}

function ToolLog({ event }) {
  const [open, setOpen] = useState(false)
  const { tool_name, success, tool_result } = event.data
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8, marginTop: 4 }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text)', fontSize: 11 }}
      >
        <span style={{
          width: 8, height: 8, borderRadius: '50%',
          background: success ? 'var(--success)' : 'var(--danger)',
          display: 'inline-block', flexShrink: 0,
        }} />
        <span className="font-mono text-xs">{tool_name}</span>
        <span style={{ marginLeft: 'auto', color: 'var(--text-dim)', fontSize: 10 }}>{open ? '\u25B2' : '\u25BC'}</span>
      </button>
      {open && (
        <div style={{ borderTop: '1px solid var(--border)', maxHeight: 280, minHeight: 0, overflow: 'auto' }}>
          <pre className="font-mono text-xs" style={{ padding: '6px 8px', color: 'var(--text-muted)', margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
            {JSON.stringify(tool_result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

function SuggestionCards({ suggestions, onSelect, disabled }) {
  if (!suggestions?.length) return null
  return (
    <div>
      <div className="section-label">Suggestions</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {suggestions.map(s => (
          <button
            key={s.id}
            className="suggestion-card"
            disabled={disabled}
            onClick={() => onSelect(s.payload || s.query || s.label)}
          >
            <div style={{ fontWeight: 600, fontSize: 11, color: 'var(--text)' }}>{s.label}</div>
            <div className="text-xs text-dim mt-1" style={{ lineHeight: 1.4 }}>{s.description}</div>
          </button>
        ))}
      </div>
    </div>
  )
}

function ChoiceUI({ options, onSelect }) {
  const [custom, setCustom] = useState('')
  const [selected, setSelected] = useState(null)
  if (!options?.length) return null
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--accent)', borderRadius: 10, padding: 12, boxShadow: '0 0 0 3px var(--accent-glow)' }}>
      <div className="section-label">Choose an Option</div>
      <div className="flex flex-col gap-1 mt-1">
        {options.map((opt, i) => (
          <button
            key={i}
            className={`choice-option ${selected === i ? 'selected' : ''}`}
            onClick={() => { setSelected(i); onSelect(opt.label || opt) }}
          >
            {opt.label || opt}
          </button>
        ))}
        <div className="flex gap-2 mt-1">
          <input
            className="input"
            placeholder="Custom input..."
            value={custom}
            onChange={e => setCustom(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && custom.trim()) { setSelected(-1); onSelect(custom.trim()) } }}
          />
          <button
            className="btn btn-primary btn-sm shrink-0"
            disabled={!custom.trim()}
            onClick={() => { if (custom.trim()) { setSelected(-1); onSelect(custom.trim()) } }}
          >OK</button>
        </div>
      </div>
    </div>
  )
}

function IterationDetail({ record }) {
  const [open, setOpen] = useState(false)
  const { iteration, success, analysis_summary, tool_name, duration } = record
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 8 }}>
      <button
        onClick={() => setOpen(v => !v)}
        style={{ width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px', background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text)', fontSize: 12 }}
      >
        <span style={{ color: 'var(--accent)', fontWeight: 600, fontFamily: "'JetBrains Mono', monospace" }}>#{iteration}</span>
        {tool_name && <span className="font-mono text-xs" style={{ color: 'var(--accent-purple)' }}>{tool_name}</span>}
        <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6, fontSize: 10 }}>
          {duration ? <span style={{ color: 'var(--text-dim)' }}>{duration.toFixed(1)}s</span> : null}
          <span style={{
            width: 8, height: 8, borderRadius: '50%',
            background: success ? 'var(--success)' : 'var(--danger)',
            display: 'inline-block',
          }} />
        </span>
        <span style={{ color: 'var(--text-dim)', fontSize: 10 }}>{open ? '\u25B2' : '\u25BC'}</span>
      </button>
      {open && (
        <div style={{ padding: '8px 10px', borderTop: '1px solid var(--border)' }}>
          {analysis_summary?.key_insights?.map((ins, i) => (
            <div key={i} className="text-xs" style={{ color: 'var(--text-muted)', marginBottom: 3 }}>
              <span style={{ color: 'var(--accent)', marginRight: 4 }}>&gt;</span>{ins}
            </div>
          ))}
          {analysis_summary?.reasoning && (
            <div className="text-xs text-dim mt-1">{analysis_summary.reasoning}</div>
          )}
        </div>
      )}
    </div>
  )
}

export default function AgentPanel({
  sessionId,
  onSpecUpdated,
  onSpecHistoryItem,
  isRunning,
  setIsRunning,
}) {
  const [runMode, setRunMode] = useState('cooperative')
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [choiceOptions, setChoiceOptions] = useState(null)
  const [iterRecords, setIterRecords] = useState([])
  const [toolLogs, setToolLogs] = useState([])
  const [activeTab, setActiveTab] = useState('chat')
  const cancelRef = useRef(null)
  const chatEndRef = useRef(null)

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    setMessages([])
    setSuggestions([])
    setChoiceOptions(null)
    setIterRecords([])
    setToolLogs([])
    setInput('')
  }, [sessionId])

  function addMsg(role, content) {
    setMessages(prev => [...prev, { id: Date.now() + Math.random(), role, content }])
  }

  function submitQuery(query) {
    if (!sessionId || !query.trim() || isRunning) return
    const q = query.trim()
    addMsg('user', q)
    setInput('')
    setSuggestions([])
    setChoiceOptions(null)
    setIsRunning(true)
    setToolLogs([])

    cancelRef.current = streamQuery(sessionId, q, runMode, (msg) => {
      const { event, data } = msg

      if (event === 'iteration.started') {
        addMsg('system', `Iteration ${data.iteration} started`)
      } else if (event === 'agent.message') {
        if (data.key_insights?.length) {
          addMsg('assistant',
            data.key_insights.map(i => `> ${i}`).join('\n') +
            (data.reasoning ? `\n\n${data.reasoning}` : '')
          )
        }
      } else if (event === 'tool.started') {
        addMsg('system', `Tool: ${data.tool_name}`)
      } else if (event === 'tool.finished') {
        setToolLogs(prev => [...prev, { event: event, data }])
        if (!data.success) addMsg('error', `Tool ${data.tool_name} failed`)
      } else if (event === 'view.updated') {
        if (data.spec) {
          onSpecUpdated(data.spec)
          onSpecHistoryItem({
            spec_id: data.spec_id || `v${Date.now()}`,
            spec: data.spec,
            iteration: data.iteration,
            tool_name: data.tool_name,
            timestamp: Date.now(),
          })
        }
      } else if (event === 'iteration.finished') {
        setIterRecords(prev => [...prev, data])
      } else if (event === 'run.finished') {
        const mode = data.mode || ''
        const totalIter = (data.explorations || data.iterations || []).length
        addMsg('system', `${mode} finished - ${totalIter} iterations`)

        if (data.final_report?.summary) {
          addMsg('assistant', data.final_report.summary)
        }
        if (data.next_action_suggestions?.length) {
          setSuggestions(data.next_action_suggestions)
        }
        setIsRunning(false)
      } else if (event === 'error') {
        addMsg('error', data.message || 'Unknown error')
        setIsRunning(false)
      }
    })
  }

  function cancel() {
    if (cancelRef.current) {
      cancelRef.current()
      cancelRef.current = null
    }
    setIsRunning(false)
    addMsg('system', 'Cancelled')
  }

  async function handleReset() {
    if (!sessionId) return
    try {
      const r = await resetView(sessionId)
      if (r.current_spec) onSpecUpdated(r.current_spec)
      addMsg('system', 'View reset to baseline')
      setSuggestions([])
    } catch (e) {
      addMsg('error', e.message)
    }
  }

  const tabItems = [
    { key: 'chat', label: 'Chat', count: null },
    { key: 'iterations', label: 'Iterations', count: iterRecords.length },
    { key: 'tools', label: 'Tools', count: toolLogs.length },
  ]

  return (
    <div className="flex flex-col overflow-hidden" style={{ height: '100%' }}>
      {/* header */}
      <div className="panel-header">
        <div className="header-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="16" height="16">
            <circle cx="12" cy="12" r="3" />
            <path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83" />
          </svg>
          <span>Agent</span>
        </div>
        <div className="flex gap-2">
          {sessionId && (
            <>
              <button className="btn btn-ghost btn-sm" onClick={handleReset} disabled={isRunning}>Reset</button>
              <button className="btn btn-ghost btn-sm" onClick={() => exportSession(sessionId)}>Export</button>
            </>
          )}
        </div>
      </div>

      {/* mode toggle */}
      <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--border)' }}>
        <div className="mode-toggle">
          <button className={runMode === 'cooperative' ? 'active' : ''} onClick={() => setRunMode('cooperative')}>
            Cooperative
          </button>
          <button className={runMode === 'autonomous' ? 'active' : ''} onClick={() => setRunMode('autonomous')}>
            Autonomous
          </button>
        </div>
      </div>

      {/* tabs */}
      <div className="flex" style={{ borderBottom: '1px solid var(--border)' }}>
        {tabItems.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`tab-btn ${activeTab === tab.key ? 'active' : ''}`}
          >
            {tab.label}{tab.count !== null ? ` (${tab.count})` : ''}
          </button>
        ))}
      </div>

      {/* tab content */}
      <div className="flex flex-col overflow-y-auto grow" style={{ padding: '10px 12px' }}>
        {activeTab === 'chat' && (
          <div className="flex flex-col gap-3">
            {!sessionId && (
              <div style={{
                textAlign: 'center',
                color: 'var(--text-dim)',
                padding: '40px 0',
                fontFamily: "'Inter', sans-serif",
                fontSize: 12,
                fontWeight: 600,
                letterSpacing: '0.04em',
              }}>
                GENERATE A VIEW TO START
              </div>
            )}
            {messages.map(m => <ChatMessage key={m.id} msg={m} />)}
            {isRunning && (
              <div className="flex items-center gap-2" style={{ color: 'var(--accent)', fontSize: 12 }}>
                <div className="spinner" />
                <span>Agent analyzing...</span>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
        )}
        {activeTab === 'iterations' && (
          <div className="flex flex-col gap-2">
            {iterRecords.length === 0 && <div className="text-dim text-sm">No iterations yet</div>}
            {iterRecords.map((r, i) => <IterationDetail key={i} record={r} />)}
          </div>
        )}
        {activeTab === 'tools' && (
          <div className="flex flex-col gap-2">
            {toolLogs.length === 0 && <div className="text-dim text-sm">No tool calls yet</div>}
            {toolLogs.map((log, i) => <ToolLog key={i} event={log} />)}
          </div>
        )}
      </div>

      {/* suggestions + choice */}
      {(suggestions.length > 0 || choiceOptions) && (
        <div style={{ padding: '8px 12px', borderTop: '1px solid var(--border)', background: 'var(--surface)' }}>
          {choiceOptions && (
            <ChoiceUI options={choiceOptions} onSelect={q => { setChoiceOptions(null); submitQuery(q) }} />
          )}
          {suggestions.length > 0 && !choiceOptions && (
            <SuggestionCards suggestions={suggestions} disabled={isRunning || !sessionId}
              onSelect={q => submitQuery(q)} />
          )}
        </div>
      )}

      {/* input bar */}
      <div style={{ padding: '12px 14px', borderTop: '1px solid var(--border)', background: 'var(--surface)', flexShrink: 0 }}>
        <div className="flex gap-2">
          <textarea
            className="textarea"
            rows={2}
            style={{ resize: 'none', minHeight: 'unset' }}
            placeholder={sessionId ? 'Describe your analysis goal...' : 'Create a session first'}
            value={input}
            disabled={!sessionId}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitQuery(input) }
            }}
          />
          {isRunning ? (
            <button className="btn btn-danger shrink-0" onClick={cancel} style={{ alignSelf: 'flex-end' }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <rect x="4" y="4" width="16" height="16" rx="2" />
              </svg>
              Stop
            </button>
          ) : (
            <button
              className="btn btn-primary shrink-0"
              disabled={!sessionId || !input.trim()}
              style={{ alignSelf: 'flex-end' }}
              onClick={() => submitQuery(input)}
            >
              Send
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
