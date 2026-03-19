import { useState, useEffect } from 'react'
import { Brain, ThumbsUp, ThumbsDown, Minus, RefreshCw, ToggleLeft, ToggleRight, TrendingUp, TrendingDown, Clock, AlertTriangle } from 'lucide-react'
import { api } from '../api.js'
import { Spinner, EmptyState, SectionHeader, Badge } from '../components.jsx'

// ── API helpers ───────────────────────────────────────────────────────────────

const learnApi = {
  report:         ()        => fetch('/api/learning').then(r => r.json()),
  feedback:       (req)     => fetch('/api/learning/feedback').then(r => r.json()),
  submitFeedback: (payload) => fetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }).then(r => r.json()),
  schedule:       ()        => fetch('/api/learning/schedule').then(r => r.json()),
  toggleAdapt:    (id, on)  => fetch(`/api/learning/adaptation/${id}/toggle?active=${on}`, { method: 'POST' }).then(r => r.json()),
}

const QUALITY_COLOR = (score) => {
  if (score >= 0.75) return 'var(--green)'
  if (score >= 0.5)  return 'var(--yellow)'
  return 'var(--red)'
}

export default function Learning() {
  const [report,   setReport]   = useState(null)
  const [loading,  setLoading]  = useState(true)
  const [tab,      setTab]      = useState('overview')  // overview | sources | keywords | adaptations | schedule | feedback

  const load = async () => {
    setLoading(true)
    try { setReport(await learnApi.report()) }
    catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  if (loading) return <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spinner size={24} /></div>

  if (!report) return (
    <EmptyState icon={Brain} title="Learning system not yet active"
      message="Submit feedback on documents to start training the system." />
  )

  const { summary, source_quality, keyword_learning, prompt_adaptations, schedule_recommendations } = report

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1000 }}>
      <SectionHeader
        title="Learning & Adaptation"
        subtitle="The system learns from your feedback to improve relevance filtering over time"
        action={<button className="btn-secondary btn-sm" onClick={load}><RefreshCw size={13} />Refresh</button>}
      />

      {/* Summary cards */}
      <div className="flex gap-4" style={{ marginBottom: 28, flexWrap: 'wrap' }}>
        {[
          { label: 'Total Feedback',     value: summary.total_feedback,        color: 'var(--text)' },
          { label: 'Confirmed Relevant', value: summary.relevant_confirmed,     color: 'var(--green)' },
          { label: 'False Positives',    value: summary.not_relevant,           color: 'var(--red)' },
          { label: 'Prompt Adaptations', value: summary.prompt_adaptations,     color: 'var(--accent)' },
          { label: 'FP Patterns Blocked',value: summary.false_positive_patterns,color: 'var(--orange)' },
        ].map(c => (
          <div key={c.label} className="card" style={{ flex: 1, minWidth: 120 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>{c.label}</div>
            <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.6rem', fontWeight: 300, color: c.color }}>{c.value ?? 0}</div>
          </div>
        ))}
      </div>

      {/* Tab bar */}
      <div className="flex gap-1" style={{ marginBottom: 20, borderBottom: '1px solid var(--border)', paddingBottom: 0 }}>
        {['overview', 'sources', 'keywords', 'adaptations', 'schedule'].map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              background: 'transparent', border: 'none',
              padding: '8px 16px', cursor: 'pointer',
              fontSize: 13, fontWeight: tab === t ? 500 : 400,
              color: tab === t ? 'var(--text)' : 'var(--text-3)',
              borderBottom: tab === t ? '2px solid var(--accent)' : '2px solid transparent',
              marginBottom: -1,
              transition: 'all 0.15s',
            }}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === 'overview' && <OverviewTab summary={summary} source_quality={source_quality} keyword_learning={keyword_learning} />}
      {tab === 'sources'  && <SourcesTab  source_quality={source_quality} />}
      {tab === 'keywords' && <KeywordsTab keyword_learning={keyword_learning} />}
      {tab === 'adaptations' && <AdaptationsTab adaptations={prompt_adaptations} onToggle={async (id, on) => { await learnApi.toggleAdapt(id, on); load() }} />}
      {tab === 'schedule' && <ScheduleTab schedule={schedule_recommendations} />}
    </div>
  )
}

