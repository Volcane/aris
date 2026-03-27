import { useState, useEffect, useRef } from 'react'
import { Play, RefreshCw, Check, AlertTriangle, ChevronRight, Info, Zap } from 'lucide-react'
import { api } from '../api.js'
import { Spinner, SectionHeader } from '../components.jsx'

// ── Source definitions grouped for compact rendering ─────────────────────────

const SOURCE_FEDERAL = { id: 'federal', label: 'US Federal', sub: 'Federal Register · Regulations.gov · Congress.gov' }

// All 50 US states grouped by region for compact display
const STATE_REGIONS = [
  { label: 'Northeast', states: [
    { id:'CT', label:'CT' }, { id:'DE', label:'DE' }, { id:'MA', label:'MA' },
    { id:'ME', label:'ME' }, { id:'NH', label:'NH' }, { id:'NJ', label:'NJ' },
    { id:'NY', label:'NY', native:true }, { id:'PA', label:'PA', native:true },
    { id:'RI', label:'RI' }, { id:'VT', label:'VT' },
  ]},
  { label: 'South', states: [
    { id:'AL', label:'AL' }, { id:'AR', label:'AR' },
    { id:'FL', label:'FL', native:true }, { id:'GA', label:'GA' },
    { id:'KY', label:'KY' }, { id:'LA', label:'LA' }, { id:'MD', label:'MD' },
    { id:'MS', label:'MS' }, { id:'NC', label:'NC' }, { id:'OK', label:'OK' },
    { id:'SC', label:'SC' }, { id:'TN', label:'TN' }, { id:'TX', label:'TX', native:true },
    { id:'VA', label:'VA' }, { id:'WV', label:'WV' },
  ]},
  { label: 'Midwest', states: [
    { id:'IA', label:'IA' }, { id:'IL', label:'IL', native:true },
    { id:'IN', label:'IN' }, { id:'KS', label:'KS' }, { id:'MI', label:'MI' },
    { id:'MN', label:'MN', native:true }, { id:'MO', label:'MO' },
    { id:'ND', label:'ND' }, { id:'NE', label:'NE' }, { id:'OH', label:'OH' },
    { id:'SD', label:'SD' }, { id:'WI', label:'WI' },
  ]},
  { label: 'West', states: [
    { id:'AK', label:'AK' }, { id:'AZ', label:'AZ' }, { id:'CA', label:'CA', native:true },
    { id:'CO', label:'CO', native:true }, { id:'HI', label:'HI' },
    { id:'ID', label:'ID' }, { id:'MT', label:'MT' }, { id:'NM', label:'NM' },
    { id:'NV', label:'NV' }, { id:'OR', label:'OR' }, { id:'UT', label:'UT' },
    { id:'WA', label:'WA', native:true }, { id:'WY', label:'WY' },
  ]},
]

// Flat list for "all states" toggle and validation
const ALL_STATE_IDS = [...new Set(STATE_REGIONS.flatMap(r => r.states.map(s => s.id)))]

// Legacy flat list kept for ALL_SOURCES
const SOURCES_STATES = ALL_STATE_IDS.map(id => ({ id, label: id }))

const SOURCES_INTL = [
  { id: 'EU',     label: 'EU',           sub: 'EUR-Lex · AI Office' },
  { id: 'GB',     label: 'UK',           sub: 'Parliament · legislation.gov.uk' },
  { id: 'CA_INTL',label: 'Canada',       sub: 'OpenParl · Gazette' },
  { id: 'SG',     label: 'Singapore',    sub: 'PDPC · IMDA' },
  { id: 'IN_INTL',label: 'India',        sub: 'PIB · MEITY' },
  { id: 'BR',     label: 'Brazil',       sub: 'ANPD · Senate' },
  { id: 'JP',     label: 'Japan',        sub: 'METI RSS' },
  { id: 'KR',     label: 'South Korea',  sub: 'MSIT' },
  { id: 'AU',     label: 'Australia',    sub: 'AI Safety Standard' },
]

const ALL_SOURCES = [
  SOURCE_FEDERAL,
  { id: 'states', label: 'US States', sub: 'All 50 states' },
  ...SOURCES_STATES,
  { id: 'international', label: 'International', sub: 'EU · UK · Canada · SG · IN · BR · JP · KR · AU' },
  ...SOURCES_INTL,
]

const URGENCY_COLORS = {
  Critical: 'var(--red)',
  High:     'var(--orange)',
  Medium:   'var(--yellow)',
  Low:      'var(--green)',
}

// ── Compact source checkbox ───────────────────────────────────────────────────

