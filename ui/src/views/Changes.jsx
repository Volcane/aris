import { useState, useEffect } from 'react'
import { CheckCheck, GitCompare, Filter, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import { api } from '../api.js'
import { Badge, Spinner, EmptyState, SectionHeader, RequirementList } from '../components.jsx'

const SEVERITY_ORDER = { Critical: 0, High: 1, Medium: 2, Low: 3 }

export default function Changes({ domain }) {
  const [changes,    setChanges]    = useState([])
  const [loading,    setLoading]    = useState(true)
  const [expanded,   setExpanded]   = useState({})
  const [severity,   setSeverity]   = useState('')
  const [diffType,   setDiffType]   = useState('')
  const [unreviewed, setUnreviewed] = useState(false)
  const [days,       setDays]       = useState(30)

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.changes({ days, severity, diff_type: diffType, unreviewed, ...(domain ? { domain } : {}) })
      setChanges(data.sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 4) - (SEVERITY_ORDER[b.severity] ?? 4)))
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [days, severity, diffType, unreviewed])

  const review = async (id) => {
    await api.reviewChange(id)
    setChanges(prev => prev.map(c => c.id === id ? { ...c, reviewed: true } : c))
  }

  const toggle = (id) => setExpanded(prev => ({ ...prev, [id]: !prev[id] }))

  const unreviewedCount = changes.filter(c => !c.reviewed).length

  return (
    <div style={{ padding: '28px 32px', maxWidth: 900 }}>
      <SectionHeader
        title="Regulatory Changes"
        subtitle={`${changes.length} changes · ${unreviewedCount} unreviewed`}
        action={
          unreviewedCount > 0 && (
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
              {unreviewedCount} pending review
            </span>
          )
        }
      />

      {/* Filters */}
      <div className="flex gap-3" style={{ marginBottom: 24, flexWrap: 'wrap' }}>
        <select value={days} onChange={e => setDays(Number(e.target.value))} style={{ width: 110 }}>
          <option value={7}>7 days</option>
          <option value={14}>14 days</option>
          <option value={30}>30 days</option>
          <option value={90}>90 days</option>
        </select>
        <select value={severity} onChange={e => setSeverity(e.target.value)} style={{ width: 130 }}>
          <option value="">All Severities</option>
          <option>Critical</option>
          <option>High</option>
          <option>Medium</option>
          <option>Low</option>
        </select>
        <select value={diffType} onChange={e => setDiffType(e.target.value)} style={{ width: 160 }}>
          <option value="">All Change Types</option>
          <option value="version_update">Version Updates</option>
          <option value="addendum">Addenda / Amendments</option>
        </select>
        <label className="flex items-center gap-2" style={{ fontSize: 13, cursor: 'pointer', color: 'var(--text-2)' }}>
          <input
            type="checkbox"
            checked={unreviewed}
            onChange={e => setUnreviewed(e.target.checked)}
            style={{ width: 'auto', accentColor: 'var(--accent)' }}
          />
          Unreviewed only
        </label>
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spinner size={24} /></div>
      ) : changes.length === 0 ? (
        <EmptyState
          icon={GitCompare}
          title="No changes detected"
          message="Changes appear automatically when a regulation is updated or an addendum is linked."
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {changes.map(c => (
            <ChangeCard
              key={c.id}
              change={c}
              expanded={!!expanded[c.id]}
              onToggle={() => toggle(c.id)}
              onReview={() => review(c.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function ChangeCard({ change: c, expanded, onToggle, onReview }) {
  const isVersionUpdate = c.diff_type === 'version_update'
  const borderColor = {
    Critical: 'var(--red)',
    High:     'var(--orange)',
    Medium:   'var(--yellow)',
    Low:      'var(--border)',
  }[c.severity] || 'var(--border)'

  return (
    <div style={{
      background: 'var(--bg-2)',
      border: `1px solid ${borderColor}`,
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden',
      opacity: c.reviewed ? 0.7 : 1,
    }}>
      {/* Header */}
      <div
        style={{ padding: '14px 18px', cursor: 'pointer' }}
        onClick={onToggle}
      >
        <div className="flex items-center gap-3">
          <Badge level={c.severity}>{c.severity}</Badge>
          <span style={{
            fontSize: 11,
            fontFamily: 'var(--font-mono)',
            color: 'var(--text-3)',
            background: 'var(--bg-4)',
            padding: '2px 8px',
            borderRadius: 4,
          }}>
            {isVersionUpdate ? 'VERSION UPDATE' : 'ADDENDUM'}
          </span>
          {!c.reviewed && (
            <span style={{ fontSize: 11, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>● NEW</span>
          )}
          <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
            {c.detected_at?.slice(0, 10)}
          </span>
          {expanded ? <ChevronUp size={14} style={{ color: 'var(--text-3)' }} /> : <ChevronDown size={14} style={{ color: 'var(--text-3)' }} />}
        </div>

        <p style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 8, lineHeight: 1.5 }}>
          {c.change_summary}
        </p>

        {/* Doc references */}
        <div style={{ marginTop: 8, display: 'flex', gap: 12, fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
          <span>BASE: {c.base_document_id?.slice(0, 50)}</span>
          <span>→</span>
          <span>NEW: {c.new_document_id?.slice(0, 50)}</span>
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div style={{ borderTop: '1px solid var(--border)', padding: '16px 18px' }}>
          {/* Side-by-side diff highlights */}
          {(c.added_requirements?.length > 0 || c.removed_requirements?.length > 0 || c.modified_requirements?.length > 0) && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
              <div>
                <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', textTransform: 'uppercase', color: 'var(--red)', marginBottom: 8 }}>
                  ＋ Added / Changed Requirements
                </div>
                {c.added_requirements?.map((r, i) => (
                  <div key={i} className="diff-added" style={{ padding: '6px 10px', borderRadius: 4, marginBottom: 4, fontSize: 12, lineHeight: 1.5 }}>
                    {typeof r === 'string' ? r : r.description}
                    {typeof r === 'object' && r.section && <span style={{ marginLeft: 8, opacity: 0.7 }}>[{r.section}]</span>}
                    {typeof r === 'object' && r.effective_date && <div style={{ fontSize: 11, marginTop: 2, opacity: 0.8 }}>Effective: {r.effective_date}</div>}
                  </div>
                ))}
                {c.modified_requirements?.map((r, i) => (
                  <div key={i} style={{ padding: '6px 10px', borderRadius: 4, marginBottom: 4, fontSize: 12, background: 'rgba(212,168,67,0.10)', color: 'var(--yellow)', lineHeight: 1.5 }}>
                    ~ {typeof r === 'string' ? r : r.description}
                    {typeof r === 'object' && r.direction && <span style={{ marginLeft: 8, opacity: 0.7 }}>[{r.direction}]</span>}
                  </div>
                ))}
              </div>
              <div>
                <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', textTransform: 'uppercase', color: 'var(--green)', marginBottom: 8 }}>
                  − Removed / Relaxed Requirements
                </div>
                {c.removed_requirements?.length > 0 ? c.removed_requirements.map((r, i) => (
                  <div key={i} className="diff-removed" style={{ padding: '6px 10px', borderRadius: 4, marginBottom: 4, fontSize: 12, lineHeight: 1.5 }}>
                    {typeof r === 'string' ? r : r.description}
                  </div>
                )) : (
                  <div style={{ fontSize: 12, color: 'var(--text-3)', fontStyle: 'italic' }}>No requirements removed</div>
                )}
              </div>
            </div>
          )}

          {/* Deadline changes */}
          {c.deadline_changes?.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', textTransform: 'uppercase', color: 'var(--blue)', marginBottom: 8 }}>Deadline Changes</div>
              {c.deadline_changes.map((d, i) => (
                <div key={i} style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 4 }}>
                  {d.description}
                  {d.old_deadline && <span> — <span style={{ color: 'var(--red)' }}>{d.old_deadline}</span> → <span style={{ color: 'var(--green)' }}>{d.new_deadline}</span></span>}
                </div>
              ))}
            </div>
          )}

          {/* Definition changes */}
          {c.definition_changes?.length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: 8 }}>Definition Changes</div>
              {c.definition_changes.map((d, i) => (
                <div key={i} style={{ fontSize: 12, marginBottom: 8, padding: '8px 10px', background: 'var(--bg-3)', borderRadius: 4 }}>
                  <strong style={{ color: 'var(--text)' }}>{d.term}</strong>
                  {d.old_definition && <div style={{ color: 'var(--red)', marginTop: 2 }}>Was: {d.old_definition}</div>}
                  {d.new_definition && <div style={{ color: 'var(--green)', marginTop: 2 }}>Now: {d.new_definition}</div>}
                  {d.impact && <div style={{ color: 'var(--text-3)', marginTop: 2 }}>Impact: {d.impact}</div>}
                  {d.clarification && <div style={{ color: 'var(--text-2)', marginTop: 2 }}>{d.clarification}</div>}
                </div>
              ))}
            </div>
          )}

          {/* New action items */}
          {c.new_action_items?.length > 0 && (
            <RequirementList items={c.new_action_items} label="New Action Items Required" color="var(--accent)" />
          )}

          {/* Obsolete actions */}
          {c.obsolete_action_items?.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: 6 }}>No Longer Required</div>
              {c.obsolete_action_items.map((a, i) => (
                <div key={i} style={{ fontSize: 12, color: 'var(--text-3)', textDecoration: 'line-through', marginBottom: 3 }}>{a}</div>
              ))}
            </div>
          )}

          {/* Assessment */}
          {c.overall_assessment && (
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, marginTop: 12, fontSize: 13, color: 'var(--text-2)', fontStyle: 'italic', lineHeight: 1.65 }}>
              {c.overall_assessment}
            </div>
          )}

          {/* Review button */}
          {!c.reviewed && (
            <div style={{ marginTop: 16 }}>
              <button className="btn-primary btn-sm" onClick={onReview}>
                <CheckCheck size={13} /> Mark as Reviewed
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
