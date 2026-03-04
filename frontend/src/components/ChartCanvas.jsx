import { useEffect, useRef, useState } from 'react'
import vegaEmbed from 'vega-embed'

function TimelineItem({ record, isActive, onClick }) {
  const toolName = record.tool_name || '--'
  const success = record.success !== false
  const iter = record.iteration || record.spec_id || '?'
  return (
    <div className={`timeline-item ${isActive ? 'active' : ''}`} onClick={onClick} title={toolName}>
      <div className="flex items-center justify-between">
        <span style={{ fontSize: 10, fontWeight: 600, color: 'var(--accent)' }}>#{iter}</span>
        <span style={{ fontSize: 9, width: 8, height: 8, borderRadius: '50%', background: success ? 'var(--success)' : 'var(--danger)', display: 'inline-block' }} />
      </div>
      <div className="truncate text-xs" style={{ color: 'var(--text-dim)' }}>{toolName}</div>
      {record.analysis_summary?.key_insights?.[0] && (
        <div className="truncate" style={{ fontSize: 9, color: 'var(--text-dim)' }}>
          {record.analysis_summary.key_insights[0]}
        </div>
      )}
    </div>
  )
}

export default function ChartCanvas({ spec, specHistory, onSelectSpec }) {
  const containerRef = useRef(null)
  const wrapperRef = useRef(null)
  const viewRef = useRef(null)
  const [renderError, setRenderError] = useState('')
  const [activeSpecId, setActiveSpecId] = useState(null)
  const [showSpecJson, setShowSpecJson] = useState(false)
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 })

  useEffect(() => {
    const el = wrapperRef.current
    if (!el) return
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect
        setContainerSize({ width: Math.floor(width), height: Math.floor(height) })
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    if (!spec || !containerRef.current) return
    if (containerSize.width === 0 || containerSize.height === 0) return
    setRenderError('')

    if (viewRef.current) {
      try { viewRef.current.finalize() } catch {}
      viewRef.current = null
    }

    const padding = 32
    const embedSpec = {
      ...spec,
      width: containerSize.width - padding,
      height: containerSize.height - padding,
      autosize: { type: 'fit', contains: 'padding' },
      config: {
        ...(spec.config || {}),
        background: 'transparent',
        axis: {
          domainColor: '#daddec',
          gridColor: 'rgba(99, 102, 241, 0.06)',
          tickColor: '#c5c9db',
          labelColor: '#64748b',
          titleColor: '#1e1b4b',
          labelFont: 'Inter',
          titleFont: 'Inter',
        },
        legend: {
          labelColor: '#64748b',
          titleColor: '#1e1b4b',
          labelFont: 'Inter',
          titleFont: 'Inter',
        },
        title: {
          color: '#1e1b4b',
          font: 'Inter',
          fontSize: 14,
          fontWeight: 600,
        },
        view: {
          stroke: '#daddec',
        },
        range: {
          category: ['#6366f1', '#8b5cf6', '#10b981', '#f59e0b', '#ef4444', '#3b82f6', '#ec4899', '#a78bfa'],
        },
      },
    }

    vegaEmbed(containerRef.current, embedSpec, {
      actions: { export: true, source: true, compiled: false, editor: true },
      renderer: 'canvas',
    })
      .then((result) => { viewRef.current = result.view })
      .catch((err) => setRenderError(err.message || String(err)))

    return () => {
      if (viewRef.current) {
        try { viewRef.current.finalize() } catch {}
        viewRef.current = null
      }
    }
  }, [spec, containerSize])

  function handleTimelineClick(item) {
    setActiveSpecId(item.spec_id || item.iteration)
    if (item.spec && onSelectSpec) onSelectSpec(item.spec)
  }

  const specStr = spec ? JSON.stringify(spec, null, 2) : ''

  return (
    <div className="flex flex-col overflow-hidden" style={{ height: '100%' }}>
      {/* toolbar */}
      <div className="panel-header">
        <div className="header-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="16" height="16">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <polyline points="7 14 11 10 15 13 19 8" />
          </svg>
          <span>Visualization Canvas</span>
        </div>
        <div className="flex gap-2">
          {spec && (
            <button className="btn btn-ghost btn-sm" onClick={() => setShowSpecJson(v => !v)}>
              {showSpecJson ? (
                <>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <polyline points="7 14 11 10 15 13 19 8" />
                  </svg>
                  Chart
                </>
              ) : (
                <>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <polyline points="16 18 22 12 16 6" />
                    <polyline points="8 6 2 12 8 18" />
                  </svg>
                  Spec
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* main area */}
      <div className="flex flex-col overflow-hidden" style={{ flex: 1 }}>
        {showSpecJson ? (
          <pre className="overflow-auto p-3 font-mono text-xs" style={{
            flex: 1,
            color: 'var(--text)',
            background: 'var(--surface2)',
          }}>
            {specStr}
          </pre>
        ) : (
          <div ref={wrapperRef} style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
            {!spec ? (
              <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)' }}>
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="var(--border-strong)" strokeWidth="0.8" style={{ marginBottom: 16 }}>
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <polyline points="7 14 11 10 15 13 19 8" />
                  <circle cx="17" cy="8" r="1.5" fill="var(--accent)" stroke="none" opacity="0.3" />
                </svg>
                <div style={{ fontFamily: "'Inter', sans-serif", fontSize: 12, fontWeight: 600, letterSpacing: '0.04em', color: 'var(--text-dim)' }}>
                  AWAITING DATA INPUT
                </div>
              </div>
            ) : renderError ? (
              <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ padding: 16, maxWidth: 500 }}>
                  <div className="font-semibold mb-2" style={{ color: 'var(--danger)' }}>Render Error</div>
                  <pre className="text-xs font-mono" style={{ color: 'var(--text-muted)', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                    {renderError}
                  </pre>
                  <div className="mt-2 text-dim text-xs">View the spec JSON via the Spec button above.</div>
                </div>
              </div>
            ) : (
              <div ref={containerRef} id="vega-container" style={{
                width: '100%',
                height: '100%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }} />
            )}
          </div>
        )}

        {/* timeline */}
        {specHistory.length > 0 && (
          <div style={{
            borderTop: '1px solid var(--border)',
            padding: '10px 14px',
            background: 'var(--surface)',
          }}>
            <div className="section-label">Iteration Timeline</div>
            <div className="timeline-rail">
              {specHistory.map((item, idx) => (
                <TimelineItem
                  key={item.spec_id || idx}
                  record={item}
                  isActive={(item.spec_id || item.iteration) === activeSpecId}
                  onClick={() => handleTimelineClick(item)}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
