import { useState, useEffect } from 'react'
import {
  Building2, Plus, Trash2, Play, Star, StarOff,
  ChevronDown, ChevronUp, AlertTriangle, CheckCircle2,
  Edit3, RefreshCw, X, Bot, Shield, BarChart3, ListChecks, Download
} from 'lucide-react'
import { Spinner, EmptyState, SectionHeader, Badge, DomainFilter } from '../components.jsx'

// ── API helpers ───────────────────────────────────────────────────────────────

const gapApi = {
  profiles:     ()        => fetch('/api/profiles').then(r => r.json()),
  getProfile:   (id)      => fetch(`/api/profiles/${id}`).then(r => r.json()),
  saveProfile:  (data)    => fetch('/api/profiles', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(data),
  }).then(r => r.json()),
  deleteProfile:(id)      => fetch(`/api/profiles/${id}`, { method: 'DELETE' }).then(r => r.json()),
  analyses:     (pid)     => fetch(`/api/gap-analyses${pid ? `?profile_id=${pid}` : ''}`).then(r => r.json()),
  getAnalysis:  (id)      => fetch(`/api/gap-analyses/${id}`).then(r => r.json()),
  runAnalysis:  (payload) => fetch('/api/gap-analyses', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify(payload),
  }).then(r => r.json()),
  starAnalysis: (id, on)  => fetch(`/api/gap-analyses/${id}/star?starred=${on}`, { method: 'POST' }).then(r => r.json()),
  annotate:     (id, n)   => fetch(`/api/gap-analyses/${id}/annotate`, {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ notes: n }),
  }).then(r => r.json()),
  runLog:       (offset)  => fetch(`/api/run/log?offset=${offset}`).then(r => r.json()),
  register:     (jurs, mode='fast') =>
    fetch(`/api/register?jurisdictions=${encodeURIComponent(jurs.join(','))}&mode=${mode}`)
      .then(r => r.json()),
  refreshRegister: (jurs, mode='full') =>
    fetch('/api/register/refresh', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ jurisdictions: jurs, mode }),
    }).then(r => r.json()),
}

const SEVERITY_STYLE = {
  Critical: { bg: 'rgba(224,82,82,0.12)',  color: 'var(--red)',    dot: '#e05252' },
  High:     { bg: 'rgba(224,131,74,0.12)', color: 'var(--orange)', dot: '#e0834a' },
  Medium:   { bg: 'rgba(212,168,67,0.12)', color: 'var(--yellow)', dot: '#d4a843' },
  Low:      { bg: 'rgba(82,168,120,0.08)', color: 'var(--green)',  dot: '#52a878' },
}

const INDUSTRIES = [
  'Healthcare', 'Finance & Banking', 'Insurance', 'HR & Recruiting',
  'Legal', 'Education', 'Government', 'Retail & E-commerce',
  'Marketing & Advertising', 'Transportation & Logistics',
  'Manufacturing', 'Technology', 'Media & Entertainment', 'Other',
]

const SIZES = ['Startup (<50)', 'SME (50-250)', 'Mid-market (250-1000)',
               'Enterprise (1000-10000)', 'Large Enterprise (10000+)']

const ALL_JURS = ['Federal','EU','GB','CA','PA','VA','NY','TX','JP','CN','AU','SG']

const DATA_TYPES = [
  'Personal data (PII)', 'Biometric data', 'Health/medical data',
  'Financial data', 'Employment data', 'Children\'s data',
  'Location data', 'Behavioral/inferred data', 'Public data only',
]

const DEPLOYMENT = ['development', 'testing', 'production', 'decommissioned']
const AUTONOMY   = ['fully automated', 'human-in-loop', 'advisory only']

// ── Main view ─────────────────────────────────────────────────────────────────

