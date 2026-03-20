import { useState, useEffect } from 'react'
import { BookOpen, Shield, AlertTriangle, Clock, ChevronDown,
         ChevronUp, ExternalLink, RefreshCw, Globe } from 'lucide-react'
import { Spinner, EmptyState, SectionHeader, Badge } from '../components.jsx'

// ── API ───────────────────────────────────────────────────────────────────────

const baselineApi = {
  all:      (p={}) => fetch('/api/baselines?' + new URLSearchParams(p)).then(r => r.json()),
  coverage: ()     => fetch('/api/baselines/coverage').then(r => r.json()),
  status:   ()     => fetch('/api/baselines/status').then(r => r.json()),
  get:      (id)   => fetch(`/api/baselines/${id}`).then(r => r.json()),
  forJur:   (jur)  => fetch(`/api/baselines/jurisdiction/${jur}`).then(r => r.json()),
}

const PRIORITY_COLOR = {
  critical: 'var(--red)',
  high:     'var(--orange)',
  medium:   'var(--yellow)',
  low:      'var(--text-3)',
}

const STATUS_STYLE = {
  'In Force':  { color: 'var(--green)',  bg: 'rgba(82,168,120,0.12)' },
  'Active':    { color: 'var(--green)',  bg: 'rgba(82,168,120,0.12)' },
  'Published': { color: 'var(--accent)', bg: 'var(--accent-dim)'     },
  'Proposed':  { color: 'var(--yellow)', bg: 'rgba(212,168,67,0.12)' },
}

// ── Main view ─────────────────────────────────────────────────────────────────