// ── Overview tab ──────────────────────────────────────────────────────────────

function OverviewTab({ summary, source_quality, keyword_learning }) {
  const top    = source_quality.top_sources?.slice(0,3)    || []
  const bottom = source_quality.bottom_sources?.slice(0,3) || []
  const boosted    = Object.entries(keyword_learning.boosted    || {}).slice(0,6)
  const penalised  = Object.entries(keyword_learning.penalised  || {}).slice(0,6)

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
      {/* Source health */}
      <div className="card">
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>Source Quality Snapshot</div>
        {top.length === 0
          ? <div style={{ color: 'var(--text-3)', fontSize: 13 }}>Provide feedback on documents to build source profiles.</div>
          : <>
              {top.map(([src, score]) => <SourceRow key={src} source={src} score={score} />)}
              {bottom.length > 0 && <div style={{ borderTop: '1px solid var(--border)', marginTop: 8, paddingTop: 8 }}>
                {bottom.map(([src, score]) => <SourceRow key={src} source={src} score={score} />)}
              </div>}
            </>
        }
      </div>

      {/* Keyword drift */}
      <div className="card">
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>Keyword Weight Drift</div>
        {boosted.length === 0 && penalised.length === 0
          ? <div style={{ color: 'var(--text-3)', fontSize: 13 }}>No keyword drift yet — weights start at 1.0 and adjust with feedback.</div>
          : <>
              {boosted.map(([kw, w]) => (
                <div key={kw} className="flex items-center gap-2" style={{ marginBottom: 5 }}>
                  <TrendingUp size={13} style={{ color: 'var(--green)', flexShrink: 0 }} />
                  <span style={{ flex: 1, fontSize: 12, fontFamily: 'var(--font-mono)' }}>{kw}</span>
                  <span style={{ fontSize: 12, color: 'var(--green)' }}>{w.toFixed(2)}×</span>
                </div>
              ))}
              {penalised.map(([kw, w]) => (
                <div key={kw} className="flex items-center gap-2" style={{ marginBottom: 5 }}>
                  <TrendingDown size={13} style={{ color: 'var(--red)', flexShrink: 0 }} />
                  <span style={{ flex: 1, fontSize: 12, fontFamily: 'var(--font-mono)' }}>{kw}</span>
                  <span style={{ fontSize: 12, color: 'var(--red)' }}>{w.toFixed(2)}×</span>
                </div>
              ))}
            </>
        }
      </div>

      {/* How to improve */}
      <div className="card" style={{ gridColumn: '1 / -1' }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14 }}>How the System Learns</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          {[
            { icon: ThumbsDown, color: 'var(--red)', title: 'Mark as Not Relevant', desc: 'When a document is clearly not about AI regulation, mark it. The source and agency scores drop, reducing future noise from the same origin.' },
            { icon: ThumbsUp,   color: 'var(--green)', title: 'Confirm as Relevant', desc: 'Confirming relevant documents reinforces the keywords and source patterns that found it, boosting their weight in future searches.' },
            { icon: Brain,      color: 'var(--accent)', title: 'Automatic Adaptation', desc: 'After 5+ false positives from the same source, Claude automatically generates a targeted prompt note to reduce future errors from that domain.' },
          ].map(({ icon: Icon, color, title, desc }) => (
            <div key={title} style={{ padding: '12px 14px', background: 'var(--bg-3)', borderRadius: 'var(--radius)' }}>
              <div className="flex items-center gap-2" style={{ marginBottom: 8 }}>
                <Icon size={15} style={{ color }} />
                <span style={{ fontSize: 13, fontWeight: 500 }}>{title}</span>
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>{desc}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

// ── Sources tab ───────────────────────────────────────────────────────────────

function SourcesTab({ source_quality }) {
  const profiles = Object.entries(source_quality.all_profiles || {})
    .filter(([k]) => !k.startsWith('agency::'))
    .sort((a, b) => (b[1].quality_score || 0) - (a[1].quality_score || 0))

  if (profiles.length === 0) return (
    <EmptyState icon={Brain} title="No source profiles yet" message="Submit feedback on documents to start building source quality profiles." />
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {profiles.map(([src, prof]) => (
        <div key={src} className="card" style={{ padding: '14px 18px' }}>
          <div className="flex items-center gap-3">
            <div style={{
              width: 40, height: 40, borderRadius: 'var(--radius)',
              background: 'var(--bg-4)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              <span style={{ fontSize: '1.1rem', fontFamily: 'var(--font-display)', color: QUALITY_COLOR(prof.quality_score || 0.7) }}>
                {Math.round((prof.quality_score || 0.7) * 100)}
              </span>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 13, fontWeight: 500 }}>{src}</div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
                {prof.total_count || 0} docs · {prof.positive_count || 0} relevant · {prof.negative_count || 0} rejected
              </div>
            </div>
            <QualityBar score={prof.quality_score || 0.7} />
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Keywords tab ──────────────────────────────────────────────────────────────

function KeywordsTab({ keyword_learning }) {
  const weights = keyword_learning.all_weights || {}
  const entries = Object.entries(weights).sort((a, b) => b[1] - a[1])

  if (entries.length === 0) return (
    <EmptyState icon={Brain} title="No keyword weights yet" message="Keyword weights adjust automatically as you provide feedback." />
  )

  return (
    <div>
      <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 16, lineHeight: 1.6 }}>
        Weights start at 1.0. Values above 1.0 mean the keyword is a strong predictor of relevant documents.
        Values below 1.0 mean it frequently appears in false positives. The system adjusts these automatically.
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
        {entries.map(([kw, w]) => (
          <div key={kw} className="flex items-center gap-3" style={{ padding: '6px 10px', background: 'var(--bg-2)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
            <span style={{ flex: 1, fontSize: 12, fontFamily: 'var(--font-mono)' }}>{kw}</span>
            <div style={{ width: 60, height: 4, background: 'var(--bg-4)', borderRadius: 2, overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                width: `${Math.min((w / 2) * 100, 100)}%`,
                background: w > 1.3 ? 'var(--green)' : w < 0.5 ? 'var(--red)' : 'var(--accent)',
                borderRadius: 2,
              }} />
            </div>
            <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: w > 1.3 ? 'var(--green)' : w < 0.5 ? 'var(--red)' : 'var(--text-2)', width: 36, textAlign: 'right' }}>
              {w.toFixed(2)}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Adaptations tab ───────────────────────────────────────────────────────────

function AdaptationsTab({ adaptations, onToggle }) {
  if (!adaptations?.length) return (
    <EmptyState icon={Brain} title="No prompt adaptations yet"
      message="When 5 or more false positives accumulate from the same source, Claude automatically generates a targeted instruction to reduce future errors. Those instructions appear here." />
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {adaptations.map(adapt => (
        <div key={adapt.id} className="card" style={{ opacity: adapt.active ? 1 : 0.5 }}>
          <div className="flex items-center gap-3" style={{ marginBottom: 10 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
                Source: {adapt.match_keys?.source} · Agency: {adapt.match_keys?.agency || 'any'} · Jurisdiction: {adapt.match_keys?.jurisdiction || 'any'}
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                Based on: {adapt.basis} · Created: {adapt.created_at?.slice(0,10)}
              </div>
            </div>
            <button
              className="btn-secondary btn-sm"
              onClick={() => onToggle(adapt.id, !adapt.active)}
              style={{ flexShrink: 0 }}
            >
              {adapt.active ? <><ToggleRight size={13} style={{ color: 'var(--green)' }} /> Active</> : <><ToggleLeft size={13} /> Disabled</>}
            </button>
          </div>
          <div style={{ padding: '10px 12px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--text-2)', fontStyle: 'italic', lineHeight: 1.6 }}>
            {adapt.instruction}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Schedule tab ──────────────────────────────────────────────────────────────

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function ScheduleTab({ schedule }) {
  const entries = Object.entries(schedule || {})
  if (entries.length === 0) return (
    <EmptyState icon={Clock} title="No schedule data yet"
      message="The system needs at least a few weeks of fetch history to recommend optimal fetch times." />
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 8, lineHeight: 1.6 }}>
        Based on historical fetch data, these are the optimal times to run each source for maximum new-document yield.
        The scheduler will automatically use these intervals in watch mode.
      </div>
      {entries.map(([source, rec]) => (
        <div key={source} className="card" style={{ padding: '14px 18px' }}>
          <div className="flex items-center gap-3" style={{ marginBottom: 10 }}>
            <Clock size={15} style={{ color: 'var(--accent)', flexShrink: 0 }} />
            <span style={{ fontSize: 13, fontWeight: 500, flex: 1 }}>{source}</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-3)', background: 'var(--bg-4)', padding: '3px 8px', borderRadius: 4 }}>
              Every {rec.recommended_interval_hours}h
            </span>
          </div>
          <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
            {DAY_NAMES.map((day, i) => (
              <div key={day} style={{
                padding: '4px 8px', borderRadius: 4, fontSize: 11, fontFamily: 'var(--font-mono)',
                background: rec.best_days_of_week?.includes(i) ? 'var(--accent)' : 'var(--bg-4)',
                color: rec.best_days_of_week?.includes(i) ? '#0d0f0f' : 'var(--text-3)',
              }}>{day}</div>
            ))}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
            Avg {rec.avg_new_per_fetch} new docs/fetch · {rec.note}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function SourceRow({ source, score }) {
  return (
    <div className="flex items-center gap-3" style={{ marginBottom: 8 }}>
      <span style={{ flex: 1, fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }} className="truncate">{source}</span>
      <QualityBar score={score} />
      <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: QUALITY_COLOR(score), width: 36, textAlign: 'right' }}>
        {Math.round(score * 100)}%
      </span>
    </div>
  )
}

function QualityBar({ score }) {
  return (
    <div style={{ width: 80, height: 6, background: 'var(--bg-4)', borderRadius: 3, overflow: 'hidden', flexShrink: 0 }}>
      <div style={{
        height: '100%',
        width: `${score * 100}%`,
        background: QUALITY_COLOR(score),
        borderRadius: 3,
        transition: 'width 0.4s ease',
      }} />
    </div>
  )
}

// ── Inline feedback buttons (used in Documents view) ─────────────────────────

export function FeedbackButtons({ documentId, onFeedback }) {
  const [sent,     setSent]     = useState(null)
  const [loading,  setLoading]  = useState(false)
  const [showReason, setShowReason] = useState(false)
  const [reason,   setReason]   = useState('')

  const submit = async (feedback) => {
    setLoading(true)
    try {
      await learnApi.submitFeedback({ document_id: documentId, feedback, reason: reason || undefined })
      setSent(feedback)
      onFeedback?.(feedback)
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  if (sent) return (
    <div style={{ fontSize: 12, color: 'var(--text-3)', fontStyle: 'italic' }}>
      ✓ Feedback recorded — system will learn from this
    </div>
  )

  return (
    <div>
      <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 8, fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        Is this document relevant to AI regulation?
      </div>
      <div className="flex gap-2 items-center" style={{ flexWrap: 'wrap' }}>
        <button className="btn-secondary btn-sm" disabled={loading} onClick={() => submit('relevant')}>
          <ThumbsUp size={12} style={{ color: 'var(--green)' }} /> Relevant
        </button>
        <button className="btn-secondary btn-sm" disabled={loading} onClick={() => { setShowReason(true) }}>
          <ThumbsDown size={12} style={{ color: 'var(--red)' }} /> Not Relevant
        </button>
        <button className="btn-secondary btn-sm" disabled={loading} onClick={() => submit('partially_relevant')}>
          <Minus size={12} style={{ color: 'var(--yellow)' }} /> Partially
        </button>
      </div>
      {showReason && (
        <div style={{ marginTop: 10 }}>
          <input
            placeholder="Why is this not relevant? (helps the system learn)"
            value={reason}
            onChange={e => setReason(e.target.value)}
            style={{ marginBottom: 8 }}
            onKeyDown={e => e.key === 'Enter' && submit('not_relevant')}
          />
          <div className="flex gap-2">
            <button className="btn-danger btn-sm" onClick={() => submit('not_relevant')} disabled={loading}>
              {loading ? 'Submitting…' : 'Submit Feedback'}
            </button>
            <button className="btn-ghost btn-sm" onClick={() => setShowReason(false)}>Cancel</button>
          </div>
        </div>
      )}
    </div>
  )
}
