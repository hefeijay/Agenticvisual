import { useCallback, useEffect, useState } from 'react'
import DataPanel from './components/DataPanel.jsx'
import ChartCanvas from './components/ChartCanvas.jsx'
import AgentPanel from './components/AgentPanel.jsx'
import { health, listSessions, getSession } from './api/client.js'

export default function App() {
  const [modelAvailable, setModelAvailable] = useState(null)
  const [sessions, setSessions] = useState([])
  const [currentSessionId, setCurrentSessionId] = useState(null)
  const [currentSpec, setCurrentSpec] = useState(null)
  const [specHistory, setSpecHistory] = useState([])
  const [isRunning, setIsRunning] = useState(false)

  useEffect(() => {
    health()
      .then(d => setModelAvailable(d.model_available))
      .catch(() => setModelAvailable(false))
  }, [])

  useEffect(() => {
    listSessions().then(d => setSessions(d.sessions || [])).catch(() => {})
  }, [])

  const handleSessionCreated = useCallback(async (res) => {
    const { session_id, baseline_spec } = res
    setCurrentSessionId(session_id)
    setCurrentSpec(baseline_spec)
    setSpecHistory([{
      spec_id: 'baseline',
      spec: baseline_spec,
      iteration: 0,
      tool_name: 'baseline',
      timestamp: Date.now(),
    }])
    setSessions(prev => {
      const exists = prev.some(s => s.session_id === session_id)
      if (exists) return prev
      return [{ session_id, chart_type: res.chart_type || '', created_at: Date.now(), last_activity: Date.now() }, ...prev]
    })
  }, [])

  const handleSwitchSession = useCallback(async (id) => {
    if (id === currentSessionId) return
    try {
      const state = await getSession(id)
      setCurrentSessionId(id)
      setCurrentSpec(state.current_spec || null)
      setSpecHistory(state.current_spec ? [{
        spec_id: 'restored',
        spec: state.current_spec,
        iteration: 0,
        tool_name: 'restored',
        timestamp: Date.now(),
      }] : [])
    } catch (e) {
      console.error('Switch session failed', e)
    }
  }, [currentSessionId])

  const handleSpecUpdated = useCallback((spec) => {
    setCurrentSpec(spec)
  }, [])

  const handleSpecHistoryItem = useCallback((item) => {
    setSpecHistory(prev => {
      const exists = prev.some(p => p.spec_id === item.spec_id)
      if (exists) return prev
      return [...prev, item]
    })
  }, [])

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100vh',
      overflow: 'hidden',
      background: 'var(--bg)',
    }}>

      {/* ── Brand bar ── */}
      <div className="brand-bar">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5">
            <circle cx="12" cy="12" r="10" opacity="0.3" />
            <circle cx="12" cy="12" r="3" fill="var(--accent)" stroke="none" opacity="0.8" />
            <line x1="12" y1="2" x2="12" y2="6" />
            <line x1="12" y1="18" x2="12" y2="22" />
            <line x1="2" y1="12" x2="6" y2="12" />
            <line x1="18" y1="12" x2="22" y2="12" />
          </svg>
          <span className="brand-title">AGENTICVISUAL</span>
        </div>
        <div className="brand-status">
          {modelAvailable === true && (
            <>
              <div className="pulse-dot" />
              <span>Model Online</span>
            </>
          )}
          {modelAvailable === false && (
            <span style={{ color: 'var(--danger)' }}>Model Offline</span>
          )}
        </div>
      </div>

      {/* ── Status warning ── */}
      {modelAvailable === false && (
        <div style={{
          background: 'var(--danger-dim)',
          color: 'var(--danger)',
          fontSize: 12,
          padding: '8px 24px',
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          borderBottom: '1px solid rgba(239, 68, 68, 0.15)',
          flexShrink: 0,
          fontWeight: 500,
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/>
            <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
          </svg>
          Model API unavailable — check OPENROUTER_API_KEY in .env
        </div>
      )}

      {/* ── Main 3-column：左侧数据 280，中间图表略窄，右侧对话更宽 ── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '280px 1fr minmax(360px, 0.6fr)',
        flex: 1,
        overflow: 'hidden',
        gap: 0,
      }}>
        {/* left: data panel */}
        <div className="glass-panel" style={{
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          borderRadius: 0,
          borderTop: 'none',
          borderLeft: 'none',
          borderBottom: 'none',
        }}>
          <DataPanel
            onSessionCreated={handleSessionCreated}
            sessions={sessions}
            currentSessionId={currentSessionId}
            onSwitchSession={handleSwitchSession}
          />
        </div>

        {/* center: chart canvas */}
        <div style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <ChartCanvas
            spec={currentSpec}
            specHistory={specHistory}
            onSelectSpec={handleSpecUpdated}
          />
        </div>

        {/* right: agent panel */}
        <div className="glass-panel" style={{
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          borderRadius: 0,
          borderTop: 'none',
          borderRight: 'none',
          borderBottom: 'none',
        }}>
          <AgentPanel
            sessionId={currentSessionId}
            onSpecUpdated={handleSpecUpdated}
            onSpecHistoryItem={handleSpecHistoryItem}
            isRunning={isRunning}
            setIsRunning={setIsRunning}
          />
        </div>
      </div>
    </div>
  )
}
