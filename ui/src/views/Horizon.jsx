import { useState, useEffect, useCallback } from 'react'
import {
  CalendarDays, RefreshCw, X, ExternalLink,
  ChevronDown, ChevronUp, Clock, Zap,
} from 'lucide-react'
import { Spinner, EmptyState, Badge } from '../components.jsx'

// ── API ───────────────────────────────────────────────────────────────────────

const horizonApi = {
  items:   (p)   => fetch(`/api/horizon?${new URLSearchParams(p)}`).then(r => r.json()),
  stats:   ()    => fetch('/api/horizon/stats').then(r => r.json()),
  fetch:   ()    => fetch('/api/horizon/fetch', { method: 'POST' }).then(r => r.json()),
  dismiss: (id)  => fetch(`/api/horizon/${id}/dismiss`, { method: 'POST' }).then(r => r.json()),
  runLog:  (off) => fetch(`/api/run/log?offset=${off}`).then(r => r.json()),
}

// ── Stage config ──────────────────────────────────────────────────────────────

const STAGE_STYLE = {
  'planned':         { color: 'var(--text-3)',  bg: 'var(--bg-3)',               label: 'Planned'           },
  'pre-rule':        { color: 'var(--accent)',  bg: 'var(--accent-dim)',          label: 'Pre-Rule'          },
  'proposed':        { color: 'var(--yellow)',  bg: 'rgba(212,168,67,0.12)',      label: 'Proposed Rule'     },
  'hearing':         { color: 'var(--orange)',  bg: 'rgba(224,131,74,0.12)',      label: 'Hearing Scheduled' },
  'final':           { color: 'var(--red)',     bg: 'rgba(224,82,82,0.10)',       label: 'Final Rule Pending'},
  'enacted':         { color: 'var(--green)',   bg: 'rgba(82,168,120,0.12)',      label: 'Enacted'           },
}

const SOURCE_LABEL = {
  unified_agenda:    'Unified Regulatory Agenda',
  congress_hearings: 'Congressional Hearing',
  eu_work_programme: 'EU Work Programme',
  uk_upcoming:       'UK Parliament',
}

const ALL_STAGES = Object.keys(STAGE_STYLE)
const ALL_JURS   = ['Federal','EU','GB','CA','IL','CO','NY']

// ── Main view ─────────────────────────────────────────────────────────────────