export default function GapAnalysis() {
  const [profiles,   setProfiles]   = useState([])
  const [analyses,   setAnalyses]   = useState([])
  const [selected,   setSelected]   = useState(null)   // profile or analysis selected
  const [view,       setView]       = useState('list') // list | edit | results
  const [loading,    setLoading]    = useState(true)
  const [running,    setRunning]    = useState(false)
  const [logLines,   setLogLines]   = useState([])
  const [logOffset,  setLogOffset]  = useState(0)
  const [lastResult, setLastResult] = useState(null)
  const [domain,     setDomain]     = useState(() => {
    try { return localStorage.getItem('aris_domain_gap') ?? null } catch { return null }
  })
  const handleDomainChange = (d) => {
    setDomain(d)
    try { localStorage.setItem('aris_domain_gap', d ?? '') } catch {}
  }

  const load = async () => {
    setLoading(true)
    try {
      const [profs, ans] = await Promise.all([gapApi.profiles(), gapApi.analyses()])
      setProfiles(Array.isArray(profs) ? profs : [])
      setAnalyses(Array.isArray(ans)   ? ans   : [])
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  // Poll while running
  useEffect(() => {
    if (!running) return
    const id = setInterval(async () => {
      const res = await gapApi.runLog(logOffset)
      if (res.lines?.length) {
        setLogLines(p => [...p, ...res.lines])
        setLogOffset(res.total)
      }
      if (!res.running) {
        setRunning(false)
        clearInterval(id)
        setLastResult(res.last_result)
        await load()
        // Auto-open newest analysis
        if (res.last_result?.analysis_id) {
          openAnalysis(res.last_result.analysis_id)
        }
      }
    }, 1500)
    return () => clearInterval(id)
  }, [running, logOffset])

  const openAnalysis = async (id) => {
    const a = await gapApi.getAnalysis(id)
    setSelected(a)
    setView('results')
  }

  const runAnalysis = async (profileId, opts = {}) => {
    setRunning(true); setLogLines([]); setLogOffset(0); setLastResult(null)
    await gapApi.runAnalysis({ profile_id: profileId, domain: domain || undefined, ...opts })
  }

  const editProfile = (profile) => {
    setSelected(profile)
    setView('edit')
  }

  const newProfile = () => {
    setSelected(null)
    setView('edit')
  }

  const onSaved = async (profile) => {
    await load()
    setSelected(profile)
    setView('list')
  }

  // Left panel: profile + analysis list
  const leftPanel = (
    <div style={{ width: 300, flexShrink: 0, borderRight: '1px solid var(--border)', overflow: 'auto', padding: '20px 16px' }}>
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <div>
            <div style={{ fontWeight: 500, fontSize: 14 }}>Gap Analysis</div>
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{profiles.length} profiles</div>
          </div>
          <button className="btn-primary btn-sm" onClick={newProfile}><Plus size={13} /> New</button>
        </div>
        <DomainFilter domain={domain} onChange={handleDomainChange} />
        {domain && (
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 6, fontStyle: 'italic' }}>
            Analysis will focus on {domain === 'privacy' ? 'data privacy' : 'AI regulation'} documents
          </div>
        )}
      </div>

      {/* Live log */}
      {running && (
        <div style={{ marginBottom: 12, padding: '8px 10px', background: 'var(--bg-3)', border: '1px solid var(--accent-dim)', borderRadius: 'var(--radius)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
          <div style={{ color: 'var(--accent)', marginBottom: 4 }}>⟳ Analysing…</div>
          {logLines.slice(-5).map((l, i) => <div key={i} style={{ color: 'var(--text-3)' }}>{l}</div>)}
        </div>
      )}

      {loading ? <div style={{ display: 'flex', justifyContent: 'center', padding: 30 }}><Spinner /></div> : (
        <>
          {profiles.length === 0 ? (
            <EmptyState icon={Building2} title="No profiles yet"
              message='Click "New" to create your first company profile.' />
          ) : profiles.map(p => (
            <ProfileCard key={p.id} profile={p}
  analyses={analyses.filter(a => {
                if (a.profile_id !== p.id) return false
                if (!domain) return true
                // Match analysis domain if stored, otherwise show all
                return !a.domain || a.domain === domain || a.domain === 'both'
              })}
              onEdit={() => editProfile(p)}
              onRun={() => runAnalysis(p.id)}
              onOpenAnalysis={openAnalysis}
              running={running}
            />
          ))}
        </>
      )}
    </div>
  )

  // Right panel
  const rightPanel = (
    <div style={{ flex: 1, overflow: 'auto' }}>
      {view === 'list' && (
        <GapAnalysisPlaceholder onNew={newProfile} analyses={analyses} onOpen={openAnalysis} />
      )}
      {view === 'edit' && (
        <ProfileEditor
          profile={selected}
          onSave={onSaved}
          onCancel={() => setView('list')}
        />
      )}
      {view === 'results' && selected && (
        <GapResults
          analysis={selected}
          domain={domain}
          onStar={async (id, on) => { await gapApi.starAnalysis(id, on); openAnalysis(id) }}
          onAnnotate={async (id, n) => { await gapApi.annotate(id, n); openAnalysis(id) }}
          onRerun={() => runAnalysis(selected.profile_id, { jurisdictions: selected.jurisdictions })}
          running={running}
        />
      )}
    </div>
  )

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {leftPanel}
      {rightPanel}
    </div>
  )
}

// ── Profile card in sidebar ───────────────────────────────────────────────────

function ProfileCard({ profile, analyses, onEdit, onRun, onOpenAnalysis, running }) {
  const latest = analyses[0]
  return (
    <div className="card" style={{ marginBottom: 8, padding: '10px 12px' }}>
      <div className="flex items-center gap-2" style={{ marginBottom: 6 }}>
        <Building2 size={13} style={{ color: 'var(--accent)', flexShrink: 0 }} />
        <span style={{ flex: 1, fontSize: 13, fontWeight: 500 }} className="truncate">{profile.name}</span>
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 8 }}>
        {profile.industry_sector} · {(profile.ai_systems || []).length} AI system{(profile.ai_systems||[]).length !== 1 ? 's' : ''}
        {' · '}{(profile.operating_jurisdictions || []).join(', ')}
      </div>
      {latest && (
        <div
          className="flex items-center gap-2"
          style={{ marginBottom: 8, padding: '5px 8px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', cursor: 'pointer' }}
          onClick={() => onOpenAnalysis(latest.id)}
        >
          <PostureBar score={latest.posture_score} small />
          <span style={{ fontSize: 11, color: 'var(--text-3)' }}>
            {latest.gap_count} gaps · {latest.generated_at?.slice(0,10)}
          </span>
        </div>
      )}
      <div className="flex gap-2">
        <button className="btn-secondary btn-sm" onClick={onEdit} style={{ flex: 1, justifyContent: 'center' }}>
          <Edit3 size={11} /> Edit
        </button>
        <button className="btn-primary btn-sm" onClick={onRun} disabled={running} style={{ flex: 1, justifyContent: 'center' }}>
          <Play size={11} /> Analyse
        </button>
      </div>
    </div>
  )
}

// ── Gap results view ──────────────────────────────────────────────────────────

