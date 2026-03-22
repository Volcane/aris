import { useState, useEffect, useRef } from 'react'
import { Play, RefreshCw, Check, AlertTriangle, ChevronRight, Info, Zap } from 'lucide-react'
import { api } from '../api.js'
import { Spinner, SectionHeader } from '../components.jsx'

const ALL_SOURCES = [
  { id: 'federal',       label: 'US Federal',       sub: 'Federal Register · Regulations.gov · Congress.gov' },
  { id: 'states',        label: 'US States',         sub: 'All 18 enabled states' },
  { id: 'PA',            label: 'Pennsylvania',      sub: 'PA General Assembly ZIP + LegiScan' },
  { id: 'CA',            label: 'California',        sub: 'CA Legislature API + LegiScan' },
  { id: 'CO',            label: 'Colorado',          sub: 'leg.colorado.gov API + LegiScan' },
  { id: 'IL',            label: 'Illinois',          sub: 'ILGA RSS feeds + LegiScan' },
  { id: 'TX',            label: 'Texas',             sub: 'TLO RSS + LegiScan' },
  { id: 'WA',            label: 'Washington',        sub: 'WSL web services + LegiScan' },
  { id: 'NY',            label: 'New York',          sub: 'NY Senate API + LegiScan' },
  { id: 'FL',            label: 'Florida',           sub: 'FL Senate API + LegiScan' },
  { id: 'MN',            label: 'Minnesota',         sub: 'MN Senate RSS + LegiScan' },
  { id: 'CT',            label: 'Connecticut',       sub: 'LegiScan' },
  { id: 'VA',            label: 'Virginia',          sub: 'LegiScan' },
  { id: 'NJ',            label: 'New Jersey',        sub: 'LegiScan' },
  { id: 'MA',            label: 'Massachusetts',     sub: 'LegiScan' },
  { id: 'OR',            label: 'Oregon',            sub: 'LegiScan' },
  { id: 'MD',            label: 'Maryland',          sub: 'LegiScan' },
  { id: 'GA',            label: 'Georgia',           sub: 'LegiScan' },
  { id: 'AZ',            label: 'Arizona',           sub: 'LegiScan' },
  { id: 'NC',            label: 'North Carolina',    sub: 'LegiScan' },
  { id: 'international', label: 'International',     sub: 'EU · UK · Canada · SG · IN · BR · JP · KR · AU' },
  { id: 'EU',            label: 'European Union',    sub: 'EUR-Lex SPARQL · EU AI Office RSS' },
  { id: 'GB',            label: 'United Kingdom',    sub: 'UK Parliament Bills · legislation.gov.uk' },
  { id: 'CA_INTL',       label: 'Canada',            sub: 'OpenParliament · Canada Gazette · ISED' },
  { id: 'SG',            label: 'Singapore',         sub: 'PDPC RSS · IMDA RSS · pinned frameworks' },
  { id: 'IN',            label: 'India',             sub: 'PIB RSS (MEITY) · DPDP Act · IndiaAI' },
  { id: 'BR',            label: 'Brazil',            sub: 'ANPD RSS · Senate RSS · LGPD · AI Bill' },
  { id: 'JP',            label: 'Japan',             sub: 'METI English RSS · pinned guidelines' },
  { id: 'KR',            label: 'South Korea',       sub: 'MSIT press releases · PIPA · AI Act draft' },
  { id: 'AU',            label: 'Australia',         sub: 'Voluntary AI Safety Standard · pinned docs' },
]

const URGENCY_COLORS = {
  Critical: 'var(--red)',
  High:     'var(--orange)',
  Medium:   'var(--yellow)',
  Low:      'var(--green)',
}

