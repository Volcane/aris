import { useState, useEffect } from 'react'
import { Layers, Play, Star, StarOff, Trash2, ChevronDown, ChevronUp,
         AlertTriangle, CheckCircle2, TrendingUp, Globe, Plus, X, Download } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api.js'
import { Badge, Spinner, EmptyState, Modal, SectionHeader, RequirementList, DomainFilter } from '../components.jsx'

// ── API helpers ───────────────────────────────────────────────────────────────

const synthApi = {
  list:     ()          => fetch('/api/synthesis').then(r => r.json()),
  topics:   ()          => fetch('/api/synthesis/topics').then(r => r.json()),
  get:      (id)        => fetch(`/api/synthesis/${id}`).then(r => r.json()),
  run:      (payload)   => fetch('/api/synthesis', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) }).then(r => r.json()),
  star:     (id, on)    => fetch(`/api/synthesis/${id}/star?starred=${on}`, { method: 'POST' }).then(r => r.json()),
  annotate: (id, notes) => fetch(`/api/synthesis/${id}/annotate`, { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ notes }) }).then(r => r.json()),
  delete:   (id)        => fetch(`/api/synthesis/${id}`, { method: 'DELETE' }).then(r => r.json()),
}

const SEVERITY_STYLE = {
  Critical: { bg: 'rgba(224,82,82,0.12)',  color: 'var(--red)',    label: 'CRITICAL' },
  High:     { bg: 'rgba(224,131,74,0.12)', color: 'var(--orange)', label: 'HIGH'     },
  Medium:   { bg: 'rgba(212,168,67,0.12)', color: 'var(--yellow)', label: 'MEDIUM'   },
  Low:      { bg: 'rgba(82,168,120,0.08)', color: 'var(--green)',  label: 'LOW'      },
}

const CONFLICT_TYPE_COLORS = {
  'Direct Conflict':         'var(--red)',
  'Double Obligation':       'var(--orange)',
  'Definitional Divergence': 'var(--yellow)',
  'Scope Mismatch':          'var(--blue)',
  'Enforcement Gap':         'var(--text-3)',
  'Permitted vs Prohibited': 'var(--red)',
}

// ── Main view ─────────────────────────────────────────────────────────────────