function GapResults({ analysis, domain, onStar, onAnnotate, onRerun, running }) {
  const [tab,          setTab]          = useState('gaps')
  const [expanded,     setExpanded]     = useState({})
  const [showAnnotate, setShowAnnotate] = useState(false)
  const [notes,        setNotes]        = useState(analysis.notes || '')

  const gaps   = analysis.gaps_result?.gaps           || []
  const comply = analysis.gaps_result?.compliant_areas || []
  const road   = analysis.gaps_result?.priority_roadmap || []
  const scope  = analysis.scope?.applicable_regulations || []
  const score  = analysis.posture_score ?? 0

  const sorted = [...gaps].sort((a, b) =>
    ({'Critical':0,'High':1,'Medium':2,'Low':3}[a.severity]??4) -
    ({'Critical':0,'High':1,'Medium':2,'Low':3}[b.severity]??4)
  )

  const tabs = [
    { id: 'gaps',     label: `Gaps (${gaps.length})`,            red: analysis.critical_count > 0 },
    { id: 'compliant',label: `Compliant (${comply.length})` },
    { id: 'roadmap',  label: 'Roadmap' },
    { id: 'register', label: 'Register' },
    { id: 'scope',    label: `Scope (${scope.length} regs)` },
  ]

  return (
    <div style={{ padding: '28px 32px', maxWidth: 900 }} className="fade-up">
      {/* Header */}
      <div className="flex items-start justify-between" style={{ marginBottom: 12 }}>
        <div style={{ flex: 1, paddingRight: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginBottom: 4 }}>
            {analysis.profile_name}
          </div>
          <h2 style={{ fontWeight: 300, fontSize: '1.2rem', marginBottom: 4 }}>
            Compliance Gap Analysis
          </h2>
          <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span>{analysis.docs_examined} docs examined · {(analysis.jurisdictions||[]).join(', ')} · {analysis.generated_at?.slice(0,10)}</span>
            {domain && (
              <span style={{
                fontSize: 9, padding: '1px 5px', borderRadius: 3,
                background: domain === 'privacy' ? 'rgba(124,158,247,0.15)' : 'var(--accent-glow)',
                color: domain === 'privacy' ? '#7c9ef7' : 'var(--accent)',
                border: `1px solid ${domain === 'privacy' ? '#7c9ef730' : 'var(--accent-dim)'}`,
              }}>
                {domain === 'privacy' ? 'DATA PRIVACY' : 'AI REGULATION'}
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-2 items-center">
          <button className="btn-icon" onClick={() => onStar(analysis.id, !analysis.starred)}>
            {analysis.starred
              ? <Star size={15} style={{ color: 'var(--accent)' }} />
              : <StarOff size={15} />}
          </button>
          <button className="btn-icon" onClick={() => setShowAnnotate(!showAnnotate)}>
            <span style={{ fontSize: 12 }}>Note</span>
          </button>
          <a href={`/api/gap-analyses/${analysis.id}/export`} download>
            <button className="btn-secondary btn-sm">
              <Download size={12} /> Export .docx
            </button>
          </a>
          <button className="btn-secondary btn-sm" onClick={onRerun} disabled={running}>
            <RefreshCw size={12} /> Re-run
          </button>
        </div>
      </div>

      {/* Posture score + summary */}
      <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: 20, marginBottom: 24, padding: '16px 20px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }}>
        <div style={{ textAlign: 'center', minWidth: 100 }}>
          <PostureScore score={score} />
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>Posture Score</div>
        </div>
        <div>
          <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.7 }}>
            {analysis.gaps_result?.posture_summary || 'Analysis complete.'}
          </div>
          <div className="flex gap-4" style={{ marginTop: 12 }}>
            {[
              { label: 'Critical', value: analysis.critical_count, color: 'var(--red)' },
              { label: 'Total Gaps', value: analysis.gap_count, color: 'var(--orange)' },
              { label: 'Compliant Areas', value: comply.length, color: 'var(--green)' },
              { label: 'Regulations Reviewed', value: analysis.applicable_count, color: 'var(--text-3)' },
            ].map(s => (
              <div key={s.label} style={{ textAlign: 'center' }}>
                <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem', fontWeight: 300, color: s.color }}>{s.value ?? 0}</div>
                <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase' }}>{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Annotation */}
      {showAnnotate && (
        <div style={{ marginBottom: 16 }}>
          <textarea value={notes} onChange={e => setNotes(e.target.value)} placeholder="Add notes for your team…" style={{ height: 70, resize: 'vertical' }} />
          <button className="btn-secondary btn-sm" style={{ marginTop: 6 }}
            onClick={() => { onAnnotate(analysis.id, notes); setShowAnnotate(false) }}>
            Save Note
          </button>
        </div>
      )}
      {analysis.notes && !showAnnotate && (
        <div style={{ marginBottom: 16, padding: '8px 14px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', fontSize: 13, color: 'var(--text-2)', fontStyle: 'italic', borderLeft: '3px solid var(--accent)' }}>
          {analysis.notes}
        </div>
      )}

      {/* Tabs */}
      <div className="flex" style={{ borderBottom: '1px solid var(--border)', marginBottom: 24 }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)} style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            padding: '8px 16px', fontSize: 13,
            fontWeight: tab === t.id ? 500 : 400,
            color: t.red ? (tab === t.id ? 'var(--red)' : 'var(--orange)') : tab === t.id ? 'var(--text)' : 'var(--text-3)',
            borderBottom: tab === t.id ? `2px solid ${t.red ? 'var(--red)' : 'var(--accent)'}` : '2px solid transparent',
            marginBottom: -1,
          }}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'gaps'      && <GapsTab       sorted={sorted} analysis={analysis} expanded={expanded} setExpanded={setExpanded} />}
      {tab === 'compliant' && <CompliantTab   comply={comply} />}
      {tab === 'roadmap'   && <RoadmapTab     road={road} />}
      {tab === 'register'  && <RegisterTab    jurisdictions={analysis.jurisdictions || []} />}
      {tab === 'scope'     && <ScopeTab       scope={scope} analysis={analysis} />}
    </div>
  )
}

// ── Named tab components ──────────────────────────────────────────────────────

