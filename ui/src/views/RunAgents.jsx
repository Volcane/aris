import { useState, useEffect, useRef } from 'react'
import { Play, Square, RefreshCw, Check } from 'lucide-react'
import { api } from '../api.js'
import { Spinner, SectionHeader } from '../components.jsx'

const ALL_SOURCES = [
  { id: 'federal',       label: 'US Federal',       sub: 'Federal Register · Regulations.gov · Congress.gov' },
  { id: 'states',        label: 'US States',         sub: 'All enabled state legislatures (LegiScan + native feeds)' },
  { id: 'PA',            label: 'Pennsylvania',      sub: 'PA General Assembly XML + LegiScan' },
  { id: 'international', label: 'International',     sub: 'EU · UK · Canada · Japan · China · Australia' },
  { id: 'EU',            label: 'European Union',    sub: 'EUR-Lex SPARQL · EU AI Office RSS' },
  { id: 'GB',            label: 'United Kingdom',    sub: 'UK Parliament Bills · legislation.gov.uk · GOV.UK' },
  { id: 'CA',            label: 'Canada',            sub: 'OpenParliament · Canada Gazette · ISED feed' },
]

export default function RunAgents({ onJobStart }) {
  const [selectedSources, setSelectedSources] = useState([])   // empty = all
  const [lookbackDays,    setLookbackDays]    = useState(30)
  const [summarize,       setSummarize]       = useState(true)
  const [runDiff,         setRunDiff]         = useState(true)
  const [limit,           setLimit]           = useState(50)
  const [forceSummarize,  setForceSummarize]  = useState(false)
  const [domain,          setDomain]          = useState('both')
  const [running,         setRunning]         = useState(false)
  const [logLines,        setLogLines]        = useState([])
  const [logOffset,       setLogOffset]       = useState(0)
  const [lastResult,      setLastResult]      = useState(null)
  const logRef = useRef(null)

  // Poll log while running
  useEffect(() => {
    if (!running) return
    const id = setInterval(async () => {
      try {
        const res = await api.runLog(logOffset)
        if (res.lines.length > 0) {
          setLogLines(prev => [...prev, ...res.lines])
          setLogOffset(res.total)
        }
        if (!res.running) {
          setRunning(false)
          clearInterval(id)
          const status = await api.runStatus()
          setLastResult(status.last_result)
        }
      } catch {}
    }, 1500)
    return () => clearInterval(id)
  }, [running, logOffset])

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [logLines])

  const handleRun = async () => {
    setRunning(true)
    setLogLines([])
    setLogOffset(0)
    setLastResult(null)
    onJobStart?.()
    try {
      await api.runAgents({
        sources:         selectedSources,
        lookback_days:   lookbackDays,
        summarize,
        run_diff:        runDiff,
        limit,
        force_summarize: forceSummarize,
        domain,
      })
    } catch (e) {
      setLogLines([`ERROR: ${e.message}`])
      setRunning(false)
    }
  }

  const toggleSource = (id) => {
    setSelectedSources(prev =>
      prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]
    )
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 860 }}>
      <SectionHeader title="Run Agents" subtitle="Fetch new documents and run AI summarization" />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 28 }}>
        {/* Source selection */}
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
            Sources
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 10 }}>
            Leave all unchecked to run everything.
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {ALL_SOURCES.map(src => (
              <label key={src.id} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, cursor: 'pointer', padding: '10px 12px', background: selectedSources.includes(src.id) ? 'var(--bg-4)' : 'var(--bg-2)', border: `1px solid ${selectedSources.includes(src.id) ? 'var(--accent-dim)' : 'var(--border)'}`, borderRadius: 'var(--radius)', transition: 'all 0.15s' }}>
                <input
                  type="checkbox"
                  checked={selectedSources.includes(src.id)}
                  onChange={() => toggleSource(src.id)}
                  style={{ width: 'auto', marginTop: 2, accentColor: 'var(--accent)' }}
                />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>{src.label}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{src.sub}</div>
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Options */}
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
            Options
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 6 }}>Domain</label>
              <select value={domain} onChange={e => setDomain(e.target.value)}>
                <option value="both">Both (AI + Privacy)</option>
                <option value="ai">AI Regulation only</option>
                <option value="privacy">Data Privacy only</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 6 }}>Lookback window</label>
              <select value={lookbackDays} onChange={e => setLookbackDays(Number(e.target.value))}>
                <option value={3}>3 days</option>
                <option value={7}>7 days</option>
                <option value={14}>14 days</option>
                <option value={30}>30 days</option>
                <option value={60}>60 days</option>
                <option value={90}>90 days</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 6 }}>Max documents to summarize</label>
              <select value={limit} onChange={e => setLimit(Number(e.target.value))}>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
                <option value={200}>200</option>
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                { val: summarize,      set: setSummarize,      label: 'Run AI summarization (Claude)' },
                { val: runDiff,        set: setRunDiff,        label: 'Run change detection (diffs & addenda)' },
              ].map(({ val, set, label }) => (
                <label key={label} className="flex items-center gap-3" style={{ cursor: 'pointer', fontSize: 13 }}>
                  <input
                    type="checkbox"
                    checked={val}
                    onChange={e => set(e.target.checked)}
                    style={{ width: 'auto', accentColor: 'var(--accent)' }}
                  />
                  <span style={{ color: 'var(--text-2)' }}>{label}</span>
                </label>
              ))}
              {summarize && (
                <label className="flex items-center gap-3"
                       style={{ cursor: 'pointer', fontSize: 12, paddingLeft: 4 }}>
                  <input
                    type="checkbox"
                    checked={forceSummarize}
                    onChange={e => setForceSummarize(e.target.checked)}
                    style={{ width: 'auto', accentColor: 'var(--yellow)' }}
                  />
                  <span style={{ color: forceSummarize ? 'var(--yellow)' : 'var(--text-3)' }}>
                    Force summarize — bypass quality filter
                    {forceSummarize && <span style={{ marginLeft: 6, fontSize: 10,
                      background: 'rgba(212,168,67,0.15)', color: 'var(--yellow)',
                      padding: '1px 6px', borderRadius: 3, fontFamily: 'var(--font-mono)' }}>
                      ON
                    </span>}
                  </span>
                </label>
              )}
            </div>
          </div>

          {/* Run button */}
          <div style={{ marginTop: 28 }}>
            <button
              className="btn-primary"
              onClick={handleRun}
              disabled={running}
              style={{ width: '100%', justifyContent: 'center', padding: '11px 16px', fontSize: 14 }}
            >
              {running
                ? <><Spinner size={14} /> Running…</>
                : <><Play size={14} /> Run {selectedSources.length > 0 ? selectedSources.join(', ') : 'All Sources'}</>
              }
            </button>
          </div>

          {/* Last result */}
          {lastResult && !running && (
            <div style={{ marginTop: 16, padding: '12px 14px', background: 'var(--green-dim)', border: '1px solid var(--green)', borderRadius: 'var(--radius)', fontSize: 12 }}>
              <div className="flex items-center gap-2" style={{ color: 'var(--green)', marginBottom: 6, fontWeight: 500 }}>
                <Check size={14} /> Run complete
              </div>
              <div style={{ color: 'var(--text-2)', display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span>Fetched: {lastResult.fetched ?? '—'} new documents</span>
                <span>Summarized: {lastResult.summarized ?? '—'}</span>
                {lastResult.version_diffs != null && <span>Version diffs: {lastResult.version_diffs}</span>}
                {lastResult.addenda_found != null && <span>Addenda found: {lastResult.addenda_found}</span>}
                <span>Total in DB: {lastResult.total_documents ?? '—'}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Live log */}
      <div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
          Agent Log {running && <Spinner size={11} />}
        </div>
        <div
          ref={logRef}
          style={{
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            padding: '14px 16px',
            height: 280,
            overflow: 'auto',
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            lineHeight: 1.8,
            color: 'var(--text-3)',
          }}
        >
          {logLines.length === 0 ? (
            <span style={{ color: 'var(--text-3)', fontStyle: 'italic' }}>Run an agent to see live output…</span>
          ) : (
            logLines.map((line, i) => (
              <div
                key={i}
                style={{
                  color: line.includes('ERROR') ? 'var(--red)'
                    : line.includes('complete') || line.includes('✓') ? 'var(--green)'
                    : line.includes('Summariz') ? 'var(--accent)'
                    : 'var(--text-2)',
                }}
              >
                {line}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
