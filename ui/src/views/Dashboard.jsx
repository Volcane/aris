import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import {
  ArrowRight, Database, Zap, ChevronRight, CalendarDays,
} from 'lucide-react'
import { api } from '../api.js'
import { Badge, UrgencyDot, Spinner } from '../components.jsx'

const URGENCY_COLORS = {
  Critical: 'var(--red)',
  High:     'var(--orange)',
  Medium:   'var(--yellow)',
  Low:      'var(--green)',
}

const fetchBaselines = () =>
  fetch('/api/baselines').then(r => r.json()).catch(() => [])

const fetchBaselineCoverage = () =>
  fetch('/api/baselines/coverage').then(r => r.json()).catch(() => null)

const fetchHorizonStats = () =>
  fetch('/api/horizon/stats').then(r => r.json()).catch(() => null)

const fetchHorizonUpcoming = () =>
  fetch('/api/horizon?days_ahead=90&limit=5').then(r => r.json()).catch(() => [])

export default function Dashboard({ status, domain }) {
  const [docs,         setDocs]         = useState([])
  const [changes,      setChanges]      = useState([])
  const [bases,        setBases]        = useState([])
  const [coverage,     setCoverage]     = useState(null)
  const [horizonStats, setHorizonStats] = useState(null)
  const [horizonItems, setHorizonItems] = useState([])
  const [loading,      setLoading]      = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([
      api.documents({ days: 90, page_size: 8, ...(domain ? { domain } : {}) }).catch(() => ({ items: [] })),
      api.changes({ days: 14, ...(domain ? { domain } : {}) }).catch(() => []),
      fetchBaselines(),
      fetchBaselineCoverage(),
      fetchHorizonStats(),
      fetchHorizonUpcoming(),
    ]).then(([d, c, b, cov, hs, hi]) => {
      setDocs(d.items || [])
      setChanges(Array.isArray(c) ? c.slice(0, 5) : [])
      setBases(Array.isArray(b) ? b : [])
      setCoverage(cov)
      setHorizonStats(hs)
      setHorizonItems(Array.isArray(hi) ? hi : [])
    }).finally(() => setLoading(false))
  }, [domain])

  const stats         = status?.stats || {}
  const hasDocuments  = (stats.total_documents || 0) > 0
  const hasSummaries  = (stats.total_summaries || 0) > 0
  const hasApiKey     = status?.api_key_set
  const setupComplete = hasApiKey && hasSummaries

  if (loading) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
      <Spinner size={24} />
    </div>
  )

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1100 }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontWeight: 300, fontSize: '1.8rem', marginBottom: 4 }}>
          {domain === 'privacy' ? 'Data Privacy Intelligence' : 'AI Regulation Intelligence'}
        </h1>
        <p style={{ color: 'var(--text-3)', fontSize: 13 }}>
          {new Date().toLocaleDateString('en-US', {
            weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
          })}
        </p>
      </div>

      {!setupComplete && (
        <SetupBanner
          hasApiKey={hasApiKey}
          hasDocuments={hasDocuments}
          hasSummaries={hasSummaries}
          navigate={navigate}
        />
      )}

      {bases.length > 0 && (
        <BaselineCoveragePanel
          bases={bases}
          coverage={coverage}
          navigate={navigate}
        />
      )}

      {horizonItems.length > 0 && (
        <HorizonPreviewPanel
          items={horizonItems}
          stats={horizonStats}
          navigate={navigate}
        />
      )}

      {hasSummaries && (
        <LiveDataSection
          docs={docs}
          changes={changes}
          stats={stats}
          navigate={navigate}
        />
      )}

      {hasDocuments && !hasSummaries && (
        <PendingSummariesPanel stats={stats} navigate={navigate} />
      )}
    </div>
  )
}

// ── Setup banner ──────────────────────────────────────────────────────────────