export default function Baselines({ domain }) {
  const [summaries,  setSummaries]  = useState([])
  const [coverage,   setCoverage]   = useState(null)
  const [diagStatus, setDiagStatus] = useState(null)
  const [selected,   setSelected]   = useState(null)
  const [detail,     setDetail]     = useState(null)
  const [loading,    setLoading]    = useState(true)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [jurFilter,  setJurFilter]  = useState('')

  const load = async () => {
    setLoading(true)
    try {
      const [all, cov, diag] = await Promise.all([
        baselineApi.all(domain ? { domain } : {}),
        baselineApi.coverage(),
        baselineApi.status(),
      ])
      setSummaries(Array.isArray(all) ? all : [])
      setCoverage(cov)
      setDiagStatus(diag)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const openDetail = async (b) => {
    setSelected(b)
    setDetail(null)
    setLoadingDetail(true)
    try { setDetail(await baselineApi.get(b.id)) }
    finally { setLoadingDetail(false) }
  }

  const filtered = jurFilter
    ? summaries.filter(b => b.jurisdiction === jurFilter)
    : summaries

  const jurisdictions = [...new Set(summaries.map(b => b.jurisdiction))].sort()

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Left panel */}
      <div style={{ width: 300, flexShrink: 0, borderRight: '1px solid var(--border)', overflow: 'auto', padding: '20px 16px' }}>
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontWeight: 500, fontSize: 14, marginBottom: 2 }}>Regulatory Baselines</div>
          <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
            {summaries.length} regulations · no API calls required
          </div>
          {coverage && (
            <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginTop: 4 }}>
              Last reviewed: {coverage.last_reviewed}
            </div>
          )}
        </div>

        {/* Jurisdiction filter */}
        <div style={{ display: 'flex', gap: 5, flexWrap: 'wrap', marginBottom: 14 }}>
          <button
            className={!jurFilter ? 'btn-primary btn-sm' : 'btn-secondary btn-sm'}
            onClick={() => setJurFilter('')}>All</button>
          {jurisdictions.map(j => (
            <button key={j}
              className={jurFilter === j ? 'btn-primary btn-sm' : 'btn-secondary btn-sm'}
              onClick={() => setJurFilter(j)}>{j}</button>
          ))}
        </div>

        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 30 }}><Spinner /></div>
        ) : filtered.length === 0 ? (
          <EmptyState icon={BookOpen} title="No baselines" message="Baseline files not found." />
        ) : (
          filtered.map(b => {
            const ss = STATUS_STYLE[b.status] || STATUS_STYLE['Published']
            return (
              <div key={b.id}
                className="card card-hover"
                style={{
                  marginBottom: 6, padding: '10px 12px',
                  borderColor: selected?.id === b.id ? 'var(--accent-dim)' : 'var(--border)',
                  background:  selected?.id === b.id ? 'var(--bg-3)' : 'var(--bg-2)',
                }}
                onClick={() => openDetail(b)}
              >
                <div className="flex items-center gap-2" style={{ marginBottom: 4 }}>
                  <Badge level={b.jurisdiction}>{b.jurisdiction}</Badge>
                  <span style={{ flex: 1, fontSize: 12, fontWeight: 500 }} className="truncate">{b.short_name}</span>
                </div>
                <div style={{ fontSize: 11, color: ss.color, background: ss.bg, display: 'inline-block', padding: '1px 6px', borderRadius: 3 }}>
                  {b.status}
                </div>
                {b.overview && (
                  <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 5, lineHeight: 1.4 }} className="truncate">
                    {b.overview}
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>

      {/* Right panel */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {!selected ? (
          <BaselinePlaceholder
            summaries={summaries}
            coverage={coverage}
            diagStatus={diagStatus}
            onSelect={openDetail}
          />
        ) : loadingDetail ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spinner size={24} /></div>
        ) : detail ? (
          <BaselineDetail detail={detail} />
        ) : null}
      </div>
    </div>
  )
}

// ── Baseline detail ───────────────────────────────────────────────────────────

function BaselineDetail({ detail: b }) {
  const [tab, setTab] = useState('overview')

  const hasObligations   = !!(b.obligations_by_actor
    || b.key_obligations || b.proposed_obligations
    || b.deployer_obligations || b.developer_obligations
    || b.ico_ai_obligations)
  const hasProhibited    = !!(b.prohibited_practices?.length)
  const hasTimeline      = !!(b.timeline?.length)
  const hasDefs          = !!(b.key_definitions?.length)
  const hasPenalties     = !!(b.penalty_structure)
  const hasCrossRefs     = !!(b.cross_references?.length)

  const ss = STATUS_STYLE[b.status] || STATUS_STYLE['Published']

  const tabs = [
    { id: 'overview',     label: 'Overview'           },
    { id: 'obligations',  label: 'Obligations',  show: hasObligations },
    { id: 'prohibited',   label: 'Prohibited',   show: hasProhibited  },
    { id: 'timeline',     label: 'Timeline',     show: hasTimeline    },
    { id: 'definitions',  label: 'Definitions',  show: hasDefs        },
    { id: 'penalties',    label: 'Penalties',    show: hasPenalties   },
    { id: 'crossrefs',    label: 'Related',      show: hasCrossRefs   },
  ].filter(t => t.show !== false)

  return (
    <div style={{ padding: '28px 32px', maxWidth: 900 }} className="fade-up">
      {/* Header */}
      <div style={{ marginBottom: 8 }}>
        <div className="flex items-center gap-3" style={{ marginBottom: 6 }}>
          <Badge level={b.jurisdiction}>{b.jurisdiction}</Badge>
          <span style={{ fontSize: 11, color: ss.color, background: ss.bg, padding: '2px 8px', borderRadius: 4, fontFamily: 'var(--font-mono)' }}>
            {b.status}
          </span>
          {b.priority && (
            <span style={{ fontSize: 10, color: PRIORITY_COLOR[b.priority] || 'var(--text-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              {b.priority} priority
            </span>
          )}
        </div>
        <h2 style={{ fontWeight: 300, fontSize: '1.2rem', marginBottom: 4 }}>{b.title}</h2>
        {b.official_title && b.official_title !== b.title && (
          <div style={{ fontSize: 12, color: 'var(--text-3)', fontStyle: 'italic', marginBottom: 4 }}>{b.official_title}</div>
        )}
        <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
          {[b.celex, b.citation, b.nist_identifier, b.federal_register_citation].filter(Boolean).join(' · ')}
          {b.effective_date && ` · Effective: ${b.effective_date}`}
          {b.last_reviewed && ` · Reviewed: ${b.last_reviewed}`}
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex" style={{ borderBottom: '1px solid var(--border)', marginBottom: 24, marginTop: 16 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            padding: '8px 14px', fontSize: 13,
            fontWeight: tab === t.id ? 500 : 400,
            color: tab === t.id ? 'var(--text)' : 'var(--text-3)',
            borderBottom: tab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
            marginBottom: -1,
          }}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'overview'    && <OverviewTab    b={b} />}
      {tab === 'obligations' && <ObligationsTab b={b} />}
      {tab === 'prohibited'  && <ProhibitedTab  b={b} />}
      {tab === 'timeline'    && <TimelineTab    b={b} />}
      {tab === 'definitions' && <DefinitionsTab b={b} />}
      {tab === 'penalties'   && <PenaltiesTab   b={b} />}
      {tab === 'crossrefs'   && <CrossRefsTab   b={b} />}
    </div>
  )
}

// ── Overview tab ──────────────────────────────────────────────────────────────

function OverviewTab({ b }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {b.overview && (
        <div>
          <Label>Overview</Label>
          <p style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.75 }}>{b.overview}</p>
        </div>
      )}

      {/* Quick stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px,1fr))', gap: 12 }}>
        {[
          { label: 'Prohibited Practices',    value: (b.prohibited_practices||[]).length },
          { label: 'Obligation Categories',   value: Object.keys(b.obligations_by_actor||{}).length
              || (b.key_obligations||b.proposed_obligations||b.deployer_obligations||[]).length },
          { label: 'Key Definitions',         value: (b.key_definitions||[]).length },
          { label: 'Timeline Milestones',     value: (b.timeline||[]).length },
        ].filter(s => s.value > 0).map(s => (
          <div key={s.label} className="card" style={{ textAlign: 'center' }}>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.5rem', fontWeight: 300, color: 'var(--accent)', marginBottom: 4 }}>{s.value}</div>
            <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Legislative status if present */}
      {b.legislative_status && (
        <div className="card" style={{ background: 'rgba(212,168,67,0.06)', border: '1px solid rgba(212,168,67,0.3)' }}>
          <Label>Legislative Status</Label>
          <p style={{ fontSize: 13, color: 'var(--text-2)' }}>
            <strong>{b.legislative_status.parliament_status}</strong>
            {b.legislative_status.note && <span style={{ display: 'block', marginTop: 4, color: 'var(--text-3)', fontStyle: 'italic' }}>{b.legislative_status.note}</span>}
          </p>
        </div>
      )}

      {/* Scope */}
      {b.scope && (
        <div>
          <Label>Scope</Label>
          <div className="card" style={{ padding: '12px 16px' }}>
            {b.scope.applies_to && <div style={{ fontSize: 13, marginBottom: 6 }}><strong>Applies to:</strong> {b.scope.applies_to}</div>}
            {b.scope.consequential_decisions && (
              <div>
                <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 4 }}>Consequential decisions covered:</div>
                <ul style={{ margin: 0, paddingLeft: 18 }}>
                  {(Array.isArray(b.scope.consequential_decisions)
                    ? b.scope.consequential_decisions
                    : [b.scope.consequential_decisions]
                  ).map((d, i) => (
                    <li key={i} style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 2 }}>{d}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Key directives (EO 14110 style) */}
      {b.key_directives?.length > 0 && (
        <div>
          <Label>Key Directives</Label>
          {b.key_directives.slice(0, 4).map((d, i) => (
            <div key={i} style={{ marginBottom: 10, padding: '10px 14px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
              <div className="flex items-center gap-2" style={{ marginBottom: 4 }}>
                <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--accent)' }}>{d.section}</span>
                <span style={{ fontSize: 13, fontWeight: 500 }}>{d.title}</span>
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5, margin: 0 }}>{d.description}</p>
            </div>
          ))}
        </div>
      )}

      {/* Five principles (UK style) */}
      {b.five_cross_sector_principles?.length > 0 && (
        <div>
          <Label>Five Cross-Sector Principles</Label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            {b.five_cross_sector_principles.map((p, i) => (
              <div key={i} style={{ padding: '10px 14px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--accent)', marginBottom: 4 }}>{p.principle}</div>
                <p style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5, margin: 0 }}>{p.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Obligations tab ───────────────────────────────────────────────────────────

function ObligationsTab({ b }) {
  const sections = []

  // EU AI Act style — grouped by actor
  if (b.obligations_by_actor) {
    for (const [actor, obls] of Object.entries(b.obligations_by_actor)) {
      sections.push({ label: actor.replace(/_/g, ' '), items: obls })
    }
  }

  // GDPR style — ai_relevant_provisions
  if (b.ai_relevant_provisions) {
    sections.push({ label: 'AI-relevant provisions', items: b.ai_relevant_provisions.map(p => ({
      id:          p.article,
      title:       `${p.article} — ${p.title}`,
      description: p.ai_relevance,
      obligations: p.obligations,
    })) })
  }

  // Flat obligation lists
  for (const [key, label] of [
    ['key_obligations',      'Key Obligations'],
    ['proposed_obligations', 'Proposed Obligations'],
    ['deployer_obligations', 'Deployer Obligations'],
    ['developer_obligations','Developer Obligations'],
    ['ico_ai_obligations',   'ICO / Data Protection Obligations'],
  ]) {
    if (b[key]?.length) sections.push({ label, items: b[key] })
  }

  // Private sector implications (EO 14110)
  if (b.private_sector_implications?.length) {
    sections.push({ label: 'Private Sector Implications', items: b.private_sector_implications.map((s, i) => ({ id: `ps-${i}`, title: s })) })
  }

  if (sections.length === 0) return (
    <div style={{ color: 'var(--text-3)', fontSize: 13, fontStyle: 'italic' }}>No structured obligations in this baseline.</div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {sections.map(({ label, items }) => (
        <div key={label}>
          <Label>{label}</Label>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {items.map((obl, i) => (
              <ObligationCard key={obl.id || i} obligation={obl} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function ObligationCard({ obligation: obl }) {
  const [open, setOpen] = useState(false)
  const hasDetail = obl.description || obl.obligations?.length || obl.ai_relevance

  return (
    <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
      <div
        style={{ padding: '10px 14px', cursor: hasDetail ? 'pointer' : 'default' }}
        onClick={() => hasDetail && setOpen(o => !o)}
      >
        <div className="flex items-center gap-3">
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 500 }}>
              {obl.id && <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', marginRight: 8 }}>{obl.id}</span>}
              {obl.title}
            </div>
            {obl.deadline && (
              <div style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>⚑ {obl.deadline}</div>
            )}
          </div>
          {hasDetail && (open ? <ChevronUp size={13} style={{ color: 'var(--text-3)', flexShrink: 0 }} /> : <ChevronDown size={13} style={{ color: 'var(--text-3)', flexShrink: 0 }} />)}
        </div>
      </div>
      {open && hasDetail && (
        <div style={{ borderTop: '1px solid var(--border)', padding: '10px 14px', background: 'var(--bg-3)' }}>
          {(obl.description || obl.ai_relevance) && (
            <p style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, marginBottom: obl.obligations?.length ? 8 : 0 }}>
              {obl.description || obl.ai_relevance}
            </p>
          )}
          {obl.obligations?.length > 0 && (
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {obl.obligations.map((o, i) => (
                <li key={i} style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 3 }}>{o}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

// ── Prohibited tab ────────────────────────────────────────────────────────────

function ProhibitedTab({ b }) {
  const items = b.prohibited_practices || b.prohibited_conduct || []
  if (!items.length) return (
    <div style={{ color: 'var(--text-3)', fontSize: 13, fontStyle: 'italic' }}>No explicit prohibitions listed in this baseline.</div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {items.map((p, i) => (
        <div key={i} style={{ padding: '12px 16px', background: 'rgba(224,82,82,0.07)', border: '1px solid rgba(224,82,82,0.3)', borderRadius: 'var(--radius)' }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
            <AlertTriangle size={14} style={{ color: 'var(--red)', flexShrink: 0, marginTop: 2 }} />
            <div style={{ flex: 1 }}>
              {typeof p === 'string' ? (
                <p style={{ fontSize: 13, color: 'var(--text-2)', margin: 0 }}>{p}</p>
              ) : (
                <>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--red)', marginBottom: 4 }}>{p.title}</div>
                  <p style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, margin: 0 }}>{p.description}</p>
                  <div style={{ display: 'flex', gap: 12, marginTop: 6, flexWrap: 'wrap' }}>
                    {p.applies_to    && <span style={{ fontSize: 11, color: 'var(--text-3)' }}>Applies to: {p.applies_to}</span>}
                    {p.in_force_from && <span style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>In force: {p.in_force_from}</span>}
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Timeline tab ──────────────────────────────────────────────────────────────

function TimelineTab({ b }) {
  const items = b.timeline || b.subsequent_actions || []
  if (!items.length) return (
    <div style={{ color: 'var(--text-3)', fontSize: 13, fontStyle: 'italic' }}>No timeline data in this baseline.</div>
  )

  const now = new Date().toISOString().slice(0, 10)
  return (
    <div style={{ position: 'relative', paddingLeft: 24 }}>
      <div style={{ position: 'absolute', left: 8, top: 0, bottom: 0, width: 2, background: 'var(--border)' }} />
      {items.map((item, i) => {
        const date       = item.date || item.date_introduced || ''
        const isPast     = date && date < now
        const isFuture   = date && date > now
        const dotColor   = isPast ? 'var(--green)' : isFuture ? 'var(--text-3)' : 'var(--accent)'
        return (
          <div key={i} style={{ position: 'relative', marginBottom: 20 }}>
            <div style={{ position: 'absolute', left: -20, top: 4, width: 12, height: 12, borderRadius: '50%', background: dotColor, border: '2px solid var(--bg)' }} />
            <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: isPast ? 'var(--text-3)' : 'var(--accent)', marginBottom: 2 }}>
              {date}
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-2)', fontWeight: isPast ? 400 : 500 }}>
              {item.milestone || item.action || item.title}
            </div>
            {item.significance && (
              <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2, lineHeight: 1.5 }}>{item.significance}</div>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Definitions tab ───────────────────────────────────────────────────────────

function DefinitionsTab({ b }) {
  const defs = b.key_definitions || []
  if (!defs.length) return (
    <div style={{ color: 'var(--text-3)', fontSize: 13, fontStyle: 'italic' }}>No key definitions in this baseline.</div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {defs.map((d, i) => (
        <div key={i} className="card" style={{ padding: '12px 16px' }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--accent)', marginBottom: 6 }}>{d.term}</div>
          <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.65, margin: 0 }}>{d.definition || d.description}</p>
          {d.significance && (
            <div style={{ marginTop: 8, padding: '6px 10px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--text-3)', fontStyle: 'italic', borderLeft: '3px solid var(--accent)' }}>
              {d.significance}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Penalties tab ─────────────────────────────────────────────────────────────

function PenaltiesTab({ b }) {
  const penalties = b.penalty_structure
  if (!penalties) return (
    <div style={{ color: 'var(--text-3)', fontSize: 13, fontStyle: 'italic' }}>No penalty structure in this baseline.</div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {Object.entries(penalties).map(([key, val]) => {
        if (typeof val === 'string') return (
          <div key={key} style={{ padding: '10px 14px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', fontSize: 13, color: 'var(--text-2)' }}>
            <strong>{key.replace(/_/g, ' ')}:</strong> {val}
          </div>
        )
        return (
          <div key={key} style={{ padding: '12px 16px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
            <div style={{ fontSize: 13, fontWeight: 500, textTransform: 'capitalize', marginBottom: 6 }}>
              {key.replace(/_/g, ' ')}
            </div>
            <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
              {val.max_eur && (
                <div>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.3rem', fontWeight: 300, color: 'var(--red)' }}>
                    €{(val.max_eur / 1000000).toFixed(0)}M
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>Maximum fine</div>
                </div>
              )}
              {val.max_pct_turnover && (
                <div>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.3rem', fontWeight: 300, color: 'var(--red)' }}>
                    {val.max_pct_turnover}%
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>Global turnover</div>
                </div>
              )}
              {val.civil_penalty_per_violation && (
                <div>
                  <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.3rem', fontWeight: 300, color: 'var(--orange)' }}>
                    ${val.civil_penalty_per_violation.toLocaleString()}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)' }}>Per violation</div>
                </div>
              )}
            </div>
            {val.note && <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 6, fontStyle: 'italic' }}>{val.note}</div>}
            {val.enforcement && <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>Enforcement: {val.enforcement}</div>}
          </div>
        )
      })}
    </div>
  )
}

// ── Cross-references tab ──────────────────────────────────────────────────────

function CrossRefsTab({ b }) {
  const refs = b.cross_references || []
  if (!refs.length) return (
    <div style={{ color: 'var(--text-3)', fontSize: 13, fontStyle: 'italic' }}>No cross-references in this baseline.</div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {refs.map((r, i) => (
        <div key={i} style={{ padding: '12px 16px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--accent)', marginBottom: 4 }}>{r.regulation}</div>
          <p style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.6, margin: 0 }}>{r.relevance}</p>
        </div>
      ))}
    </div>
  )
}

// ── Placeholder ───────────────────────────────────────────────────────────────

function BaselinePlaceholder({ summaries, coverage, diagStatus, onSelect }) {
  const filesOk  = diagStatus?.baselines_loaded > 0
  const dirPath  = diagStatus?.baselines_dir
  const dirExists= diagStatus?.dir_exists
  const fileCount= diagStatus?.json_file_count || 0

  if (diagStatus && !filesOk) {
    return (
      <div style={{ padding: '40px 32px', maxWidth: 580 }}>
        <div style={{ marginBottom: 8, fontSize: 16, fontWeight: 500, color: 'var(--orange)' }}>
          ⚠ Baseline files not found
        </div>
        <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7, marginBottom: 20 }}>
          The server is running but cannot find the baseline JSON files.
          This is almost always a folder placement issue.
        </p>

        <div style={{ marginBottom: 20, padding: '12px 16px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          <div style={{ color: 'var(--text-3)', marginBottom: 6 }}>Server is looking in:</div>
          <div style={{ color: dirExists ? 'var(--green)' : 'var(--red)', wordBreak: 'break-all', marginBottom: 8 }}>
            {dirPath || 'unknown path'}
          </div>
          <div style={{ color: 'var(--text-3)', display: 'flex', gap: 20 }}>
            <span>Folder exists: <span style={{ color: dirExists ? 'var(--green)' : 'var(--red)' }}>{dirExists ? 'Yes' : 'No'}</span></span>
            {dirExists && <span>JSON files: <span style={{ color: fileCount >= 19 ? 'var(--green)' : 'var(--orange)' }}>{fileCount} of 20</span></span>}
          </div>
        </div>

        <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 2 }}>
          <strong>Fix:</strong>
          <ol style={{ marginTop: 6, paddingLeft: 20 }}>
            <li>In your <code style={{ background:'var(--bg-3)',padding:'1px 5px',borderRadius:3 }}>ai-reg-tracker/</code> project root, create a folder: <code style={{ background:'var(--bg-3)',padding:'1px 5px',borderRadius:3 }}>data/baselines/</code></li>
            <li>Copy <strong>all 20 JSON files</strong> from the outputs into that folder — <code style={{ background:'var(--bg-3)',padding:'1px 5px',borderRadius:3 }}>index.json</code> plus the 19 regulation files</li>
            <li>Restart <code style={{ background:'var(--bg-3)',padding:'1px 5px',borderRadius:3 }}>python server.py</code></li>
          </ol>
        </div>

        <div style={{ marginTop: 20, padding: '10px 14px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--text-3)' }}>
          Full diagnostic: <a href="/api/baselines/status" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>/api/baselines/status</a>
        </div>
      </div>
    )
  }

  const byJur = {}
  summaries.forEach(b => {
    const j = b.jurisdiction
    if (!byJur[j]) byJur[j] = []
    byJur[j].push(b)
  })

  return (
    <div style={{ padding: '40px 32px', maxWidth: 560 }}>
      <BookOpen size={32} style={{ color: 'var(--accent)', marginBottom: 16 }} />
      <h2 style={{ fontWeight: 300, fontSize: '1.4rem', marginBottom: 12 }}>Regulatory Baselines</h2>
      <p style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.7, marginBottom: 28 }}>
        The settled body of AI law, authored once and shipped with ARIS. No API calls required —
        all 19 baselines load from local JSON files. Select any regulation in the sidebar to browse
        its obligations, prohibited practices, compliance timeline, key definitions, and penalties.
      </p>

      {coverage && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px,1fr))', gap: 12, marginBottom: 16 }}>
          {Object.entries(coverage.by_jurisdiction || {}).map(([jur, regs]) => (
            <div key={jur} className="card" style={{ padding: '12px 16px' }}>
              <div className="flex items-center gap-2" style={{ marginBottom: 8 }}>
                <Badge level={jur}>{jur}</Badge>
                <span style={{ fontSize: 12, color: 'var(--text-3)' }}>{regs.length} baseline{regs.length !== 1 ? 's' : ''}</span>
              </div>
              {regs.map((name, i) => (
                <div key={i} style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 2 }} className="truncate">{name}</div>
              ))}
            </div>
          ))}
        </div>
      )}

      <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
        {summaries.length} baselines loaded · select one from the left panel to begin
      </div>
    </div>
  )
}

// ── Shared label ──────────────────────────────────────────────────────────────

function Label({ children }) {
  return (
    <div style={{
      fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)',
      textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10,
    }}>
      {children}
    </div>
  )
}