export default function Synthesis() {
  const [syntheses,  setSyntheses]  = useState([])
  const [suggestions,setSuggestions]= useState([])
  const [loading,    setLoading]    = useState(true)
  const [domain,     setDomain]     = useState(() => {
    try { return localStorage.getItem('aris_domain_synthesis') ?? null } catch { return null }
  })
  const handleDomainChange = (d) => {
    setDomain(d)
    try { localStorage.setItem('aris_domain_synthesis', d ?? '') } catch {}
  }
  const [selected,   setSelected]   = useState(null)
  const [detail,     setDetail]     = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [showRun,    setShowRun]    = useState(false)
  const [running,    setRunning]    = useState(false)
  const [logLines,   setLogLines]   = useState([])
  const [logOffset,  setLogOffset]  = useState(0)

  const load = async () => {
    setLoading(true)
    try {
      const [syns, topics] = await Promise.all([
        synthApi.list(),
        synthApi.topics().catch(() => []),
      ])
      setSyntheses(Array.isArray(syns)    ? syns    : [])
      setSuggestions(Array.isArray(topics) ? topics : [])
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  // Poll log while running
  useEffect(() => {
    if (!running) return
    const id = setInterval(async () => {
      const res = await api.runLog(logOffset)
      if (res.lines?.length > 0) {
        setLogLines(prev => [...prev, ...res.lines])
        setLogOffset(res.total)
      }
      if (!res.running) {
        setRunning(false)
        clearInterval(id)
        load()
      }
    }, 1500)
    return () => clearInterval(id)
  }, [running, logOffset])

  const openDetail = async (row) => {
    setSelected(row)
    setDetail(null)
    setLoadingDetail(true)
    try { setDetail(await synthApi.get(row.id)) }
    finally { setLoadingDetail(false) }
  }

  const toggleStar = async (id, current) => {
    await synthApi.star(id, !current)
    setSyntheses(prev => prev.map(s => s.id === id ? {...s, starred: !current} : s))
    if (detail?.id === id) setDetail(d => ({...d, starred: !current}))
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this synthesis?')) return
    await synthApi.delete(id)
    if (selected?.id === id) { setSelected(null); setDetail(null) }
    load()
  }

  const handleRun = async (payload) => {
    setShowRun(false)
    setRunning(true)
    setLogLines([])
    setLogOffset(0)
    await synthApi.run(payload)
  }

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* ── Left panel: list + controls ── */}
      <div style={{ width: 340, flexShrink: 0, overflow: 'auto', padding: '28px 20px', borderRight: '1px solid var(--border)' }}>
        <div className="flex items-center justify-between" style={{ marginBottom: 20 }}>
          <div>
            <h2 style={{ fontWeight: 300, fontSize: '1.1rem' }}>Thematic Synthesis</h2>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{syntheses.length} analyses</div>
          </div>
          <button className="btn-primary btn-sm" onClick={() => setShowRun(true)}>
            <Plus size={13} /> New
          </button>
        </div>

        {/* Live log while running */}
        {running && (
          <div style={{ marginBottom: 16, padding: 12, background: 'var(--bg-3)', border: '1px solid var(--accent-dim)', borderRadius: 'var(--radius)', fontSize: 11, fontFamily: 'var(--font-mono)', maxHeight: 120, overflow: 'auto' }}>
            <div style={{ color: 'var(--accent)', marginBottom: 4 }}>⟳ Running…</div>
            {logLines.slice(-8).map((l, i) => <div key={i} style={{ color: 'var(--text-3)' }}>{l}</div>)}
          </div>
        )}

        {/* Suggested topics */}
        {suggestions.length > 0 && syntheses.length === 0 && (
          <div style={{ marginBottom: 20 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Suggested Topics</div>
            {suggestions.slice(0, 6).map(s => (
              <div key={s.topic}
                className="card card-hover"
                style={{ padding: '10px 12px', marginBottom: 6 }}
                onClick={() => setShowRun({ topic: s.topic, jurisdictions: s.jurisdictions })}
              >
                <div style={{ fontSize: 13, fontWeight: 500 }}>{s.topic}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                  {s.doc_count} docs · {s.jurisdiction_count} jurisdictions
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Synthesis list */}
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 30 }}><Spinner /></div>
        ) : syntheses.length === 0 ? (
          <EmptyState icon={Layers} title="No syntheses yet"
            message='Click "New" to run your first cross-document synthesis.' />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {syntheses.map(row => (
              <div key={row.id}
                className="card card-hover"
                style={{
                  padding: '10px 12px',
                  borderColor: selected?.id === row.id ? 'var(--accent-dim)' : 'var(--border)',
                  background: selected?.id === row.id ? 'var(--bg-3)' : 'var(--bg-2)',
                }}
                onClick={() => openDetail(row)}
              >
                <div className="flex items-center gap-2">
                  {row.starred && <Star size={11} style={{ color: 'var(--accent)', flexShrink: 0 }} />}
                  <span style={{ flex: 1, fontSize: 13, fontWeight: 500 }} className="truncate">{row.topic}</span>
                  {row.has_conflicts && (
                    <span style={{ fontSize: 10, background: 'var(--red-dim)', color: 'var(--red)', padding: '1px 5px', borderRadius: 3, fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                      {row.conflict_count} conflicts
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 3, fontFamily: 'var(--font-mono)' }}>
                  {row.docs_used} docs · {(row.jurisdictions || []).join(', ')} · {row.generated_at?.slice(0,10)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* ── Right panel: detail ── */}
      <div style={{ flex: 1, overflow: 'auto', padding: '28px 32px' }}>
        {!selected ? (
          <SynthesisPlaceholder suggestions={suggestions} onSelect={s => setShowRun({ topic: s.topic, jurisdictions: s.jurisdictions })} />
        ) : loadingDetail ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spinner size={24} /></div>
        ) : detail ? (
          <SynthesisDetail
            detail={detail}
            onStar={() => toggleStar(detail.id, detail.starred)}
            onDelete={() => handleDelete(detail.id)}
            onAnnotate={async (notes) => { await synthApi.annotate(detail.id, notes); setDetail(d => ({...d, notes})) }}
          />
        ) : null}
      </div>

      {/* ── Run modal ── */}
      {showRun && (
        <RunSynthesisModal
          initial={typeof showRun === 'object' ? showRun : {}}
          suggestions={suggestions}
          onClose={() => setShowRun(false)}
          onRun={handleRun}
        />
      )}
    </div>
  )
}

// ── Synthesis detail ──────────────────────────────────────────────────────────

function SynthesisDetail({ detail, onStar, onDelete, onAnnotate }) {
  const [showAnnotate, setShowAnnotate] = useState(false)
  const [notes,        setNotes]        = useState(detail.notes || '')
  const [activeTab,    setActiveTab]    = useState('landscape')

  const synth     = detail.synthesis  || {}
  const conflicts = detail.conflicts  || {}
  const conflictList = conflicts.conflicts || []

  const tabs = [
    { id: 'landscape', label: 'Landscape' },
    { id: 'obligations', label: `Obligations (${(synth.cumulative_obligations || []).length})` },
    { id: 'conflicts',  label: `Conflicts (${conflictList.length})`, red: conflictList.length > 0 },
    { id: 'definitions', label: 'Definitions' },
    { id: 'posture',    label: 'Posture' },
  ]

  return (
    <div className="fade-up">
      {/* Header */}
      <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
        <h2 style={{ fontWeight: 300, fontSize: '1.3rem', flex: 1, paddingRight: 16 }}>{detail.topic}</h2>
        <div className="flex gap-2">
          <a href={`/api/synthesis/${detail.id}/export`} download>
            <button className="btn-secondary btn-sm"><Download size={12} /> Export .docx</button>
          </a>
          <button className="btn-icon" title={detail.starred ? 'Unstar' : 'Star'} onClick={onStar}>
            {detail.starred
              ? <Star size={15} style={{ color: 'var(--accent)' }} />
              : <StarOff size={15} />}
          </button>
          <button className="btn-icon" onClick={() => setShowAnnotate(!showAnnotate)}>
            <span style={{ fontSize: 12 }}>Note</span>
          </button>
          <button className="btn-icon btn-danger" onClick={onDelete}><Trash2 size={14} /></button>
        </div>
      </div>

      {/* Meta */}
      <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginBottom: 20 }}>
        {detail.docs_used} documents · {(detail.jurisdictions || []).join(', ')} ·{' '}
        {detail.generated_at?.slice(0, 10)} · ID {detail.id}
      </div>

      {/* Annotation */}
      {showAnnotate && (
        <div style={{ marginBottom: 20 }}>
          <textarea
            value={notes}
            onChange={e => setNotes(e.target.value)}
            placeholder="Add notes for your team…"
            style={{ height: 80, resize: 'vertical' }}
          />
          <button className="btn-secondary btn-sm" style={{ marginTop: 6 }}
            onClick={() => { onAnnotate(notes); setShowAnnotate(false) }}>
            Save Note
          </button>
        </div>
      )}
      {detail.notes && !showAnnotate && (
        <div style={{ marginBottom: 16, padding: '10px 14px', background: 'var(--bg-3)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', fontSize: 13, color: 'var(--text-2)', fontStyle: 'italic' }}>
          {detail.notes}
        </div>
      )}

      {/* Tab bar */}
      <div className="flex gap-0" style={{ borderBottom: '1px solid var(--border)', marginBottom: 24 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            padding: '8px 16px', fontSize: 13,
            fontWeight: activeTab === t.id ? 500 : 400,
            color: t.red ? (activeTab === t.id ? 'var(--red)' : 'var(--orange)') : activeTab === t.id ? 'var(--text)' : 'var(--text-3)',
            borderBottom: activeTab === t.id ? `2px solid ${t.red ? 'var(--red)' : 'var(--accent)'}` : '2px solid transparent',
            marginBottom: -1,
          }}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'landscape'   && <LandscapeTab  synth={synth} />}
      {activeTab === 'obligations' && <ObligationsTab synth={synth} />}
      {activeTab === 'conflicts'   && <ConflictsTab  conflicts={conflicts} conflictList={conflictList} />}
      {activeTab === 'definitions' && <DefinitionsTab synth={synth} />}
      {activeTab === 'posture'     && <PostureTab     synth={synth} conflicts={conflicts} />}
    </div>
  )
}

// ── Landscape tab ─────────────────────────────────────────────────────────────

function LandscapeTab({ synth }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {synth.landscape_summary && (
        <div>
          <Label>Regulatory Landscape</Label>
          <p style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--text-2)' }}>{synth.landscape_summary}</p>
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {synth.regulatory_maturity && (
          <div className="card">
            <Label>Regulatory Maturity</Label>
            <div style={{ fontSize: 16, fontFamily: 'var(--font-display)', color: 'var(--accent)' }}>{synth.regulatory_maturity}</div>
          </div>
        )}
        {synth.enforcement_landscape?.strictest_jurisdiction && (
          <div className="card">
            <Label>Strictest Jurisdiction</Label>
            <div style={{ fontSize: 16, fontFamily: 'var(--font-display)', color: 'var(--red)' }}>
              {synth.enforcement_landscape.strictest_jurisdiction}
            </div>
            {synth.enforcement_landscape.max_penalty_summary && (
              <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>{synth.enforcement_landscape.max_penalty_summary}</div>
            )}
          </div>
        )}
      </div>
      {synth.evolution_narrative && (
        <div>
          <Label>How Regulation Is Evolving</Label>
          <p style={{ fontSize: 13, lineHeight: 1.65, color: 'var(--text-2)' }}>{synth.evolution_narrative}</p>
        </div>
      )}
      {synth.emerging_trends?.length > 0 && (
        <div>
          <Label>Emerging Trends</Label>
          {synth.emerging_trends.map((t, i) => (
            <div key={i} className="flex items-center gap-2" style={{ marginBottom: 8 }}>
              <TrendingUp size={13} style={{ color: 'var(--accent)', flexShrink: 0 }} />
              <span style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5 }}>{t}</span>
            </div>
          ))}
        </div>
      )}
      {synth.regulatory_gaps?.length > 0 && (
        <div>
          <Label>Regulatory Gaps</Label>
          {synth.regulatory_gaps.map((g, i) => (
            <div key={i} style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 6, paddingLeft: 12, borderLeft: '2px solid var(--border)' }}>{g}</div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Obligations tab ───────────────────────────────────────────────────────────

function ObligationsTab({ synth }) {
  const obligations    = synth.cumulative_obligations    || []
  const prohibitions   = synth.cumulative_prohibitions   || []

  if (!obligations.length && !prohibitions.length) return (
    <div style={{ color: 'var(--text-3)', fontStyle: 'italic', fontSize: 13 }}>No cumulative obligations identified.</div>
  )

  const universality_color = {
    'Universal':         'var(--red)',
    'Majority':          'var(--orange)',
    'Minority':          'var(--yellow)',
    'Single jurisdiction':'var(--text-3)',
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {obligations.length > 0 && (
        <>
          <Label>Mandatory Obligations ({obligations.length})</Label>
          {obligations.map((obl, i) => (
            <div key={i} style={{ padding: '12px 14px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
              <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 6 }}>{obl.obligation}</div>
              <div className="flex gap-3" style={{ flexWrap: 'wrap' }}>
                <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: universality_color[obl.universality] || 'var(--text-3)' }}>
                  {obl.universality}
                </span>
                {(obl.source_jurisdictions || []).map(j => (
                  <Badge key={j} level={j}>{j}</Badge>
                ))}
                {obl.earliest_deadline && (
                  <span style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>
                    ⚑ {obl.earliest_deadline}
                  </span>
                )}
              </div>
              {obl.applies_to && (
                <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>Applies to: {obl.applies_to}</div>
              )}
            </div>
          ))}
        </>
      )}
      {prohibitions.length > 0 && (
        <>
          <Label style={{ marginTop: 16 }}>Prohibitions ({prohibitions.length})</Label>
          {prohibitions.map((p, i) => (
            <div key={i} style={{ padding: '10px 14px', background: 'rgba(224,82,82,0.06)', border: '1px solid var(--red-dim)', borderRadius: 'var(--radius)', fontSize: 13 }}>
              <div style={{ color: 'var(--red)', fontWeight: 500 }}>{p.prohibition}</div>
              <div style={{ fontSize: 11, marginTop: 4, color: 'var(--text-3)' }}>
                {(p.source_jurisdictions || []).join(', ')}
                {p.exceptions && <span> · Exception: {p.exceptions}</span>}
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  )
}

// ── Conflicts tab ─────────────────────────────────────────────────────────────

function ConflictsTab({ conflicts, conflictList }) {
  const [expanded, setExpanded] = useState({})
  const toggle = (id) => setExpanded(p => ({...p, [id]: !p[id]}))

  if (!conflictList.length) return (
    <div className="flex items-center gap-3" style={{ color: 'var(--green)', padding: '20px 0' }}>
      <CheckCircle2 size={18} />
      <div>
        <div style={{ fontWeight: 500 }}>No material conflicts detected</div>
        {conflicts.conflict_summary && <div style={{ fontSize: 13, color: 'var(--text-3)', marginTop: 2 }}>{conflicts.conflict_summary}</div>}
      </div>
    </div>
  )

  const sorted = [...conflictList].sort((a, b) =>
    ({'Critical':0,'High':1,'Medium':2,'Low':3}[a.severity]??4) - ({'Critical':0,'High':1,'Medium':2,'Low':3}[b.severity]??4)
  )

  return (
    <div>
      {conflicts.conflict_summary && (
        <p style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 20, lineHeight: 1.65 }}>{conflicts.conflict_summary}</p>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 24 }}>
        {sorted.map(c => {
          const sev = SEVERITY_STYLE[c.severity] || SEVERITY_STYLE.Low
          const isOpen = !!expanded[c.conflict_id]
          return (
            <div key={c.conflict_id} style={{ background: sev.bg, border: `1px solid ${sev.color}44`, borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
              <div style={{ padding: '12px 16px', cursor: 'pointer' }} onClick={() => toggle(c.conflict_id)}>
                <div className="flex items-center gap-3">
                  <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: sev.color, background: sev.bg, padding: '2px 6px', borderRadius: 3, border: `1px solid ${sev.color}66`, flexShrink: 0 }}>
                    {sev.label}
                  </span>
                  <span style={{ flex: 1, fontSize: 13, fontWeight: 500 }}>{c.title}</span>
                  <span style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
                    {c.jurisdiction_a} vs {c.jurisdiction_b}
                  </span>
                  {isOpen ? <ChevronUp size={14} style={{ color: 'var(--text-3)' }} /> : <ChevronDown size={14} style={{ color: 'var(--text-3)' }} />}
                </div>
                <div style={{ fontSize: 12, color: CONFLICT_TYPE_COLORS[c.type] || 'var(--text-3)', marginTop: 4, fontFamily: 'var(--font-mono)' }}>
                  {c.type}
                </div>
              </div>
              {isOpen && (
                <div style={{ borderTop: `1px solid ${sev.color}33`, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <div style={{ padding: '10px 12px', background: 'var(--bg-3)', borderRadius: 'var(--radius)' }}>
                      <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-3)', marginBottom: 4 }}>{c.jurisdiction_a}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5 }}>{c.jurisdiction_a_position}</div>
                    </div>
                    <div style={{ padding: '10px 12px', background: 'var(--bg-3)', borderRadius: 'var(--radius)' }}>
                      <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-3)', marginBottom: 4 }}>{c.jurisdiction_b}</div>
                      <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5 }}>{c.jurisdiction_b_position}</div>
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', marginBottom: 4 }}>Conflict</div>
                    <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.65 }}>{c.conflict_description}</p>
                  </div>
                  {c.practical_impact && (
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', marginBottom: 4 }}>Practical Impact</div>
                      <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.65 }}>{c.practical_impact}</p>
                    </div>
                  )}
                  {c.resolution_options?.length > 0 && (
                    <div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', marginBottom: 4 }}>Resolution Options</div>
                      {c.resolution_options.map((opt, i) => (
                        <div key={i} style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 4, paddingLeft: 12, borderLeft: '2px solid var(--border)' }}>{opt}</div>
                      ))}
                    </div>
                  )}
                  {c.safest_approach && (
                    <div style={{ padding: '8px 12px', background: 'var(--green-dim)', border: '1px solid var(--green)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--green)' }}>
                      ✓ Safest approach: {c.safest_approach}
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Harmonised areas */}
      {conflicts.harmonised_areas?.length > 0 && (
        <div>
          <Label>Areas of Jurisdictional Alignment</Label>
          {conflicts.harmonised_areas.map((h, i) => (
            <div key={i} style={{ marginBottom: 8, padding: '8px 12px', background: 'var(--green-dim)', border: '1px solid var(--green-dim)', borderRadius: 'var(--radius)' }}>
              <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--green)' }}>{h.area}</div>
              <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{(h.jurisdictions||[]).join(', ')} · {h.description}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Definitions tab ───────────────────────────────────────────────────────────

function DefinitionsTab({ synth }) {
  const defs = synth.key_definitions_compared || []
  if (!defs.length) return <div style={{ color: 'var(--text-3)', fontSize: 13, fontStyle: 'italic' }}>No cross-jurisdiction definition comparisons in this synthesis.</div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {defs.map((d, i) => (
        <div key={i} className="card">
          <div style={{ fontSize: 14, fontWeight: 500, marginBottom: 12 }}>{d.term}</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
            {Object.entries(d.definitions || {}).map(([jur, def]) => (
              <div key={jur} style={{ display: 'grid', gridTemplateColumns: '80px 1fr', gap: 8 }}>
                <Badge level={jur}>{jur}</Badge>
                <span style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.5 }}>{def}</span>
              </div>
            ))}
          </div>
          {d.practical_implication && (
            <div style={{ fontSize: 12, color: 'var(--accent)', borderTop: '1px solid var(--border)', paddingTop: 8 }}>
              ⚑ {d.practical_implication}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Posture tab ───────────────────────────────────────────────────────────────

function PostureTab({ synth, conflicts }) {
  const ranking = (conflicts.jurisdiction_risk_ranking || [])
  const hcd     = conflicts.highest_common_denominator
  const posture = synth.recommended_compliance_posture

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {posture && (
        <div>
          <Label>Recommended Compliance Posture</Label>
          <p style={{ fontSize: 14, lineHeight: 1.7, color: 'var(--text-2)', padding: '14px 16px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', borderLeft: '3px solid var(--accent)' }}>{posture}</p>
        </div>
      )}
      {hcd && (
        <div>
          <Label>Highest Common Denominator</Label>
          <p style={{ fontSize: 13, lineHeight: 1.65, color: 'var(--text-2)' }}>{hcd}</p>
          <p style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 6, fontStyle: 'italic' }}>Satisfying this standard means you satisfy all jurisdictions simultaneously.</p>
        </div>
      )}
      {ranking.length > 0 && (
        <div>
          <Label>Jurisdiction Compliance Complexity</Label>
          {ranking.map(r => (
            <div key={r.jurisdiction} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '10px 0', borderBottom: '1px solid var(--border)' }}>
              <Badge level={r.jurisdiction}>{r.jurisdiction}</Badge>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: r.compliance_complexity === 'High' ? 'var(--red)' : r.compliance_complexity === 'Medium' ? 'var(--yellow)' : 'var(--green)' }}>
                  {r.compliance_complexity} complexity
                </div>
                {r.rationale && <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2, lineHeight: 1.5 }}>{r.rationale}</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Run modal ─────────────────────────────────────────────────────────────────

function RunSynthesisModal({ initial = {}, suggestions = [], onClose, onRun }) {
  const [topic,      setTopic]      = useState(initial.topic || '')
  const [jurs,       setJurs]       = useState(initial.jurisdictions || [])
  const [days,       setDays]       = useState(365)
  const [conflicts,  setConflicts]  = useState(true)
  const [error,      setError]      = useState('')

  const ALL_JURS = ['Federal', 'PA', 'EU', 'GB', 'CA', 'JP', 'CN', 'AU']
  const toggleJur = (j) => setJurs(p => p.includes(j) ? p.filter(x => x !== j) : [...p, j])

  const submit = () => {
    if (!topic.trim()) { setError('Topic is required'); return }
    onRun({ topic: topic.trim(), jurisdictions: jurs.length ? jurs : null, days, detect_conflicts: conflicts })
  }

  return (
    <Modal title="New Thematic Synthesis" onClose={onClose} width={560}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 6 }}>Topic</label>
          <input
            placeholder='e.g. "AI in healthcare", "automated hiring decisions", "GPAI model obligations"'
            value={topic}
            onChange={e => setTopic(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()}
            autoFocus
          />
        </div>

        {suggestions.length > 0 && !topic && (
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 6 }}>Suggested topics based on your database:</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {suggestions.slice(0, 8).map(s => (
                <button key={s.topic} className="btn-secondary btn-sm" onClick={() => { setTopic(s.topic); setJurs(s.jurisdictions || []) }}>
                  {s.topic}
                </button>
              ))}
            </div>
          </div>
        )}

        <div>
          <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 8 }}>Jurisdictions (optional — leave empty for all)</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {ALL_JURS.map(j => (
              <button key={j}
                className={jurs.includes(j) ? 'btn-primary btn-sm' : 'btn-secondary btn-sm'}
                onClick={() => toggleJur(j)}>
                {j}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 6 }}>Document lookback</label>
            <select value={days} onChange={e => setDays(Number(e.target.value))}>
              <option value={90}>90 days</option>
              <option value={180}>6 months</option>
              <option value={365}>1 year</option>
              <option value={730}>2 years</option>
              <option value={3650}>All time</option>
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, paddingTop: 20 }}>
            <label className="flex items-center gap-2" style={{ fontSize: 13, cursor: 'pointer' }}>
              <input type="checkbox" checked={conflicts} onChange={e => setConflicts(e.target.checked)} style={{ width: 'auto', accentColor: 'var(--accent)' }} />
              Detect conflicts
            </label>
          </div>
        </div>

        {error && <div style={{ fontSize: 12, color: 'var(--red)' }}>{error}</div>}

        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 14, display: 'flex', gap: 10 }}>
          <button className="btn-primary" onClick={submit} style={{ flex: 1, justifyContent: 'center' }}>
            <Layers size={14} /> Run Synthesis
          </button>
          <button className="btn-ghost" onClick={onClose}>Cancel</button>
        </div>
      </div>
    </Modal>
  )
}

// ── Placeholder when nothing is selected ─────────────────────────────────────

function SynthesisPlaceholder({ suggestions, onSelect }) {
  return (
    <div style={{ maxWidth: 560 }}>
      <h2 style={{ fontWeight: 300, fontSize: '1.4rem', marginBottom: 12 }}>Cross-Document Intelligence</h2>
      <p style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.7, marginBottom: 28 }}>
        Select a synthesis from the list, or create a new one. Synthesis reads across all relevant
        documents in your database on a topic — producing a coherent regulatory landscape narrative
        and identifying specific conflicts between jurisdictions.
      </p>
      {suggestions.length > 0 && (
        <>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>
            Ready to synthesise
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {suggestions.slice(0, 6).map(s => (
              <div key={s.topic} className="card card-hover" style={{ padding: '12px 16px' }} onClick={() => onSelect(s)}>
                <div className="flex items-center gap-3">
                  <Globe size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{s.topic}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                      {s.doc_count} docs · {s.jurisdictions.join(', ')}
                      {s.has_high_urgency && ' · ⚡ Has urgent items'}
                    </div>
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--text-3)' }}>→</span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── Shared label ──────────────────────────────────────────────────────────────

function Label({ children, style }) {
  return (
    <div style={{
      fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)',
      textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10,
      ...style,
    }}>
      {children}
    </div>
  )
}
