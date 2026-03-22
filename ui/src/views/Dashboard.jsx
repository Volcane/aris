/**
 * ARIS Dashboard — "What needs my attention right now?"
 *
 * Three zones:
 *   1. Alert rail  — actionable items only (critical changes, upcoming deadlines, skipped docs)
 *   2. Insight grid — regulatory pulse (velocity sparklines) + what's active (impact areas, enforcement, horizon)
 *   3. System health — coverage, freshness, API key readiness
 */

import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts'
import {
  AlertTriangle, Clock, ChevronRight, CheckCircle2,
  Bot, Lock, TrendingUp, Shield, CalendarDays,
  Database, Zap, ArrowRight, RefreshCw, BookOpen,
  Activity,
} from 'lucide-react'
import { api } from '../api.js'
import { Badge, Spinner } from '../components.jsx'

const AI_COLOR      = 'var(--accent)'
const PRIVACY_COLOR = '#7c9ef7'

// ── Helpers ───────────────────────────────────────────────────────────────────

function daysUntil(dateStr) {
  if (!dateStr) return null
  return Math.round((new Date(dateStr) - new Date()) / 86400000)
}

function timeAgo(isoStr) {
  if (!isoStr) return 'never'
  const secs = Math.floor((Date.now() - new Date(isoStr)) / 1000)
  if (secs < 60)   return 'just now'
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`
  return `${Math.floor(secs / 86400)}d ago`
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function Dashboard({ status }) {
  const [changes,      setChanges]      = useState([])
  const [horizonItems, setHorizonItems] = useState([])
  const [horizonStats, setHorizonStats] = useState(null)
  const [trends,       setTrends]       = useState(null)
  const [enforcement,  setEnforcement]  = useState([])
  const [criticalDocs, setCriticalDocs] = useState([])
  const [loading,      setLoading]      = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([
      api.changes({ days: 30, severity: 'Critical' }).catch(() => []),
      fetch('/api/horizon?days_ahead=730&limit=30').then(r => r.json()).catch(() => []),
      fetch('/api/horizon/stats').then(r => r.json()).catch(() => null),
      fetch('/api/trends').then(r => r.json()).catch(() => null),
      fetch('/api/enforcement?days=30&limit=4').then(r => r.json()).catch(() => { return { items: [] } }),
      api.documents({ urgency: 'Critical', days: 30, page_size: 5 }).catch(() => ({ items: [] })),
    ]).then(([c, hi, hs, tr, enf, critDocs]) => {
      setChanges(Array.isArray(c) ? c : [])
      setHorizonItems(Array.isArray(hi) ? hi : [])
      setHorizonStats(hs)
      setTrends(tr)
      setEnforcement(enf.items || [])
      setCriticalDocs(critDocs.items || [])
    }).finally(() => setLoading(false))
  }, [])

  const stats        = status?.stats || {}
  const hasDocuments = (stats.total_documents || 0) > 0
  const hasSummaries = (stats.total_summaries || 0) > 0
  const hasApiKey    = status?.api_key_set
  const job          = status?.job || {}
  const apiKeys      = status?.api_keys || {}

  const unreviewedCritical = changes.filter(c => !c.reviewed && c.severity === 'Critical')
  const unreviewedHigh     = changes.filter(c => !c.reviewed && c.severity === 'High')
  const urgentHorizon      = horizonItems.filter(h => {
    const d = daysUntil(h.anticipated_date)
    return d !== null && d >= 0 && d <= 30
  })
  const pendingCount = stats.pending_summaries || 0

  if (loading) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
      <Spinner size={24} />
    </div>
  )

  if (!hasApiKey && !hasDocuments) {
    return <SetupView navigate={navigate} />
  }

  return (
    <div style={{
      padding: '24px 28px',
      maxWidth: 1100,
      width: '100%',
      boxSizing: 'border-box',
      overflowX: 'hidden',
    }}>

      {/* Date + title */}
      <div style={{ marginBottom: 20, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div>
          <h1 style={{ fontWeight: 300, fontSize: '1.5rem', marginBottom: 2 }}>Overview</h1>
          <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
            {new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
          </div>
        </div>
        {/* Freshness badge */}
        <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: job.last_run ? 'var(--green)' : 'var(--text-3)' }} />
          Last run: {timeAgo(job.last_run)}
          {job.running && <><Spinner size={11} /> Running…</>}
        </div>
      </div>

      {/* ── Zone 1: Alert Rail ── */}
      <AlertRail
        unreviewedCritical={unreviewedCritical}
        unreviewedHigh={unreviewedHigh}
        urgentHorizon={urgentHorizon}
        pendingCount={pendingCount}
        criticalDocs={criticalDocs}
        hasSummaries={hasSummaries}
        hasDocuments={hasDocuments}
        navigate={navigate}
      />

      {hasSummaries && (
        <>
          {/* ── Zone 2: Insight grid ── */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)',
            gap: 16,
            marginBottom: 16,
          }}>
            {/* Left: Regulatory pulse */}
            <PulsePanel trends={trends} stats={stats} navigate={navigate} />

            {/* Right: What's active */}
            <ActivePanel
              trends={trends}
              enforcement={enforcement}
              horizonItems={horizonItems}
              horizonStats={horizonStats}
              navigate={navigate}
            />
          </div>

          {/* ── Zone 2c: Horizon widget ── */}
          <HorizonWidget
            items={horizonItems}
            stats={horizonStats}
            navigate={navigate}
          />

          {/* ── Zone 3: System health ── */}
          <SystemHealth stats={stats} apiKeys={apiKeys} status={status} job={job} navigate={navigate} />
        </>
      )}

      {hasDocuments && !hasSummaries && (
        <PendingSummariesPrompt stats={stats} navigate={navigate} />
      )}
    </div>
  )
}

// ── Zone 1: Alert Rail ─────────────────────────────────────────────────────────

function AlertRail({ unreviewedCritical, unreviewedHigh, urgentHorizon, pendingCount, criticalDocs, hasSummaries, hasDocuments, navigate }) {
  const alerts = []

  if (unreviewedCritical.length > 0) {
    alerts.push({
      key: 'critical-changes',
      icon: AlertTriangle,
      color: 'var(--red)',
      bg: 'rgba(224,82,82,0.10)',
      border: 'rgba(224,82,82,0.35)',
      label: `${unreviewedCritical.length} critical change${unreviewedCritical.length > 1 ? 's' : ''} unreviewed`,
      sub: unreviewedCritical[0]?.change_summary?.slice(0, 70) || 'Requires immediate review',
      action: () => navigate('/changes'),
      cta: 'Review →',
    })
  }

  if (unreviewedHigh.length > 0) {
    alerts.push({
      key: 'high-changes',
      icon: AlertTriangle,
      color: 'var(--orange)',
      bg: 'rgba(224,131,74,0.10)',
      border: 'rgba(224,131,74,0.35)',
      label: `${unreviewedHigh.length} high-severity change${unreviewedHigh.length > 1 ? 's' : ''}`,
      sub: `${unreviewedHigh.filter(c => !c.reviewed).length} pending review`,
      action: () => navigate('/changes'),
      cta: 'Review →',
    })
  }

  if (urgentHorizon.length > 0) {
    const next = urgentHorizon[0]
    const d = daysUntil(next.anticipated_date)
    alerts.push({
      key: 'horizon-urgent',
      icon: Clock,
      color: d < 14 ? 'var(--red)' : 'var(--orange)',
      bg: d < 14 ? 'rgba(224,82,82,0.08)' : 'rgba(224,131,74,0.08)',
      border: d < 14 ? 'rgba(224,82,82,0.3)' : 'rgba(224,131,74,0.3)',
      label: `${urgentHorizon.length} deadline${urgentHorizon.length > 1 ? 's' : ''} within 30 days`,
      sub: `${next.title?.slice(0, 65)} — ${d}d`,
      action: () => navigate('/horizon'),
      cta: 'View →',
    })
  }

  if (criticalDocs.length > 0) {
    alerts.push({
      key: 'critical-docs',
      icon: AlertTriangle,
      color: 'var(--red)',
      bg: 'rgba(224,82,82,0.07)',
      border: 'rgba(224,82,82,0.2)',
      label: `${criticalDocs.length} critical-urgency document${criticalDocs.length > 1 ? 's' : ''}`,
      sub: criticalDocs[0]?.title?.slice(0, 70) || '',
      action: () => navigate('/documents'),
      cta: 'Open →',
    })
  }

  if (pendingCount > 10 && hasSummaries) {
    alerts.push({
      key: 'pending',
      icon: Database,
      color: 'var(--yellow)',
      bg: 'rgba(212,168,67,0.08)',
      border: 'rgba(212,168,67,0.25)',
      label: `${pendingCount} document${pendingCount > 1 ? 's' : ''} pending summarization`,
      sub: 'Run agents to process and unlock full analysis',
      action: () => navigate('/run'),
      cta: 'Run →',
    })
  }

  if (alerts.length === 0) {
    if (!hasSummaries) return null
    return (
      <div style={{
        marginBottom: 16, padding: '10px 16px',
        background: 'rgba(82,168,120,0.08)', border: '1px solid rgba(82,168,120,0.25)',
        borderRadius: 'var(--radius)', display: 'flex', alignItems: 'center', gap: 10,
      }}>
        <CheckCircle2 size={14} style={{ color: 'var(--green)', flexShrink: 0 }} />
        <span style={{ fontSize: 13, color: 'var(--text-2)' }}>
          No critical items — system is up to date
        </span>
        <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
          {(stats?.total_documents || 0)} docs · {(stats?.total_summaries || 0)} summarised
        </span>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
      {alerts.map(a => (
        <AlertCard key={a.key} alert={a} />
      ))}
    </div>
  )
}

function AlertCard({ alert: a }) {
  const Icon = a.icon
  return (
    <div
      onClick={a.action}
      style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '10px 14px',
        background: a.bg, border: `1px solid ${a.border}`,
        borderRadius: 'var(--radius)', cursor: 'pointer',
        transition: 'opacity 0.1s',
      }}
      onMouseEnter={e => e.currentTarget.style.opacity = '0.85'}
      onMouseLeave={e => e.currentTarget.style.opacity = '1'}
    >
      <Icon size={14} style={{ color: a.color, flexShrink: 0 }} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <span style={{ fontSize: 13, fontWeight: 500, color: a.color, marginRight: 8 }}>
          {a.label}
        </span>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }} className="truncate">
          {a.sub}
        </span>
      </div>
      <span style={{ fontSize: 12, color: a.color, fontFamily: 'var(--font-mono)', flexShrink: 0, fontWeight: 500 }}>
        {a.cta}
      </span>
    </div>
  )
}

// ── Zone 2a: Regulatory Pulse ─────────────────────────────────────────────────

const STAGE_COLORS = {
  final: 'var(--red)', hearing: 'var(--orange)',
  proposed: 'var(--yellow)', enacted: 'var(--green)',
  'pre-rule': 'var(--accent)', planned: 'var(--text-3)',
}

const JUR_COLORS = ['#1A5EAB', '#e05252', '#52a878', '#d4a843', '#e0834a', '#7b52ab']

function PulsePanel({ trends, stats, navigate }) {
  const velocity = trends?.velocity || []
  const alerts   = trends?.alerts   || []
  const heatmap  = trends?.heatmap  || []

  // Build sparkline data per jurisdiction (last 6 windows)
  const topJurs = velocity.slice(0, 5)

  const noData = !trends || velocity.length === 0

  return (
    <div className="card" style={{ padding: '16px 18px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Activity size={14} style={{ color: 'var(--accent)' }} />
          <span style={{ fontSize: 13, fontWeight: 500 }}>Regulatory Pulse</span>
        </div>
        <button className="btn-ghost btn-sm" style={{ fontSize: 11 }} onClick={() => navigate('/trends')}>
          Full trends <ChevronRight size={11} />
        </button>
      </div>

      {noData ? (
        <div style={{ color: 'var(--text-3)', fontSize: 13, padding: '12px 0', fontStyle: 'italic' }}>
          Run agents to generate trend data
        </div>
      ) : (
        <>
          {/* Velocity sparklines */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
            {topJurs.map((v, i) => {
              const sparkData = (v.windows || []).slice(-8).map((w, wi) => ({ wi, count: w.count }))
              const maxCount = Math.max(...sparkData.map(d => d.count), 1)
              const trend    = v.trend
              const trendColor = trend === 'accelerating' ? 'var(--red)' : trend === 'stable' ? 'var(--text-3)' : 'var(--text-3)'
              const lineColor  = JUR_COLORS[i % JUR_COLORS.length]

              return (
                <div key={v.jurisdiction} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 11,
                    color: 'var(--text-2)', width: 50, flexShrink: 0,
                  }}>{v.jurisdiction}</span>

                  <div style={{ flex: 1, height: 28 }}>
                    <ResponsiveContainer width="100%" height={28}>
                      <LineChart data={sparkData}>
                        <Line type="monotone" dataKey="count" stroke={lineColor}
                          strokeWidth={1.5} dot={false} />
                        <Tooltip
                          contentStyle={{ background: 'var(--bg-3)', border: '1px solid var(--border)', borderRadius: 4, fontSize: 10, padding: '2px 6px' }}
                          formatter={(v) => [v, 'docs']}
                          labelFormatter={() => ''}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, width: 80, flexShrink: 0, justifyContent: 'flex-end' }}>
                    <span style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
                      {v.total_documents}
                    </span>
                    <span style={{
                      fontSize: 9, fontFamily: 'var(--font-mono)', padding: '1px 5px',
                      borderRadius: 3, background: trendColor + '18', color: trendColor,
                    }}>
                      {trend === 'accelerating' ? '↑' : trend === 'decelerating' ? '↓' : '—'}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Alert badges */}
          {alerts.length > 0 && (
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 10 }}>
              <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
                Acceleration Alerts
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {alerts.slice(0, 4).map((a, i) => (
                  <span key={i} style={{
                    fontSize: 11, padding: '2px 8px', borderRadius: 4,
                    background: a.severity === 'Critical' ? 'rgba(224,82,82,0.12)' : 'rgba(224,131,74,0.10)',
                    color: a.severity === 'Critical' ? 'var(--red)' : 'var(--orange)',
                    fontFamily: 'var(--font-mono)',
                  }}>
                    {a.label} {a.severity === 'Critical' ? '⚠' : '↑'}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Top impact areas */}
          {heatmap.length > 0 && (
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 10, marginTop: 10 }}>
              <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 }}>
                Top Impact Areas
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                {heatmap.slice(0, 5).map((h, i) => {
                  const max = heatmap[0]?.activity_score || 1
                  const intensity = Math.round((h.activity_score / max) * 100)
                  return (
                    <span key={i} style={{
                      fontSize: 11, padding: '2px 8px', borderRadius: 4,
                      background: `rgba(26,94,171,${0.08 + (intensity / 100) * 0.18})`,
                      color: 'var(--text-2)',
                    }}>
                      {h.area}
                      <span style={{ marginLeft: 5, fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
                        {h.total}
                      </span>
                    </span>
                  )
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ── Zone 2b: What's Active ────────────────────────────────────────────────────

function ActivePanel({ trends, enforcement, horizonItems, horizonStats, navigate }) {
  const nextDeadlines = horizonItems
    .filter(h => h.anticipated_date && daysUntil(h.anticipated_date) >= 0)
    .sort((a, b) => new Date(a.anticipated_date) - new Date(b.anticipated_date))
    .slice(0, 3)

  const latestEnforcement = enforcement.slice(0, 3)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* Domain coverage pills */}
      <div className="card" style={{ padding: '12px 14px' }}>
        <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
          Coverage
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          {[
            { icon: Bot,  label: 'AI Reg',  value: trends?.jurisdictions || 0, color: AI_COLOR,      sub: 'jurisdictions' },
            { icon: Lock, label: 'Privacy', value: horizonStats?.total || 0,    color: PRIVACY_COLOR, sub: 'horizon items' },
          ].map(s => (
            <div key={s.label} style={{ flex: 1, padding: '8px 10px', background: 'var(--bg-3)', borderRadius: 'var(--radius)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 3 }}>
                <s.icon size={11} style={{ color: s.color }} />
                <span style={{ fontSize: 11, color: 'var(--text-3)' }}>{s.label}</span>
              </div>
              <div style={{ fontSize: '1.3rem', fontFamily: 'var(--font-display)', fontWeight: 300, color: s.color, lineHeight: 1 }}>
                {s.value}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2 }}>{s.sub}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Upcoming deadlines */}
      {nextDeadlines.length > 0 && (
        <div className="card" style={{ padding: '12px 14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Next Deadlines
            </div>
            <button className="btn-ghost btn-sm" style={{ fontSize: 10 }} onClick={() => navigate('/horizon')}>
              All <ChevronRight size={10} />
            </button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {nextDeadlines.map(h => {
              const d     = daysUntil(h.anticipated_date)
              const color = d < 14 ? 'var(--red)' : d < 30 ? 'var(--orange)' : 'var(--yellow)'
              return (
                <div key={h.id} style={{ display: 'flex', alignItems: 'center', gap: 8 }} onClick={() => navigate('/horizon')} className="cursor-pointer">
                  <CalendarDays size={11} style={{ color, flexShrink: 0 }} />
                  <span style={{ flex: 1, fontSize: 11, color: 'var(--text-2)', minWidth: 0 }} className="truncate">{h.title}</span>
                  <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color, flexShrink: 0 }}>{d}d</span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Latest enforcement */}
      {latestEnforcement.length > 0 && (
        <div className="card" style={{ padding: '12px 14px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Recent Enforcement
            </div>
            <button className="btn-ghost btn-sm" style={{ fontSize: 10 }} onClick={() => navigate('/enforcement')}>
              All <ChevronRight size={10} />
            </button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {latestEnforcement.map(e => (
              <div key={e.id} style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                <Shield size={10} style={{ color: 'var(--orange)', flexShrink: 0 }} />
                <span style={{ flex: 1, fontSize: 11, color: 'var(--text-2)', minWidth: 0 }} className="truncate">{e.title}</span>
                <span style={{ fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--text-3)', flexShrink: 0 }}>
                  {e.source?.toUpperCase()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}


// ── Horizon Widget ─────────────────────────────────────────────────────────────

const STAGE_COLORS = {
  'enacted':    { bg: 'rgba(224,82,82,0.10)',  border: 'rgba(224,82,82,0.3)',  text: 'var(--red)',    label: 'Deadline' },
  'final':      { bg: 'rgba(224,82,82,0.08)',  border: 'rgba(224,82,82,0.25)', text: 'var(--red)',    label: 'Final Rule' },
  'hearing':    { bg: 'rgba(212,168,67,0.10)', border: 'rgba(212,168,67,0.3)', text: 'var(--yellow)', label: 'Hearing' },
  'proposed':   { bg: 'rgba(93,158,234,0.10)', border: 'rgba(93,158,234,0.3)', text: 'var(--accent)', label: 'Proposed' },
  'pre-rule':   { bg: 'rgba(93,158,234,0.08)', border: 'rgba(93,158,234,0.2)', text: 'var(--accent)', label: 'Pre-Rule' },
  'planned':    { bg: 'var(--bg-3)',            border: 'var(--border)',        text: 'var(--text-3)', label: 'Planned' },
}

const JUR_COLORS = {
  EU: '#3B82F6', GB: '#8B5CF6', Federal: '#22C55E',
  CA: '#F59E0B', CO: '#F97316', IL: '#EC4899',
  TX: '#EF4444', WA: '#06B6D4', NY: '#A78BFA',
  BR: '#10B981', IN: '#F59E0B', SG: '#14B8A6',
  KR: '#6366F1', JP: '#F97316', AU: '#84CC16',
}

function HorizonWidget({ items, stats, navigate }) {
  const [filter, setFilter] = useState('upcoming')   // upcoming | all | by_jurisdiction

  if (!items || items.length === 0) {
    return (
      <div className="card" style={{ padding: '16px 18px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <CalendarDays size={14} style={{ color: 'var(--accent)' }} />
            <span style={{ fontSize: 13, fontWeight: 500 }}>Regulatory Horizon</span>
          </div>
          <button className="btn-ghost btn-sm" style={{ fontSize: 10 }} onClick={() => navigate('/horizon')}>
            Open full view <ChevronRight size={10} />
          </button>
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-3)', fontStyle: 'italic', paddingTop: 8 }}>
          No horizon items yet. Run agents to fetch upcoming regulatory events.
        </div>
      </div>
    )
  }

  // Group by urgency
  const now = new Date()
  const urgent  = items.filter(h => { const d = daysUntil(h.anticipated_date); return d !== null && d >= 0 && d <= 30 })
  const near    = items.filter(h => { const d = daysUntil(h.anticipated_date); return d !== null && d > 30 && d <= 180 })
  const distant = items.filter(h => { const d = daysUntil(h.anticipated_date); return d !== null && d > 180 })
  const undated = items.filter(h => !h.anticipated_date || daysUntil(h.anticipated_date) === null)

  const displayed = filter === 'upcoming'
    ? [...urgent, ...near, ...distant].slice(0, 12)
    : items.slice(0, 20)

  return (
    <div className="card" style={{ padding: '16px 18px', marginBottom: 0 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <CalendarDays size={14} style={{ color: 'var(--accent)' }} />
          <span style={{ fontSize: 13, fontWeight: 500 }}>Regulatory Horizon</span>
          <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-3)',
            background: 'var(--bg-4)', padding: '1px 6px', borderRadius: 3 }}>
            {items.length}
          </span>
          {urgent.length > 0 && (
            <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--red)',
              background: 'rgba(224,82,82,0.10)', padding: '1px 6px', borderRadius: 3,
              border: '1px solid rgba(224,82,82,0.25)' }}>
              {urgent.length} within 30d
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 6 }}>
          {['upcoming', 'all'].map(f => (
            <button key={f} onClick={() => setFilter(f)}
              style={{ fontSize: 10, padding: '2px 7px', borderRadius: 3, cursor: 'pointer',
                background: filter === f ? 'var(--accent-dim)' : 'var(--bg-4)',
                border: `1px solid ${filter === f ? 'var(--accent)' : 'var(--border)'}`,
                color: filter === f ? 'var(--accent)' : 'var(--text-3)' }}>
              {f}
            </button>
          ))}
          <button className="btn-ghost btn-sm" style={{ fontSize: 10 }} onClick={() => navigate('/horizon')}>
            Full view <ChevronRight size={10} />
          </button>
        </div>
      </div>

      {/* Urgency summary bar */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 14 }}>
        {[
          { label: 'Within 30d',  count: urgent.length,  color: 'var(--red)',    bg: 'rgba(224,82,82,0.08)',  border: 'rgba(224,82,82,0.2)'  },
          { label: '30–180d',     count: near.length,    color: 'var(--yellow)', bg: 'rgba(212,168,67,0.08)', border: 'rgba(212,168,67,0.2)' },
          { label: '180d+',       count: distant.length, color: 'var(--accent)', bg: 'var(--accent-glow)',    border: 'var(--accent-dim)'    },
          { label: 'TBD',         count: undated.length, color: 'var(--text-3)', bg: 'var(--bg-3)',           border: 'var(--border)'        },
        ].map(s => (
          <div key={s.label} style={{ padding: '8px 10px', background: s.bg,
            border: `1px solid ${s.border}`, borderRadius: 'var(--radius)', textAlign: 'center' }}>
            <div style={{ fontSize: '1.3rem', fontFamily: 'var(--font-display)', fontWeight: 300,
              color: s.color, lineHeight: 1 }}>{s.count}</div>
            <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2 }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Item list */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {displayed.map((h, i) => {
          const d     = daysUntil(h.anticipated_date)
          const stage = (h.stage || 'planned').toLowerCase()
          const sc    = STAGE_COLORS[stage] || STAGE_COLORS.planned
          const jurColor = JUR_COLORS[h.jurisdiction] || 'var(--text-3)'

          const urgencyColor = d === null ? 'var(--text-3)'
            : d < 0   ? 'var(--text-3)'
            : d <= 14 ? 'var(--red)'
            : d <= 30 ? 'var(--orange)'
            : d <= 90 ? 'var(--yellow)'
            : 'var(--text-3)'

          const dateLabel = d === null ? 'TBD'
            : d < 0   ? `${Math.abs(d)}d ago`
            : d === 0 ? 'Today'
            : d <= 365 ? `${d}d`
            : h.anticipated_date ? new Date(h.anticipated_date).getFullYear().toString() : 'TBD'

          return (
            <div key={h.id || i}
              onClick={() => navigate('/horizon')}
              style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px',
                background: 'var(--bg-2)', border: '1px solid var(--border)',
                borderRadius: 'var(--radius)', cursor: 'pointer', transition: 'border-color 0.1s' }}
              onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--border-hi)'}
              onMouseLeave={e => e.currentTarget.style.borderColor = 'var(--border)'}
            >
              {/* Date countdown */}
              <div style={{ width: 36, flexShrink: 0, textAlign: 'right' }}>
                <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: urgencyColor, fontWeight: d !== null && d <= 30 ? 600 : 400 }}>
                  {dateLabel}
                </span>
              </div>

              {/* Stage badge */}
              <span style={{ fontSize: 9, padding: '1px 5px', borderRadius: 3, flexShrink: 0,
                background: sc.bg, border: `1px solid ${sc.border}`, color: sc.text,
                fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                {sc.label}
              </span>

              {/* Jurisdiction */}
              <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: jurColor,
                background: jurColor + '18', padding: '1px 5px', borderRadius: 3, flexShrink: 0,
                border: `1px solid ${jurColor}30` }}>
                {h.jurisdiction}
              </span>

              {/* Title */}
              <span style={{ flex: 1, fontSize: 12, color: 'var(--text-2)', minWidth: 0 }} className="truncate">
                {h.title}
              </span>

              {/* Agency (optional, show if space) */}
              {h.agency && (
                <span style={{ fontSize: 10, color: 'var(--text-3)', flexShrink: 0, maxWidth: 120,
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {h.agency}
                </span>
              )}
            </div>
          )
        })}
        {displayed.length < items.length && (
          <button
            className="btn-ghost btn-sm"
            style={{ width: '100%', justifyContent: 'center', fontSize: 11 }}
            onClick={() => navigate('/horizon')}
          >
            +{items.length - displayed.length} more in full Horizon view
          </button>
        )}
      </div>
    </div>
  )
}

// ── Zone 3: System Health ─────────────────────────────────────────────────────

function SystemHealth({ stats, apiKeys, status, job, navigate }) {
  const coverage = Math.round(((stats.total_summaries || 0) / Math.max(stats.total_documents || 1, 1)) * 100)
  const baselines = 31 // known constant

  const keyItems = [
    { key: 'anthropic',       label: 'Claude AI',     critical: true  },
    { key: 'legiscan',        label: 'LegiScan',      critical: false },
    { key: 'regulations_gov', label: 'Regs.gov',      critical: false },
    { key: 'congress_gov',    label: 'Congress.gov',  critical: false },
  ]
  const missingKeys = keyItems.filter(k => !apiKeys[k.key])

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
      gap: 10,
    }}>
      {/* Data coverage */}
      <HealthTile
        label="Data Coverage"
        onClick={() => navigate('/documents')}
      >
        <div style={{ fontSize: '1.6rem', fontFamily: 'var(--font-display)', fontWeight: 300, color: coverage > 80 ? 'var(--green)' : coverage > 50 ? 'var(--yellow)' : 'var(--orange)', lineHeight: 1, marginBottom: 4 }}>
          {coverage}%
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
          {stats.total_summaries ?? 0} / {stats.total_documents ?? 0} summarised
        </div>
        <div style={{ marginTop: 6, height: 3, background: 'var(--bg-4)', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${coverage}%`, background: coverage > 80 ? 'var(--green)' : coverage > 50 ? 'var(--yellow)' : 'var(--orange)', borderRadius: 2 }} />
        </div>
      </HealthTile>

      {/* Domain split */}
      <HealthTile label="Domains" onClick={() => navigate('/documents')}>
        <div style={{ display: 'flex', gap: 10, marginTop: 2 }}>
          {[
            { label: 'AI Reg',  value: stats.ai_documents || 0,      color: AI_COLOR      },
            { label: 'Privacy', value: stats.privacy_documents || 0, color: PRIVACY_COLOR },
          ].map(d => (
            <div key={d.label} style={{ flex: 1 }}>
              <div style={{ fontSize: '1.3rem', fontFamily: 'var(--font-display)', fontWeight: 300, color: d.color, lineHeight: 1, marginBottom: 2 }}>
                {d.value}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-3)' }}>{d.label}</div>
            </div>
          ))}
        </div>
      </HealthTile>

      {/* Baselines */}
      <HealthTile label="Baselines" onClick={() => navigate('/baselines')}>
        <div style={{ fontSize: '1.6rem', fontFamily: 'var(--font-display)', fontWeight: 300, color: 'var(--accent)', lineHeight: 1, marginBottom: 4 }}>
          {baselines}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-3)' }}>regulations loaded · no API</div>
        <div style={{ fontSize: 10, color: 'var(--text-3)', marginTop: 2 }}>
          {stats.horizon_items || 0} horizon items tracked
        </div>
      </HealthTile>

      {/* API keys */}
      <HealthTile
        label="API Keys"
        onClick={() => navigate('/settings')}
        alert={missingKeys.some(k => k.critical)}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 2 }}>
          {keyItems.map(k => (
            <div key={k.key} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
              <div style={{
                width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
                background: apiKeys[k.key] ? 'var(--green)' : k.critical ? 'var(--red)' : 'var(--text-3)',
              }} />
              <span style={{ color: apiKeys[k.key] ? 'var(--text-2)' : k.critical ? 'var(--red)' : 'var(--text-3)' }}>
                {k.label}
              </span>
              {!apiKeys[k.key] && !k.critical && (
                <span style={{ fontSize: 9, color: 'var(--text-3)', marginLeft: 'auto' }}>optional</span>
              )}
            </div>
          ))}
        </div>
      </HealthTile>
    </div>
  )
}