export default function RunAgents({ onJobStart }) {
  const [selectedSources, setSelectedSources] = useState([])
  const [lookbackDays,    setLookbackDays]    = useState(30)
  const [summarize,       setSummarize]       = useState(true)
  const [runDiff,         setRunDiff]         = useState(true)
  const [limit,           setLimit]           = useState(50)
  const [forceSummarize,  setForceSummarize]  = useState(false)
  const [domain,          setDomain]          = useState(() => {
    try {
      const recent = ['documents','changes','horizon','enforcement','baselines','trends','synthesis']
        .map(k => localStorage.getItem(`aris_domain_${k}`))
        .find(v => v && v !== '')
      return recent || 'both'
    } catch { return 'both' }
  })
  const [running,         setRunning]         = useState(false)
  const [logLines,        setLogLines]        = useState([])
  const [logOffset,       setLogOffset]       = useState(0)
  const [lastResult,      setLastResult]      = useState(null)
  const [isFirstRun,      setIsFirstRun]      = useState(false)
  const logRef = useRef(null)

  // Check on mount if this is a first-run situation
  useEffect(() => {
    api.status().then(s => {
      const stats = s?.stats || {}
      const realSummaries = (stats.total_summaries || 0) - (stats.skipped_summaries || 0)
      const hasDocs = (stats.total_documents || 0) > 0
      setIsFirstRun(hasDocs && realSummaries === 0)
    }).catch(() => {})
  }, [])

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
          // Re-check first run state after run completes
          const stats = status.last_result || {}
          const realSummaries = (stats.total_summaries || 0) - (stats.skipped_summaries || 0)
          setIsFirstRun(false)  // cleared after any run completes
        }
      } catch {}
    }, 1500)
    return () => clearInterval(id)
  }, [running, logOffset])

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
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
    setSelectedSources(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id])
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 860 }}>
      <SectionHeader title="Run Agents" subtitle="Fetch new documents and run AI summarization" />

      {/* First-run banner */}
      {isFirstRun && !running && (
        <div style={{
          marginBottom: 20, padding: '12px 16px',
          background: 'rgba(212,168,67,0.10)', border: '1px solid rgba(212,168,67,0.4)',
          borderRadius: 'var(--radius)', display: 'flex', gap: 10, alignItems: 'flex-start',
        }}>
          <Zap size={15} style={{ color: 'var(--yellow)', flexShrink: 0, marginTop: 1 }} />
          <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6 }}>
            <strong style={{ color: 'var(--yellow)' }}>First run detected.</strong>{' '}
            Force Summarize will be enabled automatically so your first batch processes fully
            without the relevance pre-filter. After this run, the pre-filter activates normally.
          </div>
        </div>
      )}

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
                <input type="checkbox" checked={selectedSources.includes(src.id)} onChange={() => toggleSource(src.id)} style={{ width: 'auto', marginTop: 2, accentColor: 'var(--accent)' }} />
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
                { val: summarize, set: setSummarize, label: 'Run AI summarization (Claude)' },
                { val: runDiff,   set: setRunDiff,   label: 'Run change detection (diffs & addenda)' },
              ].map(({ val, set, label }) => (
                <label key={label} className="flex items-center gap-3" style={{ cursor: 'pointer', fontSize: 13 }}>
                  <input type="checkbox" checked={val} onChange={e => set(e.target.checked)} style={{ width: 'auto', accentColor: 'var(--accent)' }} />
                  <span style={{ color: 'var(--text-2)' }}>{label}</span>
                </label>
              ))}
              {summarize && (
                <div style={{ padding: '10px 12px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', border: `1px solid ${forceSummarize ? 'var(--yellow)' : 'var(--border)'}` }}>
                  <label className="flex items-center gap-3" style={{ cursor: 'pointer', fontSize: 13, marginBottom: 6 }}>
                    <input type="checkbox" checked={forceSummarize} onChange={e => setForceSummarize(e.target.checked)} style={{ width: 'auto', accentColor: 'var(--yellow)' }} />
                    <span style={{ color: forceSummarize ? 'var(--yellow)' : 'var(--text-2)', fontWeight: 500 }}>Force Summarize</span>
                    {forceSummarize && <span style={{ marginLeft: 'auto', fontSize: 10, background: 'rgba(212,168,67,0.15)', color: 'var(--yellow)', padding: '1px 6px', borderRadius: 3, fontFamily: 'var(--font-mono)' }}>ON</span>}
                  </label>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', lineHeight: 1.5 }}>
                    Bypasses the relevance pre-filter. Use this if documents show as "Skipped"
                    in the Documents view or if fewer documents are being summarized than expected.
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Run button */}
          <div style={{ marginTop: 28 }}>
            <button className="btn-primary" onClick={handleRun} disabled={running}
              style={{ width: '100%', justifyContent: 'center', padding: '11px 16px', fontSize: 14 }}>
              {running
                ? <><Spinner size={14} /> Running…</>
                : <><Play size={14} /> Run {selectedSources.length > 0 ? selectedSources.join(', ') : 'All Sources'}</>
              }
            </button>
          </div>

          {/* Post-run summary card */}
          {lastResult && !running && (
            <RunResultCard result={lastResult} />
          )}
        </div>
      </div>

      {/* Live log */}
      <div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
          Agent Log {running && <Spinner size={11} />}
        </div>
        <div ref={logRef} style={{ background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '14px 16px', height: 280, overflow: 'auto', fontFamily: 'var(--font-mono)', fontSize: 12, lineHeight: 1.8, color: 'var(--text-3)' }}>
          {logLines.length === 0
            ? <span style={{ color: 'var(--text-3)', fontStyle: 'italic' }}>Run an agent to see live output…</span>
            : logLines.map((line, i) => (
                <div key={i} style={{
                  color: line.includes('ERROR')    ? 'var(--red)'
                       : line.includes('complete') || line.includes('✓') ? 'var(--green)'
                       : line.includes('Summariz') || line.includes('Force') ? 'var(--accent)'
                       : line.includes('skipped')  ? 'var(--yellow)'
                       : 'var(--text-2)',
                }}>{line}</div>
              ))
          }
        </div>
      </div>
    </div>
  )
}