function GapsTab({ sorted, analysis, expanded, setExpanded }) {
  if (sorted.length === 0) return (
    <div className="flex items-center gap-3" style={{ color: 'var(--green)', padding: '20px 0' }}>
      <CheckCircle2 size={20} />
      <div>
        <div style={{ fontWeight: 500 }}>No gaps identified</div>
        <div style={{ fontSize: 13, color: 'var(--text-3)', marginTop: 2 }}>
          Your stated practices satisfy all applicable obligations in the analysed documents.
        </div>
      </div>
    </div>
  )
  return (
    <div>
      {sorted.map(gap => {
        const sev  = SEVERITY_STYLE[gap.severity] || SEVERITY_STYLE.Low
        const open = !!expanded[gap.gap_id]
        return (
          <div key={gap.gap_id} style={{ marginBottom: 10, background: sev.bg, border: `1px solid ${sev.color}44`, borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
            <div style={{ padding: '12px 16px', cursor: 'pointer' }} onClick={() => setExpanded(p => ({...p, [gap.gap_id]: !p[gap.gap_id]}))}>
              <div className="flex items-center gap-3">
                <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: sev.color, background: sev.bg, padding: '2px 6px', border: `1px solid ${sev.color}66`, borderRadius: 3, flexShrink: 0 }}>
                  {(gap.severity||'').toUpperCase()}
                </span>
                <span style={{ flex: 1, fontSize: 13, fontWeight: 500 }}>{gap.title}</span>
                <Badge level={gap.jurisdiction}>{gap.jurisdiction}</Badge>
                {gap.deadline && <span style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>⚑ {gap.deadline}</span>}
                {open ? <ChevronUp size={14} style={{ color: 'var(--text-3)' }} /> : <ChevronDown size={14} style={{ color: 'var(--text-3)' }} />}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>
                {gap.regulation_title} · Effort: {gap.effort_estimate}
                {(gap.affected_systems||[]).length > 0 && ` · Affects: ${gap.affected_systems.join(', ')}`}
              </div>
            </div>
            {open && (
              <div style={{ borderTop: `1px solid ${sev.color}33`, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <GapCard label="Regulatory Obligation" content={gap.obligation} />
                  <GapCard label="Current State" content={gap.current_state} />
                </div>
                <GapCard label="Gap" content={gap.gap_description} accent="var(--red)" />
                <div style={{ padding: '10px 14px', background: 'var(--bg-4)', borderRadius: 'var(--radius)', borderLeft: '3px solid var(--accent)' }}>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', marginBottom: 4 }}>First Action</div>
                  <div style={{ fontSize: 13, color: 'var(--text-2)', fontWeight: 500 }}>{gap.first_action}</div>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
                  Source: {gap.document_id}
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function CompliantTab({ comply }) {
  if (!comply.length) return (
    <div style={{ color: 'var(--text-3)', fontSize: 13, fontStyle: 'italic' }}>No compliant areas identified in this analysis.</div>
  )
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {comply.map((c, i) => (
        <div key={i} style={{ padding: '12px 16px', background: 'rgba(82,168,120,0.06)', border: '1px solid var(--green-dim)', borderRadius: 'var(--radius)' }}>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--green)', marginBottom: 4 }}>{c.area}</div>
          <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.55 }}>{c.evidence}</div>
          {(c.document_ids||[]).length > 0 && (
            <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginTop: 4 }}>
              Satisfies: {c.document_ids.join(', ')}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function RoadmapTab({ road }) {
  if (!road.length) return (
    <div style={{ color: 'var(--text-3)', fontSize: 13, fontStyle: 'italic' }}>No roadmap generated.</div>
  )
  return (
    <div>
      {road.map((phase, i) => (
        <div key={i} style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10, fontWeight: 600 }}>
            {phase.phase}
          </div>
          {(phase.actions||[]).map((action, j) => (
            <div key={j} style={{ display: 'flex', gap: 10, marginBottom: 8, padding: '8px 12px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
              <div style={{ width: 20, height: 20, borderRadius: '50%', background: 'var(--bg-4)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontSize: 10, color: 'var(--text-3)' }}>{j+1}</div>
              <span style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5 }}>{action}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  )
}

function ScopeTab({ scope, analysis }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {scope.length === 0
        ? <div style={{ color: 'var(--text-3)', fontSize: 13, fontStyle: 'italic' }}>No scope data available.</div>
        : scope.map((reg, i) => (
          <div key={i} className="card" style={{ padding: '12px 16px' }}>
            <div className="flex items-center gap-3" style={{ marginBottom: 6 }}>
              <Badge level={reg.jurisdiction}>{reg.jurisdiction}</Badge>
              <span style={{ fontSize: 13, fontWeight: 500 }}>{reg.title}</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 8 }}>{reg.why_applicable}</div>
            {(reg.triggered_provisions||[]).map((p, j) => (
              <div key={j} style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 4, paddingLeft: 12, borderLeft: '2px solid var(--border)' }}>
                {p.provision}
                {p.deadline && <span style={{ color: 'var(--red)', marginLeft: 8 }}>⚑ {p.deadline}</span>}
              </div>
            ))}
          </div>
        ))
      }
      {analysis.scope?.coverage_note && (
        <div style={{ padding: '8px 12px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--text-3)', fontStyle: 'italic' }}>
          {analysis.scope.coverage_note}
        </div>
      )}
    </div>
  )
}

// ── Register tab ──────────────────────────────────────────────────────────────

const CATEGORY_COLORS = {
  'Prohibition':   { color: 'var(--red)',    bg: 'rgba(224,82,82,0.10)'  },
  'Assessment':    { color: 'var(--orange)', bg: 'rgba(224,131,74,0.10)' },
  'Oversight':     { color: 'var(--accent)', bg: 'var(--accent-dim)'     },
  'Transparency':  { color: 'var(--yellow)', bg: 'rgba(212,168,67,0.10)' },
  'Governance':    { color: 'var(--text-2)', bg: 'var(--bg-3)'           },
  'Documentation': { color: 'var(--text-2)', bg: 'var(--bg-3)'           },
  'Reporting':     { color: 'var(--text-2)', bg: 'var(--bg-3)'           },
  'Technical':     { color: 'var(--text-2)', bg: 'var(--bg-3)'           },
  'Rights':        { color: 'var(--green)',  bg: 'rgba(82,168,120,0.10)' },
  'Training Data': { color: 'var(--text-2)', bg: 'var(--bg-3)'           },
}

const UNIV_STYLE = {
  'Universal':            { color: 'var(--red)',    label: 'Universal'   },
  'Majority':             { color: 'var(--orange)', label: 'Majority'    },
  'Single jurisdiction':  { color: 'var(--text-3)', label: 'Single'      },
}

function RegisterTab({ jurisdictions }) {
  const [register,    setRegister]    = useState([])
  const [loading,     setLoading]     = useState(true)
  const [mode,        setMode]        = useState('fast')
  const [upgrading,   setUpgrading]   = useState(false)
  const [catFilter,   setCatFilter]   = useState('')
  const [univFilter,  setUnivFilter]  = useState('')
  const [expanded,    setExpanded]    = useState({})
  const [sortBy,      setSortBy]      = useState('category') // category | deadline | universality

  const load = async (m = mode) => {
    if (!jurisdictions.length) { setLoading(false); return }
    setLoading(true)
    try {
      const res = await gapApi.register(jurisdictions, m)
      setRegister(res.items || [])
    } catch (e) {
      console.error('Register load error', e)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [jurisdictions.join(',')])

  const upgrade = async () => {
    setUpgrading(true)
    try {
      const res = await gapApi.refreshRegister(jurisdictions, 'full')
      setRegister(res.items || [])
      setMode('full')
    } finally { setUpgrading(false) }
  }

  const categories  = [...new Set(register.map(r => r.category))].sort()
  const universalities = ['Universal','Majority','Single jurisdiction']

  const filtered = register
    .filter(r => !catFilter   || r.category    === catFilter)
    .filter(r => !univFilter  || r.universality === univFilter)
    .sort((a, b) => {
      if (sortBy === 'deadline') {
        const da = a.earliest_deadline || 'z'
        const db = b.earliest_deadline || 'z'
        return da < db ? -1 : da > db ? 1 : 0
      }
      if (sortBy === 'universality') {
        const order = { 'Universal': 0, 'Majority': 1, 'Single jurisdiction': 2 }
        return (order[a.universality]??3) - (order[b.universality]??3)
      }
      // category
      return (a.category||'').localeCompare(b.category||'') ||
             (a.title||'').localeCompare(b.title||'')
    })

  if (!jurisdictions.length) return (
    <div style={{ color: 'var(--text-3)', fontSize: 13, fontStyle: 'italic' }}>
      No jurisdictions selected for this analysis.
    </div>
  )

  return (
    <div>
      {/* Header row */}
      <div className="flex items-center justify-between" style={{ marginBottom: 16, flexWrap: 'wrap', gap: 10 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 500 }}>Consolidated Obligation Register</div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
            {loading ? 'Loading…' : `${filtered.length} of ${register.length} obligations`}
            {' · '}{jurisdictions.join(', ')}
            {mode === 'fast' && <span style={{ color: 'var(--text-3)' }}> · structural consolidation</span>}
            {mode === 'full' && <span style={{ color: 'var(--green)'  }}> · Claude-verified</span>}
          </div>
        </div>
        <div className="flex gap-2">
          {mode === 'fast' && (
            <button className="btn-secondary btn-sm" onClick={upgrade} disabled={upgrading}>
              {upgrading ? <><Spinner size={11} /> Verifying…</> : <><ListChecks size={11} /> Upgrade to Full</>}
            </button>
          )}
          <button className="btn-ghost btn-sm" onClick={() => load(mode)} disabled={loading}>
            <RefreshCw size={11} />
          </button>
        </div>
      </div>

      {/* Filters + sort */}
      <div className="flex gap-2 items-center" style={{ marginBottom: 14, flexWrap: 'wrap' }}>
        <select value={catFilter}  onChange={e => setCatFilter(e.target.value)}  style={{ fontSize: 11, padding: '3px 8px', height: 28 }}>
          <option value="">All categories</option>
          {categories.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={univFilter} onChange={e => setUnivFilter(e.target.value)} style={{ fontSize: 11, padding: '3px 8px', height: 28 }}>
          <option value="">All universality</option>
          {universalities.map(u => <option key={u} value={u}>{u}</option>)}
        </select>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: 'var(--text-3)' }}>Sort:</span>
          {['category','deadline','universality'].map(s => (
            <button key={s}
              className={sortBy === s ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
              style={{ fontSize: 11, textTransform: 'capitalize' }}
              onClick={() => setSortBy(s)}>{s}</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spinner /></div>
      ) : filtered.length === 0 ? (
        <div style={{ color: 'var(--text-3)', fontSize: 13, fontStyle: 'italic' }}>
          No obligations found for the selected filters.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {filtered.map((obl, i) => {
            const catStyle  = CATEGORY_COLORS[obl.category]  || CATEGORY_COLORS['Governance']
            const univStyle = UNIV_STYLE[obl.universality]   || UNIV_STYLE['Single jurisdiction']
            const isOpen    = !!expanded[i]
            const sources   = obl.sources || []

            return (
              <div key={i} style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
                <div style={{ padding: '10px 14px', cursor: 'pointer' }} onClick={() => setExpanded(p => ({...p, [i]: !p[i]}))}>
                  <div className="flex items-center gap-3">
                    <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 3, background: catStyle.bg, color: catStyle.color, fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                      {obl.category}
                    </span>
                    <span style={{ flex: 1, fontSize: 13, fontWeight: 500 }}>{obl.title}</span>
                    {obl.earliest_deadline && (
                      <span style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                        ⚑ {obl.earliest_deadline}
                      </span>
                    )}
                    <span style={{ fontSize: 10, color: univStyle.color, fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                      {univStyle.label}
                    </span>
                    {isOpen ? <ChevronUp size={13} style={{ color: 'var(--text-3)', flexShrink: 0 }} /> : <ChevronDown size={13} style={{ color: 'var(--text-3)', flexShrink: 0 }} />}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
                    {(obl.jurisdictions||[]).join(' · ')}
                    {sources.length > 0 && ` · ${sources.length} source${sources.length !== 1 ? 's' : ''}`}
                  </div>
                </div>
                {isOpen && (
                  <div style={{ borderTop: '1px solid var(--border)', padding: '12px 14px', background: 'var(--bg-3)', display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {obl.description && (
                      <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6, margin: 0 }}>
                        {obl.description}
                      </p>
                    )}
                    {obl.strictest_scope && obl.strictest_scope !== obl.description && (
                      <div style={{ padding: '8px 12px', background: 'var(--bg-4)', borderRadius: 'var(--radius)', borderLeft: '3px solid var(--accent)' }}>
                        <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', marginBottom: 3 }}>Strictest scope</div>
                        <div style={{ fontSize: 12, color: 'var(--text-2)' }}>{obl.strictest_scope}</div>
                      </div>
                    )}
                    {obl.notes && (
                      <div style={{ fontSize: 12, color: 'var(--text-3)', fontStyle: 'italic' }}>{obl.notes}</div>
                    )}
                    {sources.length > 0 && (
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', marginBottom: 6 }}>Sources</div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                          {sources.map((s, si) => (
                            <div key={si} className="flex items-center gap-2" style={{ fontSize: 12 }}>
                              <Badge level={s.jurisdiction}>{s.jurisdiction}</Badge>
                              <span style={{ color: 'var(--text-2)' }}>{s.regulation_title}</span>
                              {s.deadline && <span style={{ color: 'var(--red)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>⚑ {s.deadline}</span>}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Mode explanation footer */}
      <div style={{ marginTop: 16, padding: '8px 12px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', fontSize: 11, color: 'var(--text-3)', lineHeight: 1.6 }}>
        {mode === 'fast'
          ? '⚡ Structural consolidation: obligations are grouped by category and merged by title similarity. No API call. Upgrade to Full for Claude-verified semantic deduplication.'
          : '✓ Claude-verified: obligations have been semantically deduplicated and categorised. Cached for 24 hours.'}
      </div>
    </div>
  )
}

// ── Profile editor ────────────────────────────────────────────────────────────

function ProfileEditor({ profile, onSave, onCancel }) {
  const blank = {
    name: '', industry_sector: '', company_size: '',
    operating_jurisdictions: [], ai_systems: [],
    current_practices: {
      has_ai_governance_policy: null, has_risk_assessments: null,
      has_human_oversight: null, has_incident_response: null,
      has_documentation: null, has_bias_testing: null,
      has_transparency_disclosures: null, notes: '',
    },
    existing_certifications: [], primary_concerns: '', recent_changes: '',
  }

  const [form,    setForm]    = useState(profile ? {...blank, ...profile} : blank)
  const [saving,  setSaving]  = useState(false)
  const [error,   setError]   = useState('')
  const [section, setSection] = useState('identity')

  const set = (k, v) => setForm(p => ({...p, [k]: v}))
  const setPractice = (k, v) => setForm(p => ({...p, current_practices: {...p.current_practices, [k]: v}}))

  const toggleJur  = (j) => set('operating_jurisdictions',
    form.operating_jurisdictions.includes(j)
      ? form.operating_jurisdictions.filter(x => x !== j)
      : [...form.operating_jurisdictions, j])

  const toggleCert = (c) => set('existing_certifications',
    form.existing_certifications.includes(c)
      ? form.existing_certifications.filter(x => x !== c)
      : [...form.existing_certifications, c])

  const addSystem = () => set('ai_systems', [
    ...form.ai_systems,
    { name: '', description: '', purpose: '', data_inputs: [], affected_population: '', deployment_status: 'production', autonomy_level: 'human-in-loop' },
  ])

  const updateSystem = (i, k, v) => set('ai_systems',
    form.ai_systems.map((s, idx) => idx === i ? {...s, [k]: v} : s))

  const removeSystem = (i) => set('ai_systems', form.ai_systems.filter((_, idx) => idx !== i))

  const toggleDataInput = (sysIdx, type) => {
    const sys  = form.ai_systems[sysIdx]
    const data = sys.data_inputs.includes(type)
      ? sys.data_inputs.filter(x => x !== type)
      : [...sys.data_inputs, type]
    updateSystem(sysIdx, 'data_inputs', data)
  }

  const save = async () => {
    if (!form.name.trim())  { setError('Name is required'); return }
    if (!form.operating_jurisdictions.length) { setError('Select at least one jurisdiction'); return }
    setSaving(true); setError('')
    try {
      const saved = await gapApi.saveProfile({...form, id: profile?.id})
      onSave(saved)
    } catch (e) { setError(String(e)) }
    finally { setSaving(false) }
  }

  const SECTIONS = [
    { id: 'identity',   label: 'Identity',    icon: Building2 },
    { id: 'systems',    label: 'AI Systems',  icon: Bot },
    { id: 'practices',  label: 'Practices',   icon: Shield },
  ]

  return (
    <div style={{ padding: '28px 32px', maxWidth: 780 }}>
      <SectionHeader
        title={profile ? `Edit: ${profile.name}` : 'New Company Profile'}
        subtitle="Fill in details about your company and AI systems. The more specific, the better the gap analysis."
      />

      {/* Section tabs */}
      <div className="flex gap-2" style={{ marginBottom: 24, borderBottom: '1px solid var(--border)', paddingBottom: 0 }}>
        {SECTIONS.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setSection(id)} style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            padding: '8px 16px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6,
            fontWeight: section === id ? 500 : 400,
            color: section === id ? 'var(--text)' : 'var(--text-3)',
            borderBottom: section === id ? '2px solid var(--accent)' : '2px solid transparent',
            marginBottom: -1,
          }}>
            <Icon size={13} />{label}
          </button>
        ))}
      </div>

      {/* Identity */}
      {section === 'identity' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Profile name <span style={{ color: 'var(--red)' }}>*</span></label>
            <input value={form.name} onChange={e => set('name', e.target.value)} placeholder="e.g. Acme Corp — Healthcare Division" />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
            <div>
              <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Industry sector</label>
              <select value={form.industry_sector} onChange={e => set('industry_sector', e.target.value)}>
                <option value="">Select…</option>
                {INDUSTRIES.map(i => <option key={i} value={i}>{i}</option>)}
              </select>
            </div>
            <div>
              <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Company size</label>
              <select value={form.company_size} onChange={e => set('company_size', e.target.value)}>
                <option value="">Select…</option>
                {SIZES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 8 }}>Operating jurisdictions <span style={{ color: 'var(--red)' }}>*</span></label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {ALL_JURS.map(j => (
                <button key={j}
                  className={form.operating_jurisdictions.includes(j) ? 'btn-primary btn-sm' : 'btn-secondary btn-sm'}
                  onClick={() => toggleJur(j)}>{j}</button>
              ))}
            </div>
          </div>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 8 }}>Existing certifications</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {['ISO 42001','ISO 27001','SOC 2','NIST AI RMF','CE Mark','FedRAMP'].map(c => (
                <button key={c}
                  className={form.existing_certifications.includes(c) ? 'btn-primary btn-sm' : 'btn-secondary btn-sm'}
                  onClick={() => toggleCert(c)}>{c}</button>
              ))}
            </div>
          </div>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Primary compliance concerns</label>
            <textarea value={form.primary_concerns} onChange={e => set('primary_concerns', e.target.value)} placeholder="e.g. EU AI Act obligations for our HR screening system; HIPAA + AI Act interaction for clinical AI" style={{ height: 70, resize: 'vertical' }} />
          </div>
          <div>
            <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Recent changes (new systems, markets, acquisitions)</label>
            <textarea value={form.recent_changes} onChange={e => set('recent_changes', e.target.value)} placeholder="e.g. Launched AI-powered loan approval system in Jan 2025; expanding into Germany in Q3" style={{ height: 60, resize: 'vertical' }} />
          </div>
        </div>
      )}

      {/* AI Systems */}
      {section === 'systems' && (
        <div>
          {form.ai_systems.length === 0 ? (
            <div style={{ color: 'var(--text-3)', fontSize: 13, marginBottom: 16, fontStyle: 'italic' }}>
              No AI systems added yet. Add each AI system your company uses or develops.
            </div>
          ) : form.ai_systems.map((sys, i) => (
            <div key={i} className="card" style={{ marginBottom: 12, padding: '14px 16px' }}>
              <div className="flex items-center justify-between" style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--accent)' }}>AI System {i + 1}</div>
                <button className="btn-icon btn-danger" onClick={() => removeSystem(i)}><X size={13} /></button>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <input placeholder="System name (e.g. HR Resume Screener)" value={sys.name} onChange={e => updateSystem(i, 'name', e.target.value)} />
                <input placeholder="Purpose — what decision or task does it support?" value={sys.purpose} onChange={e => updateSystem(i, 'purpose', e.target.value)} />
                <textarea placeholder="Description — how does it work, what model/vendor?" value={sys.description} onChange={e => updateSystem(i, 'description', e.target.value)} style={{ height: 55, resize: 'vertical' }} />
                <input placeholder="Affected population (e.g. job applicants, loan customers, patients)" value={sys.affected_population} onChange={e => updateSystem(i, 'affected_population', e.target.value)} />
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <div>
                    <label style={{ fontSize: 11, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Deployment status</label>
                    <select value={sys.deployment_status} onChange={e => updateSystem(i, 'deployment_status', e.target.value)}>
                      {DEPLOYMENT.map(d => <option key={d} value={d}>{d}</option>)}
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 11, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Autonomy level</label>
                    <select value={sys.autonomy_level} onChange={e => updateSystem(i, 'autonomy_level', e.target.value)}>
                      {AUTONOMY.map(a => <option key={a} value={a}>{a}</option>)}
                    </select>
                  </div>
                </div>
                <div>
                  <label style={{ fontSize: 11, color: 'var(--text-3)', display: 'block', marginBottom: 6 }}>Data processed</label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                    {DATA_TYPES.map(t => (
                      <button key={t}
                        className={sys.data_inputs.includes(t) ? 'btn-primary btn-sm' : 'btn-secondary btn-sm'}
                        style={{ fontSize: 11 }}
                        onClick={() => toggleDataInput(i, t)}>{t}</button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ))}
          <button className="btn-secondary" onClick={addSystem} style={{ width: '100%', justifyContent: 'center' }}>
            <Plus size={13} /> Add AI System
          </button>
        </div>
      )}

      {/* Practices */}
      {section === 'practices' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 6, lineHeight: 1.6 }}>
            Answer honestly. The gap analysis compares these against what each regulation requires.
            Gaps are only identified where the requirement is clearly not met.
          </div>
          {[
            { key: 'has_ai_governance_policy',     label: 'AI governance policy',                       tip: 'A documented policy covering AI use, risk tolerance, and accountability' },
            { key: 'has_risk_assessments',         label: 'AI risk assessments',                        tip: 'Formal risk assessments conducted for AI systems before deployment' },
            { key: 'has_human_oversight',          label: 'Human oversight mechanisms',                 tip: 'Defined processes for human review of AI decisions' },
            { key: 'has_incident_response',        label: 'AI incident response plan',                  tip: 'Process for detecting, reporting, and responding to AI system failures' },
            { key: 'has_documentation',            label: 'AI system documentation',                    tip: 'Technical and operational documentation for each AI system' },
            { key: 'has_bias_testing',             label: 'Bias / fairness testing',                    tip: 'Testing for discriminatory outcomes before and after deployment' },
            { key: 'has_transparency_disclosures', label: 'Transparency disclosures to affected parties', tip: 'Informing customers, employees, or others when AI is used to make decisions about them' },
          ].map(({ key, label, tip }) => (
            <div key={key} style={{ padding: '10px 14px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
              <div className="flex items-center gap-10" style={{ justifyContent: 'space-between' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{label}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{tip}</div>
                </div>
                <div className="flex gap-2">
                  {[true, false, null].map((v, vi) => (
                    <button key={vi}
                      style={{
                        padding: '4px 12px', borderRadius: 4, fontSize: 12, cursor: 'pointer', border: '1px solid',
                        borderColor: form.current_practices[key] === v
                          ? v === true ? 'var(--green)' : v === false ? 'var(--red)' : 'var(--text-3)'
                          : 'var(--border)',
                        background: form.current_practices[key] === v
                          ? v === true ? 'rgba(82,168,120,0.15)' : v === false ? 'rgba(224,82,82,0.12)' : 'var(--bg-3)'
                          : 'transparent',
                        color: form.current_practices[key] === v
                          ? v === true ? 'var(--green)' : v === false ? 'var(--red)' : 'var(--text-3)'
                          : 'var(--text-3)',
                      }}
                      onClick={() => setPractice(key, v)}
                    >
                      {v === true ? 'Yes' : v === false ? 'No' : 'Unsure'}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ))}
          <div style={{ marginTop: 8 }}>
            <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Additional notes on governance practices</label>
            <textarea
              value={form.current_practices.notes || ''}
              onChange={e => setPractice('notes', e.target.value)}
              placeholder="e.g. Risk assessments are done informally, not yet documented. Bias testing is done for the hiring tool but not the loan system."
              style={{ height: 70, resize: 'vertical' }}
            />
          </div>
        </div>
      )}

      {error && <div style={{ marginTop: 14, padding: '8px 12px', background: 'rgba(224,82,82,0.1)', border: '1px solid var(--red)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--red)' }}>{error}</div>}

      <div style={{ marginTop: 24, display: 'flex', gap: 10 }}>
        <button className="btn-primary" onClick={save} disabled={saving} style={{ flex: 1, justifyContent: 'center' }}>
          {saving ? <><Spinner size={13} /> Saving…</> : profile ? 'Save Changes' : 'Create Profile'}
        </button>
        <button className="btn-ghost" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}

// ── Placeholder ───────────────────────────────────────────────────────────────

function GapAnalysisPlaceholder({ onNew, analyses, onOpen }) {
  return (
    <div style={{ padding: '40px 32px', maxWidth: 560 }}>
      <BarChart3 size={32} style={{ color: 'var(--accent)', marginBottom: 16 }} />
      <h2 style={{ fontWeight: 300, fontSize: '1.4rem', marginBottom: 12 }}>Company Compliance Gap Analysis</h2>
      <p style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.7, marginBottom: 28 }}>
        Create a company profile describing your AI systems and current governance practices.
        ARIS will compare them against the regulatory documents in your database and identify
        specific gaps — anchored to real documents, not generic advice.
        Use the domain filter in the sidebar to focus on AI regulation or data privacy obligations.
      </p>
      <button className="btn-primary" onClick={onNew}>
        <Plus size={14} /> Create Company Profile
      </button>
      {analyses.length > 0 && (
        <div style={{ marginTop: 32 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>Recent analyses</div>
          {analyses.slice(0, 5).map(a => (
            <div key={a.id} className="card card-hover" style={{ padding: '10px 14px', marginBottom: 6 }} onClick={() => onOpen(a.id)}>
              <div style={{ fontSize: 13, fontWeight: 500 }}>{a.profile_name}</div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 3 }}>
                {a.gap_count} gaps · score {a.posture_score}/100 · {a.generated_at?.slice(0,10)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function PostureScore({ score }) {
  const color = score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)'
  return (
    <div style={{ position: 'relative', width: 80, height: 80, margin: '0 auto' }}>
      <svg viewBox="0 0 80 80" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx="40" cy="40" r="32" fill="none" stroke="var(--bg-4)" strokeWidth="8" />
        <circle cx="40" cy="40" r="32" fill="none" stroke={color} strokeWidth="8"
          strokeDasharray={`${(score/100)*201} 201`} strokeLinecap="round" />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: '1.3rem', fontWeight: 300, color }}>{score}</span>
      </div>
    </div>
  )
}

function PostureBar({ score, small }) {
  const color = score >= 70 ? 'var(--green)' : score >= 40 ? 'var(--yellow)' : 'var(--red)'
  const h     = small ? 4 : 6
  return (
    <div style={{ flex: 1, height: h, background: 'var(--bg-4)', borderRadius: h/2, overflow: 'hidden' }}>
      <div style={{ height: '100%', width: `${score}%`, background: color, borderRadius: h/2, transition: 'width 0.4s' }} />
    </div>
  )
}

function GapCard({ label, content, accent }) {
  return (
    <div style={{ padding: '10px 12px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', borderLeft: accent ? `3px solid ${accent}` : undefined }}>
      <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 12, color: 'var(--text-2)', lineHeight: 1.55 }}>{content}</div>
    </div>
  )
}