export default function Horizon({ domain }) {
  const [items,    setItems]    = useState([])
  const [stats,    setStats]    = useState(null)
  const [loading,  setLoading]  = useState(true)
  const [fetching, setFetching] = useState(false)
  const [logLines, setLogLines] = useState([])
  const [logOffset,setLogOffset]= useState(0)
  const [jurFilter,setJurFilter]= useState('')
  const [stgFilter,setStgFilter]= useState('')
  const [view,     setView]     = useState('timeline') // timeline | list

  const load = useCallback(async () => {
    setLoading(true)
    const params = {}
    if (jurFilter) params.jurisdiction = jurFilter
    if (stgFilter) params.stage        = stgFilter
    try {
      const [its, st] = await Promise.all([
        horizonApi.items({ ...params, ...(domain ? { domain } : {}) }),
        horizonApi.stats(),
      ])
      setItems(Array.isArray(its) ? its : [])
      setStats(st)
    } finally { setLoading(false) }
  }, [jurFilter, stgFilter, domain])

  useEffect(() => { load() }, [load])

  // Poll while fetching
  useEffect(() => {
    if (!fetching) return
    const id = setInterval(async () => {
      const res = await horizonApi.runLog(logOffset)
      if (res.lines?.length) {
        setLogLines(p => [...p, ...res.lines])
        setLogOffset(res.total)
      }
      if (!res.running) {
        setFetching(false)
        clearInterval(id)
        load()
      }
    }, 1500)
    return () => clearInterval(id)
  }, [fetching, logOffset, load])

  const triggerFetch = async () => {
    setFetching(true)
    setLogLines([])
    setLogOffset(0)
    await horizonApi.fetch()
  }

  const dismiss = async (id) => {
    await horizonApi.dismiss(id)
    setItems(prev => prev.filter(i => i.id !== id))
    setStats(prev => prev ? { ...prev, total: (prev.total || 1) - 1 } : prev)
  }

  const grouped = groupByMonth(items)
  const hasItems = items.length > 0

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1000 }}>
      {/* Header */}
      <div className="flex items-start justify-between" style={{ marginBottom: 24 }}>
        <div>
          <h2 style={{ fontWeight: 300, fontSize: '1.4rem', marginBottom: 4 }}>
            Regulatory Horizon
          </h2>
          <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
            Planned and advancing regulations — before they publish
          </div>
        </div>
        <button className="btn-primary btn-sm" onClick={triggerFetch} disabled={fetching || loading}>
          <RefreshCw size={12} style={{ animation: fetching ? 'spin 1s linear infinite' : 'none' }} />
          {fetching ? 'Scanning…' : 'Scan Sources'}
        </button>
      </div>

      {/* Live log */}
      {fetching && (
        <div style={{ marginBottom: 16, padding: '8px 12px', background: 'var(--bg-3)', border: '1px solid var(--accent-dim)', borderRadius: 'var(--radius)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
          <div style={{ color: 'var(--accent)', marginBottom: 4 }}>⟳ Scanning regulatory calendars…</div>
          {logLines.slice(-4).map((l, i) => <div key={i} style={{ color: 'var(--text-3)' }}>{l}</div>)}
        </div>
      )}

      {/* Stats row */}
      {stats && (
        <div className="flex gap-3" style={{ marginBottom: 20, flexWrap: 'wrap' }}>
          {[
            { label: 'Total Items',    value: stats.total            || 0 },
            { label: 'Next 90 Days',   value: stats.upcoming_90_days || 0, color: 'var(--orange)' },
            ...Object.entries(stats.by_jurisdiction || {}).slice(0, 3).map(([j, n]) => ({ label: j, value: n })),
          ].map(s => (
            <div key={s.label} className="card" style={{ flex: '1 1 110px', padding: '10px 13px' }}>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 300, color: s.color || 'var(--text)', marginBottom: 1 }}>{s.value}</div>
              <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filters + view toggle */}
      <div className="flex gap-2 items-center" style={{ marginBottom: 20, flexWrap: 'wrap' }}>
        <select value={jurFilter} onChange={e => setJurFilter(e.target.value)} style={{ fontSize: 11, padding: '3px 8px', height: 28 }}>
          <option value="">All jurisdictions</option>
          {ALL_JURS.map(j => <option key={j} value={j}>{j}</option>)}
        </select>
        <select value={stgFilter} onChange={e => setStgFilter(e.target.value)} style={{ fontSize: 11, padding: '3px 8px', height: 28 }}>
          <option value="">All stages</option>
          {ALL_STAGES.map(s => <option key={s} value={s}>{STAGE_STYLE[s]?.label || s}</option>)}
        </select>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
          {['timeline','list'].map(v => (
            <button key={v} onClick={() => setView(v)}
              className={view === v ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
              style={{ fontSize: 11, textTransform: 'capitalize' }}>{v}</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spinner size={22} /></div>
      ) : !hasItems ? (
        <HorizonEmptyState onFetch={triggerFetch} />
      ) : view === 'timeline' ? (
        <TimelineView grouped={grouped} onDismiss={dismiss} />
      ) : (
        <ListView items={items} onDismiss={dismiss} />
      )}
    </div>
  )
}

// ── Timeline view ─────────────────────────────────────────────────────────────

function TimelineView({ grouped, onDismiss }) {
  const now = new Date()

  return (
    <div>
      {grouped.map(({ monthLabel, monthDate, items }) => {
        const isPast   = monthDate < now
        const isNow    = !isPast && monthDate < new Date(now.getFullYear(), now.getMonth() + 2, 1)
        return (
          <div key={monthLabel} style={{ marginBottom: 28 }}>
            {/* Month header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <div style={{
                width: 12, height: 12, borderRadius: '50%', flexShrink: 0,
                background: isPast ? 'var(--text-3)' : isNow ? 'var(--orange)' : 'var(--accent)',
                border: '2px solid var(--bg)',
                boxShadow: isNow ? '0 0 0 2px var(--orange)' : 'none',
              }} />
              <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
              <div style={{
                fontSize: 11, fontFamily: 'var(--font-mono)', fontWeight: 600,
                color: isPast ? 'var(--text-3)' : isNow ? 'var(--orange)' : 'var(--accent)',
                textTransform: 'uppercase', letterSpacing: '0.08em',
                flexShrink: 0,
              }}>
                {monthLabel}
                {isNow && <span style={{ marginLeft: 6, background: 'var(--orange)', color: 'var(--bg)', padding: '1px 5px', borderRadius: 3, fontSize: 9 }}>NEXT</span>}
              </div>
            </div>

            {/* Items in this month */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingLeft: 24 }}>
              {items.map(item => (
                <HorizonCard key={item.id} item={item} onDismiss={onDismiss} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── List view ─────────────────────────────────────────────────────────────────

function ListView({ items, onDismiss }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {items.map(item => <HorizonCard key={item.id} item={item} onDismiss={onDismiss} />)}
    </div>
  )
}

// ── Horizon card ──────────────────────────────────────────────────────────────

function HorizonCard({ item, onDismiss }) {
  const [open, setOpen] = useState(false)
  const ss = STAGE_STYLE[item.stage] || STAGE_STYLE['planned']
  const daysUntil = item.anticipated_date
    ? Math.round((new Date(item.anticipated_date) - new Date()) / 86400000)
    : null

  return (
    <div style={{
      background: 'var(--bg-2)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', overflow: 'hidden',
      borderLeft: `3px solid ${ss.color}`,
    }}>
      <div style={{ padding: '10px 14px', cursor: 'pointer' }}
           onClick={() => setOpen(o => !o)}>
        <div className="flex items-center gap-3">
          {/* Stage badge */}
          <span style={{
            fontSize: 10, padding: '2px 6px', borderRadius: 3, flexShrink: 0,
            background: ss.bg, color: ss.color, fontFamily: 'var(--font-mono)',
          }}>
            {ss.label}
          </span>

          {/* Title */}
          <span style={{ flex: 1, fontSize: 13, fontWeight: 500 }} className="truncate">
            {item.title}
          </span>

          {/* Jurisdiction */}
          <Badge level={item.jurisdiction}>{item.jurisdiction}</Badge>

          {/* Countdown */}
          {daysUntil !== null && (
            <span style={{
              fontSize: 11, fontFamily: 'var(--font-mono)', flexShrink: 0,
              color: daysUntil < 30 ? 'var(--red)' : daysUntil < 90 ? 'var(--orange)' : 'var(--text-3)',
            }}>
              {daysUntil < 0
                ? `${Math.abs(daysUntil)}d ago`
                : daysUntil === 0 ? 'Today'
                : `${daysUntil}d`}
            </span>
          )}

          {open
            ? <ChevronUp  size={13} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
            : <ChevronDown size={13} style={{ color: 'var(--text-3)', flexShrink: 0 }} />}

          {/* Dismiss */}
          <button
            className="btn-icon"
            onClick={e => { e.stopPropagation(); onDismiss(item.id) }}
            title="Dismiss"
            style={{ opacity: 0.5, flexShrink: 0 }}
          >
            <X size={12} />
          </button>
        </div>

        {/* Subtitle row */}
        <div style={{ display: 'flex', gap: 10, marginTop: 4, fontSize: 11, color: 'var(--text-3)', paddingLeft: 2 }}>
          {item.agency && <span>{item.agency}</span>}
          {item.anticipated_date && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <Clock size={10} />
              {item.anticipated_date.slice(0, 10)}
            </span>
          )}
          <span style={{ opacity: 0.7 }}>{SOURCE_LABEL[item.source] || item.source}</span>
          {item.ai_score > 0 && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 2, opacity: 0.6 }}>
              <Zap size={9} />
              {Math.round(item.ai_score * 100)}%
            </span>
          )}
        </div>
      </div>

      {open && (
        <div style={{ borderTop: '1px solid var(--border)', padding: '10px 14px', background: 'var(--bg-3)' }}>
          {item.description && (
            <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.65, margin: '0 0 10px' }}>
              {item.description}
            </p>
          )}
          {item.url && (
            <a href={item.url} target="_blank" rel="noreferrer"
               style={{ fontSize: 12, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 4 }}>
              <ExternalLink size={11} /> View source
            </a>
          )}
        </div>
      )}
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────

function HorizonEmptyState({ onFetch }) {
  return (
    <div style={{ maxWidth: 480 }}>
      <CalendarDays size={32} style={{ color: 'var(--accent)', marginBottom: 16 }} />
      <h3 style={{ fontWeight: 400, fontSize: '1.1rem', marginBottom: 12 }}>No horizon items yet</h3>
      <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7, marginBottom: 24 }}>
        Horizon scanning monitors forward-looking regulatory calendars — the Unified
        Regulatory Agenda, congressional committee hearings, EU Work Programme, and
        UK Parliament upcoming business. Click Scan Sources to fetch the latest entries.
      </p>
      <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7, marginBottom: 24 }}>
        Items are filtered by AI relevance using keyword scoring — only regulations likely
        to affect AI systems appear here. No Claude API calls are used.
      </p>
      <button className="btn-primary" onClick={onFetch}>
        <RefreshCw size={13} /> Scan Sources Now
      </button>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function groupByMonth(items) {
  const groups = {}
  const noDate = []

  for (const item of items) {
    if (!item.anticipated_date) {
      noDate.push(item)
      continue
    }
    const d     = new Date(item.anticipated_date)
    const key   = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
    const label = d.toLocaleString('en-US', { month: 'long', year: 'numeric' })
    if (!groups[key]) groups[key] = { monthLabel: label, monthDate: new Date(d.getFullYear(), d.getMonth(), 1), items: [] }
    groups[key].items.push(item)
  }

  const sorted = Object.entries(groups)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([, v]) => v)

  if (noDate.length) {
    sorted.push({ monthLabel: 'Date Unknown', monthDate: new Date(9999, 0), items: noDate })
  }

  return sorted
}