function SourceChip({ src, selected, onToggle }) {
  return (
    <label style={{
      display: 'flex', alignItems: 'center', gap: 7, cursor: 'pointer',
      padding: '6px 8px',
      background: selected ? 'var(--bg-4)' : 'var(--bg-2)',
      border: `1px solid ${selected ? 'var(--accent-dim)' : 'var(--border)'}`,
      borderRadius: 'var(--radius)', transition: 'all 0.12s',
    }}>
      <input
        type="checkbox" checked={selected} onChange={onToggle}
        style={{ width: 'auto', marginTop: 0, accentColor: 'var(--accent)', flexShrink: 0 }}
      />
      <div style={{ minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{src.label}</div>
        <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{src.sub}</div>
      </div>
    </label>
  )
}

// ── State grid — compact regional layout for 50 states ──────────────────────

function StateGrid({ selectedSources, toggleSource }) {
  const [stateSearch, setStateSearch] = useState('')
  const query = stateSearch.toLowerCase()

  const allSelected  = ALL_STATE_IDS.every(id => selectedSources.includes(id))
  const someSelected = ALL_STATE_IDS.some(id => selectedSources.includes(id))

  const toggleAll = () => {
    if (allSelected) {
      // deselect all states
      ALL_STATE_IDS.forEach(id => {
        if (selectedSources.includes(id)) toggleSource(id)
      })
    } else {
      // select all states
      ALL_STATE_IDS.forEach(id => {
        if (!selectedSources.includes(id)) toggleSource(id)
      })
    }
  }

  return (
    <div style={{ marginBottom: 14 }}>
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <label style={{
          display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer',
          padding: '5px 8px',
          background: someSelected ? 'var(--bg-4)' : 'var(--bg-3)',
          border: `1px solid ${someSelected ? 'var(--accent-dim)' : 'var(--border)'}`,
          borderRadius: 'var(--radius)', flex: 1,
        }}>
          <input type="checkbox" checked={allSelected} ref={el => { if (el) el.indeterminate = someSelected && !allSelected }}
            onChange={toggleAll} style={{ width: 'auto', accentColor: 'var(--accent)', flexShrink: 0 }} />
          <div>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)' }}>US States</span>
            <span style={{ fontSize: 10, color: 'var(--text-3)', marginLeft: 6 }}>
              {someSelected ? `${ALL_STATE_IDS.filter(id => selectedSources.includes(id)).length} of 50 selected` : 'All 50 states · LegiScan'}
            </span>
          </div>
        </label>
        {/* Search filter */}
        <input
          value={stateSearch}
          onChange={e => setStateSearch(e.target.value)}
          placeholder="Filter…"
          style={{ width: 80, fontSize: 11, padding: '4px 7px', background: 'var(--bg-3)',
            border: '1px solid var(--border)', borderRadius: 'var(--radius)', color: 'var(--text)' }}
        />
      </div>

      {/* Regional grid */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {STATE_REGIONS.map(region => {
          const filtered = query
            ? region.states.filter(s => s.id.toLowerCase().includes(query) || s.label.toLowerCase().includes(query))
            : region.states
          if (filtered.length === 0) return null
          const regionAll = filtered.every(s => selectedSources.includes(s.id))
          const toggleRegion = () => filtered.forEach(s => {
            if (regionAll ? selectedSources.includes(s.id) : !selectedSources.includes(s.id))
              toggleSource(s.id)
          })
          return (
            <div key={region.label}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 3 }}>
                <button onClick={toggleRegion} style={{
                  fontSize: 9, fontFamily: 'var(--font-mono)', textTransform: 'uppercase',
                  letterSpacing: '0.05em', color: 'var(--text-3)', background: 'none',
                  border: 'none', cursor: 'pointer', padding: 0,
                }}>
                  {region.label}
                </button>
                <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
                {filtered.map(s => {
                  const sel = selectedSources.includes(s.id)
                  return (
                    <button key={s.id} onClick={() => toggleSource(s.id)} title={s.id} style={{
                      fontSize: 10, fontFamily: 'var(--font-mono)', fontWeight: 600,
                      padding: '3px 6px', borderRadius: 3, cursor: 'pointer',
                      border: `1px solid ${sel ? 'var(--accent)' : 'var(--border)'}`,
                      background: sel ? 'var(--accent-dim)' : 'var(--bg-3)',
                      color: sel ? 'var(--accent)' : s.native ? 'var(--text)' : 'var(--text-3)',
                      transition: 'all 0.1s',
                    }}>
                      {s.id}
                      {s.native && <span style={{ fontSize: 7, marginLeft: 2, verticalAlign: 'super' }}>●</span>}
                    </button>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
      {!query && (
        <div style={{ fontSize: 9, color: 'var(--text-3)', marginTop: 5, fontFamily: 'var(--font-mono)' }}>
          ● native feed &nbsp;|&nbsp; click region name to toggle all in region
        </div>
      )}
    </div>
  )
}

// ── Aggregate row (US States / International) ─────────────────────────────────

function GroupHeader({ label, sub, selected, onToggle }) {
  return (
    <label style={{
      display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer',
      padding: '7px 10px',
      background: selected ? 'var(--bg-4)' : 'var(--bg-3)',
      border: `1px solid ${selected ? 'var(--accent-dim)' : 'var(--border)'}`,
      borderRadius: 'var(--radius)', marginBottom: 6,
    }}>
      <input
        type="checkbox" checked={selected} onChange={onToggle}
        style={{ width: 'auto', accentColor: 'var(--accent)', flexShrink: 0 }}
      />
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)' }}>{label}</div>
        <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 1 }}>{sub}</div>
      </div>
    </label>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

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

  useEffect(() => {
    api.status().then(s => {
      const stats = s?.stats || {}
      const realSummaries = (stats.total_summaries || 0) - (stats.skipped_summaries || 0)
      const hasDocs = (stats.total_documents || 0) > 0
      setIsFirstRun(hasDocs && realSummaries === 0)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!running) return
    const iv = setInterval(async () => {
      try {
        const data = await api.runLog(logOffset)
        if (data?.lines?.length) {
          setLogLines(prev => [...prev, ...data.lines])
          setLogOffset(data.total)
        }
        const status = await api.runStatus()
        if (!status?.running) {
          setRunning(false)
          clearInterval(iv)
          const s2 = await api.status()
          if (s2?.last_result) setLastResult(s2.last_result)
        }
      } catch {}
    }, 1200)
    return () => clearInterval(iv)
  }, [running, logOffset])

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logLines])

  const toggleSource = id => setSelectedSources(prev =>
    prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]
  )

  const isSelected = id => selectedSources.includes(id)

  const handleRun = async () => {
    setRunning(true)
    setLogLines([])
    setLogOffset(0)
    setLastResult(null)
    try {
      await api.runAgents({
        sources: selectedSources,
        lookback_days: lookbackDays,
        summarize, run_diff: runDiff, limit,
        force_summarize: forceSummarize || isFirstRun,
        domain,
      })
      if (onJobStart) onJobStart()
    } catch (e) {
      setLogLines([`ERROR: ${e.message}`])
      setRunning(false)
    }
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1100 }}>
      <SectionHeader title="Run Agents" subtitle="Fetch and analyse regulatory documents" />

      {/* First-run banner */}
      {isFirstRun && (
        <div style={{ marginBottom: 20, padding: '12px 16px', background: 'rgba(212,168,67,0.08)', border: '1px solid rgba(212,168,67,0.3)', borderRadius: 'var(--radius)', display: 'flex', alignItems: 'flex-start', gap: 10 }}>
          <Zap size={14} style={{ color: 'var(--yellow)', marginTop: 1, flexShrink: 0 }} />
          <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5 }}>
            <strong style={{ color: 'var(--yellow)' }}>First run detected</strong> — Force Summarize will be enabled automatically so your first batch processes fully without the relevance pre-filter.
          </div>
        </div>
      )}

      {/* ── Main grid: sources (left) + options (right) ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 28, alignItems: 'start' }}>

        {/* ── Sources column ── */}
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
            Sources
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 12 }}>
            Leave all unchecked to run everything.
          </div>

          {/* Federal — single full-width chip */}
          <div style={{ marginBottom: 14 }}>
            <SourceChip
              src={SOURCE_FEDERAL}
              selected={isSelected('federal')}
              onToggle={() => toggleSource('federal')}
            />
          </div>

          {/* US States — compact regional grid */}
          <StateGrid selectedSources={selectedSources} toggleSource={toggleSource} />

          {/* International */}
          <div>
            <GroupHeader
              label="International"
              sub="EU · UK · Canada · SG · IN · BR · JP · KR · AU"
              selected={isSelected('international')}
              onToggle={() => toggleSource('international')}
            />
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 5 }}>
              {SOURCES_INTL.map(src => (
                <SourceChip
                  key={src.id}
                  src={src}
                  selected={isSelected(src.id)}
                  onToggle={() => toggleSource(src.id)}
                />
              ))}
            </div>
          </div>
        </div>

        {/* ── Options column ── */}
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
  const autoArchived = result.auto_archived ?? 0

  const rows = [
    { label: 'Fetched',    value: fetched,    sub: 'new documents',       color: 'var(--text)' },
    { label: 'Summarised', value: summarized, sub: firstRun ? 'first run — force mode' : undefined, color: 'var(--green)', link: '/documents' },
    skipped > 0 && { label: 'Skipped', value: skipped, sub: 'relevance pre-filter', color: 'var(--yellow)', link: '/documents', warn: true },
    autoArchived > 0 && { label: 'Auto-archived', value: autoArchived, sub: 'Claude score ≤ 0.15', color: 'var(--text-3)', link: '/documents' },
    totalChanges > 0 && { label: 'Changes', value: totalChanges, sub: critical > 0 ? `${critical} critical` : high > 0 ? `${high} high` : undefined, color: critical > 0 ? 'var(--red)' : high > 0 ? 'var(--orange)' : 'var(--text-2)', link: '/changes' },
  ].filter(Boolean)

  return (
    <div style={{ marginTop: 16, background: 'var(--bg-2)', border: '1px solid var(--green-dim)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      <div style={{ padding: '10px 14px', background: 'var(--green-dim)', display: 'flex', alignItems: 'center', gap: 8 }}>
        <Check size={14} style={{ color: 'var(--green)' }} />
        <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--green)' }}>Run complete</span>
        {firstRun && (
          <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--yellow)', fontFamily: 'var(--font-mono)', background: 'rgba(212,168,67,0.15)', padding: '1px 6px', borderRadius: 3 }}>
            FIRST RUN
          </span>
        )}
      </div>
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