function HealthTile({ label, children, onClick, alert }) {
  return (
    <div
      className="card"
      onClick={onClick}
      style={{
        padding: '12px 14px', cursor: 'pointer',
        borderColor: alert ? 'rgba(224,82,82,0.35)' : 'var(--border)',
        transition: 'border-color 0.15s',
      }}
      onMouseEnter={e => e.currentTarget.style.borderColor = alert ? 'rgba(224,82,82,0.6)' : 'var(--border-hi)'}
      onMouseLeave={e => e.currentTarget.style.borderColor = alert ? 'rgba(224,82,82,0.35)' : 'var(--border)'}
    >
      <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>
        {label}
      </div>
      {children}
    </div>
  )
}

// ── Setup view ────────────────────────────────────────────────────────────────

function SetupView({ navigate }) {
  const steps = [
    { num: 1, label: 'Configure API key',     detail: 'Add Anthropic key in Settings', action: () => navigate('/settings'), cta: 'Open Settings' },
    { num: 2, label: 'Fetch documents',       detail: 'Pull from government sources',  action: () => navigate('/run'),      cta: 'Run Agents'   },
    { num: 3, label: 'Summarise with Claude', detail: 'Interpret compliance obligations', action: () => navigate('/run'),   cta: 'Summarise'    },
  ]
  return (
    <div style={{ padding: '48px 40px', maxWidth: 560 }}>
      <h2 style={{ fontWeight: 300, fontSize: '1.4rem', marginBottom: 8 }}>Welcome to ARIS</h2>
      <p style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 28 }}>Complete setup to start monitoring regulations.</p>
      <div style={{ display: 'flex', gap: 0 }}>
        {steps.map((step, i) => (
          <div key={i} style={{ flex: 1, position: 'relative' }}>
            {i < steps.length - 1 && <div style={{ position: 'absolute', top: 13, left: '50%', width: '100%', height: 2, background: 'var(--border)', zIndex: 0 }} />}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, position: 'relative', zIndex: 1 }}>
              <div style={{ width: 26, height: 26, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, background: 'var(--bg-4)', color: 'var(--text-3)', border: '2px solid var(--border)' }}>
                {step.num}
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 12, fontWeight: 500 }}>{step.label}</div>
                <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{step.detail}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
      <div style={{ marginTop: 24, display: 'flex', justifyContent: 'center' }}>
        <button className="btn-primary" onClick={steps[0].action}>
          Get started <ArrowRight size={13} />
        </button>
      </div>
    </div>
  )
}

// ── Pending summaries prompt ───────────────────────────────────────────────────

function PendingSummariesPrompt({ stats, navigate }) {
  return (
    <div style={{ padding: '18px 22px', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
        <Database size={17} style={{ color: 'var(--accent)', flexShrink: 0 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 500 }}>{stats.total_documents} documents fetched</div>
          <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 1 }}>{stats.pending_summaries || stats.total_documents} pending AI interpretation</div>
        </div>
        <button className="btn-primary btn-sm" onClick={() => navigate('/run')}><Zap size={12} /> Summarise now</button>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
        Documents are fetched but not yet interpreted. Run the summarise step to unlock urgency ratings, insights, and the full dashboard.
      </div>
    </div>
  )
}