function SetupBanner({ hasApiKey, hasDocuments, hasSummaries, navigate }) {
  const steps = [
    {
      num: 1, label: 'Configure API key',
      detail: 'Add your Anthropic API key in Settings',
      done: hasApiKey, action: () => navigate('/settings'), cta: 'Open Settings',
    },
    {
      num: 2, label: 'Fetch documents',
      detail: 'Pull regulations from government APIs',
      done: hasDocuments, action: () => navigate('/run'), cta: 'Run Agents',
    },
    {
      num: 3, label: 'Summarise with Claude',
      detail: 'Interpret and extract compliance obligations',
      done: hasSummaries, action: () => navigate('/run'), cta: 'Summarise',
    },
  ]
  const nextStep = steps.find(s => !s.done)

  return (
    <div style={{ marginBottom: 28, padding: '20px 24px', background: 'var(--bg-2)', border: '1px solid var(--accent-dim)', borderRadius: 'var(--radius-lg)' }}>
      <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 16, color: 'var(--accent)' }}>
        Getting started
      </div>
      <div style={{ display: 'flex', gap: 0 }}>
        {steps.map((step, i) => (
          <div key={i} style={{ flex: 1, position: 'relative' }}>
            {i < steps.length - 1 && (
              <div style={{ position: 'absolute', top: 13, left: '50%', width: '100%', height: 2, background: step.done ? 'var(--accent)' : 'var(--border)', zIndex: 0 }} />
            )}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, position: 'relative', zIndex: 1 }}>
              <div style={{ width: 26, height: 26, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, background: step.done ? 'var(--accent)' : 'var(--bg-4)', color: step.done ? 'var(--bg)' : 'var(--text-3)', border: `2px solid ${step.done ? 'var(--accent)' : 'var(--border)'}` }}>
                {step.done ? '✓' : step.num}
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 12, fontWeight: step.done ? 400 : 500, color: step.done ? 'var(--text-3)' : 'var(--text)' }}>{step.label}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{step.detail}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
      {nextStep && (
        <div style={{ marginTop: 20, display: 'flex', justifyContent: 'center' }}>
          <button className="btn-primary" onClick={nextStep.action}>
            {nextStep.cta} <ArrowRight size={13} />
          </button>
        </div>
      )}
    </div>
  )
}

// ── Baseline coverage panel ───────────────────────────────────────────────────

