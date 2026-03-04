import { useRef, useState } from 'react'
import { uploadCSV, createSession } from '../api/client.js'

const CHART_TYPES = [
  { value: 'scatter',  label: 'Scatter Plot' },
  { value: 'bar',      label: 'Bar Chart' },
  { value: 'line',     label: 'Line Chart' },
  { value: 'parallel', label: 'Parallel Coordinates' },
  { value: 'heatmap',  label: 'Heatmap' },
  { value: 'sankey',   label: 'Sankey Diagram' },
]

const ENCODING_FIELDS = {
  scatter:  ['x', 'y', 'color', 'size'],
  bar:      ['x', 'y', 'color'],
  line:     ['x', 'y', 'color'],
  parallel: ['columns', 'color'],
  heatmap:  ['x', 'y', 'color'],
  sankey:   ['source', 'target', 'value'],
}

function ColumnTag({ type, name }) {
  const cls = type === 'numeric' ? 'tag tag-numeric'
    : type === 'datetime' ? 'tag tag-datetime'
    : 'tag tag-categorical'
  return <span className={cls} title={type}>{name}</span>
}

export default function DataPanel({ onSessionCreated, sessions, currentSessionId, onSwitchSession }) {
  const fileRef = useRef(null)
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [dataset, setDataset] = useState(null)
  const [chartType, setChartType] = useState('scatter')
  const [encoding, setEncoding] = useState({})
  const [width, setWidth] = useState(600)
  const [height, setHeight] = useState(400)
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState('')
  const [specJson, setSpecJson] = useState('')
  const [useDirectSpec, setUseDirectSpec] = useState(false)

  const colInfo = dataset?.column_info || {}
  const allCols = colInfo.all || []

  function getColType(colName) {
    if ((colInfo.numeric || []).includes(colName)) return 'numeric'
    if ((colInfo.datetime || []).includes(colName)) return 'datetime'
    return 'categorical'
  }

  function handleFile(file) {
    if (!file) return
    setError('')
    setUploading(true)
    setUploadProgress(0)
    uploadCSV(file, (e) => {
      if (e.lengthComputable) setUploadProgress(Math.round(e.loaded / e.total * 100))
    })
      .then((data) => {
        setDataset(data)
        setEncoding({})
        setChartType('scatter')
      })
      .catch((e) => setError(e.message))
      .finally(() => { setUploading(false); setUploadProgress(0) })
  }

  function autoFill() {
    if (!dataset) return
    const { numeric = [], categorical = [], datetime = [] } = colInfo
    const auto = {}
    if (chartType === 'scatter') {
      auto.x = numeric[0] || allCols[0] || ''
      auto.y = numeric[1] || numeric[0] || allCols[1] || ''
      if (categorical[0]) auto.color = categorical[0]
    } else if (chartType === 'bar') {
      auto.x = categorical[0] || allCols[0] || ''
      auto.y = numeric[0] || allCols[1] || ''
      if (categorical[1]) auto.color = categorical[1]
    } else if (chartType === 'line') {
      auto.x = datetime[0] || categorical[0] || allCols[0] || ''
      auto.y = numeric[0] || allCols[1] || ''
      if (categorical[0] && auto.x !== categorical[0]) auto.color = categorical[0]
    } else if (chartType === 'parallel') {
      auto.columns = numeric.slice(0, Math.min(5, numeric.length))
    } else if (chartType === 'heatmap') {
      auto.x = categorical[0] || allCols[0] || ''
      auto.y = categorical[1] || allCols[1] || ''
      auto.color = numeric[0] || ''
    } else if (chartType === 'sankey') {
      auto.source = categorical[0] || allCols[0] || ''
      auto.target = categorical[1] || allCols[1] || ''
    }
    setEncoding(auto)
  }

  async function generate() {
    setError('')
    setGenerating(true)
    try {
      let body
      if (useDirectSpec) {
        body = { spec: JSON.parse(specJson) }
      } else {
        body = {
          dataset_id: dataset.dataset_id,
          chart_type: chartType,
          encoding,
          width,
          height,
        }
      }
      const res = await createSession(body)
      onSessionCreated(res)
    } catch (e) {
      setError(e.message)
    } finally {
      setGenerating(false)
    }
  }

  const encFields = ENCODING_FIELDS[chartType] || []

  return (
    <div className="flex flex-col overflow-hidden" style={{ height: '100%' }}>
      <div className="panel-header">
        <div className="header-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" width="16" height="16">
            <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"/>
          </svg>
          <span>Data & Encoding</span>
        </div>
      </div>

      <div className="flex flex-col gap-3 overflow-y-auto p-3" style={{ flex: 1 }}>

        {/* session switcher */}
        {sessions.length > 0 && (
          <div>
            <div className="section-label">Sessions</div>
            <div className="flex flex-col gap-1" style={{ maxHeight: 110, overflowY: 'auto' }}>
              {sessions.map(s => (
                <button
                  key={s.session_id}
                  onClick={() => onSwitchSession(s.session_id)}
                  className={`btn btn-ghost btn-sm ${s.session_id === currentSessionId ? 'text-accent' : ''}`}
                  style={{
                    justifyContent: 'flex-start',
                    fontFamily: "'JetBrains Mono', monospace",
                    ...(s.session_id === currentSessionId ? { borderColor: 'var(--accent)', background: 'rgba(99, 102, 241, 0.06)', boxShadow: '0 0 0 3px var(--accent-glow)' } : {}),
                  }}
                >
                  {s.session_id.slice(0, 8)}...
                  <span className="text-dim" style={{ marginLeft: 'auto' }}>{s.chart_type || '?'}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* mode toggle */}
        <div>
          <div className="section-label">Input Mode</div>
          <div className="mode-toggle">
            <button className={!useDirectSpec ? 'active' : ''} onClick={() => setUseDirectSpec(false)}>CSV Upload</button>
            <button className={useDirectSpec ? 'active' : ''} onClick={() => setUseDirectSpec(true)}>Paste Spec</button>
          </div>
        </div>

        {useDirectSpec ? (
          <div>
            <div className="section-label">Vega / Vega-Lite JSON</div>
            <textarea
              className="textarea font-mono"
              style={{ minHeight: 180 }}
              placeholder='{"$schema": "...", "mark": "bar", ...}'
              value={specJson}
              onChange={e => setSpecJson(e.target.value)}
            />
          </div>
        ) : (
          <>
            {/* drop zone */}
            <div>
              <div className="section-label">CSV File</div>
              <div
                className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
                onClick={() => fileRef.current?.click()}
                onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={e => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]) }}
              >
                <input ref={fileRef} type="file" accept=".csv" style={{ display: 'none' }}
                  onChange={e => handleFile(e.target.files[0])} />
                {uploading ? (
                  <div className="flex flex-col items-center gap-2">
                    <div className="spinner" />
                    <span className="text-sm text-muted">Uploading... {uploadProgress}%</span>
                  </div>
                ) : dataset ? (
                  <div>
                    <div className="font-semibold" style={{ color: 'var(--accent)' }}>{dataset.filename}</div>
                    <div className="text-sm text-muted mt-1">{dataset.row_count.toLocaleString()} rows / {allCols.length} cols</div>
                  </div>
                ) : (
                  <div>
                    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.5" style={{ margin: '0 auto 8px', display: 'block', opacity: 0.5 }}>
                      <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                      <polyline points="17 8 12 3 7 8" />
                      <line x1="12" y1="3" x2="12" y2="15" />
                    </svg>
                    <div className="text-sm text-muted">Drag & drop CSV or click to browse</div>
                  </div>
                )}
              </div>
            </div>

            {/* column info */}
            {dataset && (
              <div>
                <div className="section-label">Columns</div>
                <div className="flex gap-1" style={{ flexWrap: 'wrap' }}>
                  {allCols.map(c => <ColumnTag key={c} name={c} type={getColType(c)} />)}
                </div>
              </div>
            )}

            {/* chart type */}
            <div>
              <div className="section-label">Chart Type</div>
              <select className="select" value={chartType} onChange={e => { setChartType(e.target.value); setEncoding({}) }}>
                {CHART_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>

            {/* encoding */}
            {dataset && (
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="section-label" style={{ marginBottom: 0 }}>Encoding</span>
                  <button className="btn btn-ghost btn-sm" onClick={autoFill}>Auto-fill</button>
                </div>
                <div className="flex flex-col gap-2">
                  {encFields.map(field => (
                    <div key={field}>
                      <label className="text-xs text-muted" style={{ display: 'block', marginBottom: 3 }}>
                        {field.toUpperCase()}
                      </label>
                      {field === 'columns' ? (
                        <select
                          className="select"
                          multiple
                          size={4}
                          value={encoding.columns || []}
                          onChange={e => {
                            const vals = Array.from(e.target.selectedOptions, o => o.value)
                            setEncoding(prev => ({ ...prev, columns: vals }))
                          }}
                        >
                          {allCols.map(c => <option key={c} value={c}>{c}</option>)}
                        </select>
                      ) : (
                        <select
                          className="select"
                          value={encoding[field] || ''}
                          onChange={e => setEncoding(prev => ({ ...prev, [field]: e.target.value || undefined }))}
                        >
                          <option value="">-- None --</option>
                          {allCols.map(c => <option key={c} value={c}>{c}</option>)}
                        </select>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* size */}
            <div className="flex gap-2">
              <div style={{ flex: 1 }}>
                <label className="section-label">Width</label>
                <input className="input" type="number" value={width} min={200} max={1600}
                  onChange={e => setWidth(+e.target.value)} />
              </div>
              <div style={{ flex: 1 }}>
                <label className="section-label">Height</label>
                <input className="input" type="number" value={height} min={150} max={1200}
                  onChange={e => setHeight(+e.target.value)} />
              </div>
            </div>
          </>
        )}

        {error && <div className="text-danger text-sm">{error}</div>}

        <button
          className="btn btn-primary w-full"
          disabled={generating || (!dataset && !useDirectSpec) || (useDirectSpec && !specJson.trim())}
          onClick={generate}
          style={{ padding: '10px 14px', fontSize: 13 }}
        >
          {generating ? (
            <><div className="spinner" style={{ width: 13, height: 13 }} /> Generating...</>
          ) : (
            <>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none">
                <polygon points="5,3 19,12 5,21" />
              </svg>
              Generate View
            </>
          )}
        </button>

      </div>
    </div>
  )
}