// ── Post-run summary card ─────────────────────────────────────────────────────

function RunResultCard({ result }) {
  const fetched    = result.fetched    ?? 0
  const summarized = result.summarized ?? 0
  const skipped    = result.skipped    ?? 0
  const diffs      = result.version_diffs ?? 0
  const addenda    = result.addenda_found ?? 0
  const totalChanges = diffs + addenda
  const urgency    = result.urgency_dist || {}
  const critical   = urgency.Critical || 0
  const high       = urgency.High     || 0
  const firstRun   = result.first_run  || false

  const rows = [
    {
      label: 'Fetched',
      value: fetched,
      sub: 'new documents',
      color: 'var(--text)',
    },
    {
      label: 'Summarised',
      value: summarized,
      sub: firstRun ? 'first run — force mode' : undefined,
      color: 'var(--green)',
      link: '/documents',
    },
    skipped > 0 && {
      label: 'Skipped',
      value: skipped,
      sub: 'relevance pre-filter',
      color: 'var(--yellow)',
      link: '/documents',
      warn: true,
    },
    totalChanges > 0 && {
      label: 'Changes',
      value: totalChanges,
      sub: critical > 0 ? `${critical} critical` : high > 0 ? `${high} high` : undefined,
      color: critical > 0 ? 'var(--red)' : high > 0 ? 'var(--orange)' : 'var(--text-2)',
      link: '/changes',
    },
  ].filter(Boolean)

  return (
    <div style={{ marginTop: 16, background: 'var(--bg-2)', border: '1px solid var(--green-dim)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ padding: '10px 14px', background: 'var(--green-dim)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <Check size={14} style={{ color: 'var(--green)' }} />
        <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--green)' }}>Run complete</span>
        {firstRun && (
          <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--yellow)', fontFamily: 'var(--font-mono)', background: 'rgba(212,168,67,0.15)', padding: '1px 6px', borderRadius: 3 }}>
            FIRST RUN
          </span>
        )}
      </div>

      {/* Stats */}
      <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 6 }}>
        {rows.map((row, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
            <span style={{ fontFamily: 'var(--font-display)', fontSize: '1.1rem', fontWeight: 300, color: row.color, minWidth: 28, textAlign: 'right' }}>
              {row.value}
            </span>
            <span style={{ color: 'var(--text-2)' }}>{row.label}</span>
            {row.sub && (
              <span style={{ fontSize: 11, color: row.warn ? 'var(--yellow)' : 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
                {row.sub}
              </span>
            )}
            {row.link && (
              <a href={row.link} style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--accent)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 2 }}>
                View <ChevronRight size={11} />
              </a>
            )}
          </div>
        ))}

        {/* Urgency pills — only if we have urgency data */}
        {Object.keys(urgency).length > 0 && (
          <div style={{ marginTop: 6, paddingTop: 8, borderTop: '1px solid var(--border)', display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {['Critical','High','Medium','Low'].filter(u => urgency[u] > 0).map(u => (
              <span key={u} style={{ fontSize: 11, fontFamily: 'var(--font-mono)', padding: '2px 7px', borderRadius: 4, background: URGENCY_COLORS[u] + '18', color: URGENCY_COLORS[u] }}>
                {urgency[u]} {u}
              </span>
            ))}
            <span style={{ fontSize: 11, color: 'var(--text-3)', marginLeft: 'auto' }}>
              {result.total_documents ?? 0} total in DB
            </span>
          </div>
        )}

        {/* Skipped hint */}
        {skipped > 0 && (
          <div style={{ marginTop: 4, padding: '8px 10px', background: 'rgba(212,168,67,0.08)', border: '1px solid rgba(212,168,67,0.25)', borderRadius: 'var(--radius)', fontSize: 11, color: 'var(--text-3)', lineHeight: 1.5 }}>
            <Info size={11} style={{ color: 'var(--yellow)', verticalAlign: 'middle', marginRight: 4 }} />
            {skipped} document{skipped > 1 ? 's' : ''} were filtered by the relevance pre-filter and show as "Skipped" in Documents.
            Check <strong style={{ color: 'var(--text-2)' }}>Force Summarize</strong> to process them regardless of score.
          </div>
        )}
      </div>
    </div>
  )
}