function BaselineCoveragePanel({ bases, coverage, navigate }) {
  const priorityOrder = ['EU','Federal','GB','NY','CA_STATE','IL','CO','CA','SG','AU','JP','BR','INTL']
  const critical = bases.filter(b => b.priority === 'critical')
  const high     = bases.filter(b => b.priority === 'high')
  const medium   = bases.filter(b => b.priority === 'medium')

  const byJur = {}
  bases.forEach(b => { byJur[b.jurisdiction] = (byJur[b.jurisdiction] || 0) + 1 })
  const sortedJurs = Object.keys(byJur).sort((a, b) => {
    return (priorityOrder.indexOf(a) === -1 ? 99 : priorityOrder.indexOf(a)) -
           (priorityOrder.indexOf(b) === -1 ? 99 : priorityOrder.indexOf(b))
  })

  return (
    <div style={{ marginBottom: 28 }}>
      <div className="flex items-center justify-between" style={{ marginBottom: 12 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Regulatory Baselines — Available Now
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
            {bases.length} regulations loaded locally · no API required
            {coverage?.last_reviewed && ` · reviewed ${coverage.last_reviewed}`}
          </div>
        </div>
        <button className="btn-ghost btn-sm" onClick={() => navigate('/baselines')}>
          Browse all <ChevronRight size={12} />
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {[
          { label: 'Critical', items: critical, color: 'var(--red)',    border: 'rgba(224,82,82,0.25)',   bg: 'rgba(224,82,82,0.06)'   },
          { label: 'High',     items: high,     color: 'var(--orange)', border: 'rgba(224,131,74,0.25)',  bg: 'rgba(224,131,74,0.06)'  },
          { label: 'Medium',   items: medium,   color: 'var(--text-3)', border: 'var(--border)',          bg: 'var(--bg-2)'             },
        ].filter(g => g.items.length > 0).map(({ label, items, color, border, bg }) => (
          <div key={label} style={{ padding: '10px 14px', background: bg, border: `1px solid ${border}`, borderRadius: 'var(--radius)' }}>
            <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 7 }}>
              {label}
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
              {items.map((b, i) => (
                <button key={i} className="btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={() => navigate('/baselines')}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 9, color, marginRight: 3 }}>{b.jurisdiction}</span>
                  {b.short_name}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="flex gap-3" style={{ marginTop: 8, flexWrap: 'wrap' }}>
        {sortedJurs.map(jur => (
          <span key={jur} style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-3)', cursor: 'pointer' }} onClick={() => navigate('/baselines')}>
            <span style={{ color: 'var(--accent)' }}>{jur}</span> ×{byJur[jur]}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Horizon preview panel ─────────────────────────────────────────────────────

const STAGE_COLOR = {
  'planned':  'var(--text-3)',
  'pre-rule': 'var(--accent)',
  'proposed': 'var(--yellow)',
  'hearing':  'var(--orange)',
  'final':    'var(--red)',
  'enacted':  'var(--green)',
}

function HorizonPreviewPanel({ items, stats, navigate }) {
  return (
    <div style={{ marginBottom: 28 }}>
      <div className="flex items-center justify-between" style={{ marginBottom: 12 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Regulatory Horizon — Coming Up
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
            {stats?.upcoming_90_days > 0
              ? `${stats.upcoming_90_days} items anticipated in the next 90 days`
              : `${stats?.total || items.length} items on the horizon`}
          </div>
        </div>
        <button className="btn-ghost btn-sm" onClick={() => navigate('/horizon')}>
          Full calendar <ChevronRight size={12} />
        </button>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        {items.slice(0, 5).map(item => {
          const color      = STAGE_COLOR[item.stage] || 'var(--text-3)'
          const daysUntil  = item.anticipated_date
            ? Math.round((new Date(item.anticipated_date) - new Date()) / 86400000)
            : null

          return (
            <div key={item.id} className="card card-hover" style={{ padding: '9px 13px', borderLeft: `3px solid ${color}` }}
              onClick={() => navigate('/horizon')}>
              <div className="flex items-center gap-3">
                <span style={{ fontSize: 10, color, fontFamily: 'var(--font-mono)', flexShrink: 0, minWidth: 90 }}>
                  {item.stage?.replace('-', ' ').toUpperCase() || 'PLANNED'}
                </span>
                <span style={{ flex: 1, fontSize: 12 }} className="truncate">{item.title}</span>
                <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-3)', flexShrink: 0 }}>
                  {item.jurisdiction}
                </span>
                {daysUntil !== null && (
                  <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', flexShrink: 0,
                    color: daysUntil < 30 ? 'var(--red)' : daysUntil < 90 ? 'var(--orange)' : 'var(--text-3)' }}>
                    {daysUntil < 0 ? `${Math.abs(daysUntil)}d ago` : `${daysUntil}d`}
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Pending summaries panel ───────────────────────────────────────────────────

function PendingSummariesPanel({ stats, navigate }) {
  return (
    <div style={{ padding: '18px 22px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
        <Database size={17} style={{ color: 'var(--accent)', flexShrink: 0 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 500 }}>{stats.total_documents} documents fetched</div>
          <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 1 }}>
            {stats.pending_summaries || stats.total_documents} pending AI interpretation
          </div>
        </div>
        <button className="btn-primary btn-sm" onClick={() => navigate('/run')}>
          <Zap size={12} /> Summarise now
        </button>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
        Documents are fetched but not yet interpreted. Run the summarise step to
        unlock urgency ratings, plain-English summaries, requirements lists, and
        the full dashboard.
      </div>
    </div>
  )
}

// ── Live data section ─────────────────────────────────────────────────────────

function LiveDataSection({ docs, changes, stats, navigate }) {
  const urgencyCounts = docs.reduce((acc, d) => {
    const u = d.urgency || 'Low'
    acc[u] = (acc[u] || 0) + 1
    return acc
  }, {})
  const chartData = ['Critical','High','Medium','Low'].map(u => ({
    name: u, count: urgencyCounts[u] || 0, fill: URGENCY_COLORS[u],
  }))

  const jurCounts = docs.reduce((acc, d) => {
    acc[d.jurisdiction || 'Unknown'] = (acc[d.jurisdiction || 'Unknown'] || 0) + 1
    return acc
  }, {})

  return (
    <>
      {/* Stats */}
      <div className="flex gap-3" style={{ marginBottom: 22, flexWrap: 'wrap' }}>
        {[
          { label: 'Documents',  value: stats.total_documents,  sub: 'total tracked' },
          { label: 'Summarised', value: stats.total_summaries,  sub: `${stats.pending_summaries||0} pending` },
          { label: 'Changes',    value: stats.total_diffs,      sub: `${stats.unreviewed_diffs||0} unreviewed`, color: 'var(--accent)' },
          { label: 'Critical',   value: stats.critical_diffs,   sub: 'changes', color: 'var(--red)' },
          { label: 'Gap Analyses',value: stats.gap_analyses||0, sub: 'run' },
        ].map(s => (
          <div key={s.label} className="card" style={{ flex: '1 1 130px', padding: '11px 14px' }}>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.5rem', fontWeight: 300, color: s.color || 'var(--text)', marginBottom: 1 }}>
              {s.value ?? 0}
            </div>
            <div style={{ fontSize: 12, fontWeight: 500 }}>{s.label}</div>
            <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 1 }}>{s.sub}</div>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14, marginBottom: 22 }}>
        <div className="card">
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>Urgency distribution</div>
          <ResponsiveContainer width="100%" height={130}>
            <BarChart data={chartData} barSize={26}>
              <XAxis dataKey="name" tick={{ fill: 'var(--text-3)', fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'var(--text-3)', fontSize: 10 }} axisLine={false} tickLine={false} width={18} />
              <Tooltip contentStyle={{ background: 'var(--bg-3)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
              <Bar dataKey="count" radius={[3,3,0,0]}>
                {chartData.map((e, i) => <Cell key={i} fill={e.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="card">
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>By jurisdiction</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {Object.entries(jurCounts).sort((a,b)=>b[1]-a[1]).slice(0,6).map(([jur,count]) => {
              const max = Math.max(...Object.values(jurCounts))
              return (
                <div key={jur} className="flex items-center gap-3">
                  <span style={{ width: 50, fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{jur}</span>
                  <div style={{ flex: 1, height: 5, background: 'var(--bg-4)', borderRadius: 3, overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${Math.round((count/max)*100)}%`, background: 'var(--accent)', borderRadius: 3 }} />
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--text-3)', width: 18, textAlign: 'right' }}>{count}</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Recent changes */}
      {changes.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Recent Changes</div>
            <button className="btn-ghost btn-sm" onClick={() => navigate('/changes')}>View all →</button>
          </div>
          {changes.map(c => (
            <div key={c.id} className="card card-hover" style={{ padding: '9px 13px', marginBottom: 5 }} onClick={() => navigate('/changes')}>
              <div className="flex items-center gap-3">
                <UrgencyDot level={c.severity} />
                <span style={{ flex: 1, fontSize: 12, color: 'var(--text-2)' }} className="truncate">{c.change_summary || 'Change detected'}</span>
                <Badge level={c.severity}>{c.severity}</Badge>
                {!c.reviewed && <span style={{ fontSize: 10, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>NEW</span>}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Recent documents */}
      <div>
        <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Latest Documents</div>
          <button className="btn-ghost btn-sm" onClick={() => navigate('/documents')}>View all →</button>
        </div>
        {docs.slice(0, 6).map(doc => (
          <div key={doc.id} className="card card-hover" style={{ padding: '8px 13px', marginBottom: 4 }} onClick={() => navigate('/documents')}>
            <div className="flex items-center gap-3">
              <UrgencyDot level={doc.urgency} />
              <span style={{ flex: 1, fontSize: 12 }} className="truncate">{doc.title}</span>
              <Badge level={doc.jurisdiction}>{doc.jurisdiction}</Badge>
              {doc.urgency && <Badge level={doc.urgency}>{doc.urgency}</Badge>}
              <span style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>{doc.published_date?.slice(0,10)}</span>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
