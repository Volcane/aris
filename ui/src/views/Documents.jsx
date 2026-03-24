import { useState, useEffect, useCallback } from 'react'
import { Search, ExternalLink, FileText, ListChecks, GitCompare, X, ChevronRight, Download, CheckCircle2, MinusCircle, Archive } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api.js'
import { Badge, UrgencyDot, Spinner, EmptyState, Modal, Pagination, RequirementList, KeyValue, SectionHeader, DomainFilter, ViewHeader } from '../components.jsx'
import { FeedbackButtons } from './Learning.jsx'

const URGENCIES    = ['', 'Critical', 'High', 'Medium', 'Low']
const JURISDICTIONS = ['', 'Federal', 'PA', 'EU', 'GB', 'CA', 'JP', 'CN', 'AU']

// ── Review badge shown on list rows ──────────────────────────────────────────

const REVIEW_BADGE = {
  relevant: {
    icon:  CheckCircle2,
    color: 'var(--green)',
    label: 'Reviewed - Relevant',
  },
  partially_relevant: {
    icon:  MinusCircle,
    color: 'var(--yellow)',
    label: 'Reviewed - Partially Relevant',
  },
}

function ReviewBadge({ status }) {
  const cfg = REVIEW_BADGE[status]
  if (!cfg) return null
  const Icon = cfg.icon
  return (
    <Icon
      size={13}
      style={{ color: cfg.color, flexShrink: 0 }}
      title={cfg.label}
    />
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Documents() {
  // Domain filter - local, persisted per view
  const [domain, setDomain] = useState(() => {
    try { return localStorage.getItem('aris_domain_documents') ?? null } catch { return null }
  })
  const handleDomainChange = (d) => {
    setDomain(d)
    try { localStorage.setItem('aris_domain_documents', d ?? '') } catch {}
  }
  const [tab,      setTab]      = useState('active')   // 'active' | 'archived'

  // Active tab state
  const [docs,     setDocs]     = useState([])
  const [total,    setTotal]    = useState(0)
  const [pages,    setPages]    = useState(1)
  const [page,     setPage]     = useState(1)
  const [loading,  setLoading]  = useState(true)

  // Archive tab state
  const [archived,       setArchived]       = useState([])
  const [archivedTotal,  setArchivedTotal]  = useState(0)
  const [archivedPages,  setArchivedPages]  = useState(1)
  const [archivedPage,   setArchivedPage]   = useState(1)
  const [archivedLoading,setArchivedLoading]= useState(false)

  // Detail panel
  const [selected,      setSelected]      = useState(null)
  const [detail,        setDetail]        = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  // Checklist / diff
  const [checklist,        setChecklist]        = useState(null)
  const [checklistLoading, setChecklistLoading] = useState(false)
  const [companyCtx,       setCompanyCtx]       = useState('')
  const [showChecklist,    setShowChecklist]    = useState(false)
  const [showDiff,         setShowDiff]         = useState(false)
  const [diffTarget,       setDiffTarget]       = useState('')
  const [diffResult,       setDiffResult]       = useState(null)
  const [diffLoading,      setDiffLoading]      = useState(false)

  // Filters (shared across tabs)
  const [search,       setSearch]       = useState('')
  const [urgency,      setUrgency]      = useState('')
  const [jurisdiction, setJurisdiction] = useState('')
  const [days,         setDays]         = useState(365)

  // ── Data loading ──────────────────────────────────────────────────────────

  const loadActive = useCallback(async () => {
    setLoading(true)
    try {
      let res
      if (search.trim()) {
        // Use ranked search endpoint when a query is present
        const params = new URLSearchParams({
          q: search.trim(), limit: 30, days,
        })
        if (jurisdiction) params.set('jurisdiction', jurisdiction)
        if (urgency)      params.set('urgency', urgency)
        res = await fetch(`/api/search?${params}`).then(r => r.json())
        // search endpoint returns {items, total, expanded_query}
        setDocs(res.items || [])
        setTotal(res.total || 0)
        setPages(1)
      } else {
        res = await api.documents({ urgency, jurisdiction, days, page, page_size: 30, ...(domain ? { domain } : {}) })
        setDocs(res.items || [])
        setTotal(res.total || 0)
        setPages(res.pages || 1)
      }
    } finally { setLoading(false) }
  }, [search, urgency, jurisdiction, days, page, domain])  // domain from local state

  const loadArchived = useCallback(async () => {
    setArchivedLoading(true)
    try {
      const params = new URLSearchParams({ page: archivedPage, page_size: 30 })
      if (jurisdiction) params.set('jurisdiction', jurisdiction)
      if (search)       params.set('search', search)
      const res = await fetch(`/api/documents/archived?${params}`).then(r => r.json())
      setArchived(res.items || [])
      setArchivedTotal(res.total || 0)
      setArchivedPages(res.pages || 1)
    } finally { setArchivedLoading(false) }
  }, [jurisdiction, search, archivedPage])

  useEffect(() => {
    if (tab === 'active')   loadActive()
    if (tab === 'archived') loadArchived()
  }, [tab, loadActive, loadArchived])

  // ── Feedback handler ──────────────────────────────────────────────────────

  const handleFeedback = useCallback((feedback) => {
    if (feedback === 'not_relevant') {
      // Immediately remove from active list and close detail panel
      setDocs(prev => prev.filter(d => d.id !== selected?.id))
      setTotal(prev => Math.max(0, prev - 1))
      setSelected(null)
      setDetail(null)
    } else if (feedback === 'relevant' || feedback === 'partially_relevant') {
      // Update review_status in list so badge appears immediately
      setDocs(prev => prev.map(d =>
        d.id === selected?.id ? { ...d, review_status: feedback } : d
      ))
    }
  }, [selected])

  // ── Detail panel ──────────────────────────────────────────────────────────

  const openDetail = async (doc) => {
    setSelected(doc)
    setDetail(null)
    setChecklist(null)
    setDiffResult(null)
    setLoadingDetail(true)
    try {
      const d = await api.document(doc.id)
      setDetail(d)
    } finally { setLoadingDetail(false) }
  }

  const generateChecklist = async () => {
    if (!selected) return
    setChecklistLoading(true)
    try {
      const res = await api.checklist(selected.id, companyCtx || undefined)
      setChecklist(res.checklist)
      setShowChecklist(true)
    } catch (e) { alert(e.message) }
    finally { setChecklistLoading(false) }
  }

  const runDiff = async () => {
    if (!selected || !diffTarget.trim()) return
    setDiffLoading(true)
    try {
      await api.manualDiff(selected.id, diffTarget.trim())
      let attempts = 0
      const poll = setInterval(async () => {
        const status = await api.runStatus()
        if (!status.running) {
          clearInterval(poll)
          setDiffResult(status.last_result)
          setDiffLoading(false)
        }
        if (++attempts > 30) { clearInterval(poll); setDiffLoading(false) }
      }, 2000)
    } catch (e) { alert(e.message); setDiffLoading(false) }
  }

  // ── Shared filter row ─────────────────────────────────────────────────────

  const filterRow = (
    <div className="flex gap-3" style={{ marginBottom: 20, flexWrap: 'wrap' }}>
      <div style={{ position: 'relative', flex: '1', minWidth: 180 }}>
        <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)' }} />
        <input
          placeholder="Search titles, summaries…"
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(1); setArchivedPage(1) }}
          style={{ paddingLeft: 30 }}
        />
      </div>
      <select value={jurisdiction} onChange={e => { setJurisdiction(e.target.value); setPage(1); setArchivedPage(1) }} style={{ width: 120 }}>
        {JURISDICTIONS.map(j => <option key={j} value={j}>{j || 'All Jurisdictions'}</option>)}
      </select>
      {tab === 'active' && (
        <>
          <select value={urgency} onChange={e => { setUrgency(e.target.value); setPage(1) }} style={{ width: 120 }}>
            {URGENCIES.map(u => <option key={u} value={u}>{u || 'All Urgencies'}</option>)}
          </select>
          <select value={days} onChange={e => { setDays(Number(e.target.value)); setPage(1) }} style={{ width: 110 }}>
            <option value={14}>14 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
            <option value={180}>6 months</option>
            <option value={365}>1 year</option>
            <option value={3650}>All time</option>
          </select>
        </>
      )}
    </div>
  )

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>

      {/* ── Left panel - list ── */}
      <div style={{ flex: selected ? '0 0 55%' : '1', overflow: 'auto', padding: '28px 32px', borderRight: selected ? '1px solid var(--border)' : 'none' }}>

        <ViewHeader
          title="Documents"
          subtitle={tab === 'active' ? `${total} active` : `${archivedTotal} archived`}
          domain={domain}
          onDomainChange={handleDomainChange}
          action={
            <a href={api.exportJson({ days })} download="aris_export.json">
              <button className="btn-secondary btn-sm"><Download size={13} />Export JSON</button>
            </a>
          }
        />

        {/* Active / Archived tab toggle */}
        <div className="flex" style={{ borderBottom: '1px solid var(--border)', marginBottom: 20 }}>
          {[
            { id: 'active',   label: `Active${total > 0 ? ` (${total})` : ''}` },
            { id: 'archived', label: `Archived${archivedTotal > 0 ? ` (${archivedTotal})` : ''}` },
          ].map(t => (
            <button key={t.id} onClick={() => { setTab(t.id); setSelected(null) }} style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              padding: '7px 16px', fontSize: 13,
              fontWeight: tab === t.id ? 500 : 400,
              color: tab === t.id ? 'var(--text)' : 'var(--text-3)',
              borderBottom: tab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
              marginBottom: -1,
              display: 'flex', alignItems: 'center', gap: 6,
            }}>
              {t.id === 'archived' && <Archive size={12} style={{ opacity: 0.7 }} />}
              {t.label}
            </button>
          ))}
        </div>

        {filterRow}

        {/* Active list */}
        {tab === 'active' && (
          loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spinner /></div>
          ) : docs.length === 0 ? (
            <EmptyState
              title={domain ? `No ${domain === 'privacy' ? 'data privacy' : 'AI regulation'} documents found` : "No documents found"}
              message={domain
                ? `Run agents with domain=${domain === 'privacy' ? 'privacy' : 'ai'} to fetch ${domain === 'privacy' ? 'data privacy' : 'AI regulation'} documents, or switch to All to see everything.`
                : "Try adjusting your filters or run the agents to fetch new documents."
              }
            />
          ) : (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {docs.map(doc => (
                  <DocRow
                    key={doc.id}
                    doc={doc}
                    selected={selected?.id === doc.id}
                    onClick={() => openDetail(doc)}
                  />
                ))}
              </div>
              <Pagination page={page} pages={pages} onChange={setPage} />
            </>
          )
        )}

        {/* Archived list */}
        {tab === 'archived' && (
          archivedLoading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spinner /></div>
          ) : archived.length === 0 ? (
            <EmptyState
              icon={Archive}
              title="No archived documents"
              message="Documents marked Not Relevant will appear here. They are removed from the active list but never deleted."
            />
          ) : (
            <>
              <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 12, fontStyle: 'italic' }}>
                These documents were marked Not Relevant. They remain available for reference but do not appear in the active review queue.
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {archived.map(doc => (
                  <DocRow
                    key={doc.id}
                    doc={doc}
                    selected={selected?.id === doc.id}
                    onClick={() => openDetail(doc)}
                    archived
                  />
                ))}
              </div>
              <Pagination page={archivedPage} pages={archivedPages} onChange={setArchivedPage} />
            </>
          )
        )}
      </div>

      {/* ── Right panel - detail ── */}
      {selected && (
        <div style={{ flex: '0 0 45%', overflow: 'auto', padding: '28px 24px', background: 'var(--bg)' }}>
          <div className="flex items-center justify-between" style={{ marginBottom: 20 }}>
            <h2 style={{ fontWeight: 300, fontSize: '1rem', flex: 1, paddingRight: 12 }}>{selected.title}</h2>
            <button className="btn-icon" onClick={() => { setSelected(null); setDetail(null) }}><X size={16} /></button>
          </div>

          {loadingDetail ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spinner /></div>
          ) : detail ? (
            <>
              {/* Metadata */}
              <div style={{ marginBottom: 20 }}>
                <KeyValue label="Jurisdiction" value={<Badge level={detail.jurisdiction}>{detail.jurisdiction}</Badge>} />
                <KeyValue label="Type"         value={detail.doc_type} />
                <KeyValue label="Status"       value={detail.status} />
                <KeyValue label="Agency"       value={detail.agency} />
                <KeyValue label="Published"    value={detail.published_date?.slice(0,10)} />
                <KeyValue label="Urgency"      value={detail.summary ? <Badge level={detail.summary.urgency}>{detail.summary.urgency}</Badge> : null} />
                <KeyValue label="Deadline"     value={detail.summary?.deadline} />
                {detail.url && (
                  <div style={{ display: 'grid', gridTemplateColumns: '130px 1fr', gap: 8, padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Source</span>
                    <a href={detail.url} target="_blank" rel="noreferrer" className="flex items-center gap-1" style={{ fontSize: 12, color: 'var(--accent)' }}>
                      View original <ExternalLink size={11} />
                    </a>
                  </div>
                )}
              </div>

              {/* Summary */}
              {detail.summary?.plain_english && (
                <div style={{ marginBottom: 20 }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>Summary</div>
                  <p style={{ fontSize: 13, lineHeight: 1.65, color: 'var(--text-2)' }}>{detail.summary.plain_english}</p>
                </div>
              )}

              {/* Impact areas */}
              {detail.summary?.impact_areas?.length > 0 && (
                <div style={{ marginBottom: 16, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {detail.summary.impact_areas.map(a => (
                    <span key={a} className="badge badge-neutral">{a}</span>
                  ))}
                </div>
              )}

              {/* Requirements */}
              {detail.summary && (
                <>
                  <RequirementList items={detail.summary.requirements}    label="Mandatory Requirements" color="var(--red)" />
                  <RequirementList items={detail.summary.recommendations ?? []} label="Recommendations"        color="var(--yellow)" />
                  <RequirementList items={detail.summary.action_items}    label="Action Items"           color="var(--accent)" />
                </>
              )}

              {/* Feedback - hidden for archived docs (already reviewed as not_relevant) */}
              {tab !== 'archived' && (
                <div style={{ marginTop: 20, padding: '14px 16px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                  <FeedbackButtons
                    documentId={selected.id}
                    initialStatus={selected.review_status}
                    onFeedback={handleFeedback}
                  />
                </div>
              )}

              {/* Archived label shown instead of feedback buttons for archived docs */}
              {tab === 'archived' && (
                <div style={{ marginTop: 20, padding: '10px 14px', background: 'rgba(224,82,82,0.07)', border: '1px solid rgba(224,82,82,0.25)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--text-3)', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Archive size={13} style={{ color: 'var(--red)', flexShrink: 0 }} />
                  Archived - marked Not Relevant. Feedback recorded.
                </div>
              )}

              {/* Action buttons */}
              <div className="flex gap-2" style={{ marginTop: 24, flexWrap: 'wrap' }}>
                <button className="btn-secondary btn-sm" onClick={() => setShowChecklist(true)}>
                  <ListChecks size={13} />Checklist
                </button>
                <button className="btn-secondary btn-sm" onClick={() => setShowDiff(true)}>
                  <GitCompare size={13} />Compare
                </button>
              </div>

              {/* Change history */}
              {detail.diffs?.length > 0 && (
                <div style={{ marginTop: 20 }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
                    Change History ({detail.diffs.length})
                  </div>
                  {detail.diffs.slice(0, 4).map(d => (
                    <div key={d.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 12 }}>
                      <div className="flex items-center gap-2">
                        <Badge level={d.severity}>{d.severity}</Badge>
                        <span style={{ color: 'var(--text-2)' }}>{d.relationship_type || d.diff_type}</span>
                        <span style={{ marginLeft: 'auto', color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{d.detected_at?.slice(0,10)}</span>
                      </div>
                      {d.change_summary && <p style={{ color: 'var(--text-3)', marginTop: 4, lineHeight: 1.4 }}>{d.change_summary}</p>}
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : null}
        </div>
      )}

      {/* ── Checklist modal ── */}
      {showChecklist && selected && (
        <Modal title="Compliance Checklist Generator" onClose={() => setShowChecklist(false)} width={680}>
          {!checklist ? (
            <>
              <p style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 16, lineHeight: 1.6 }}>
                Claude will generate a structured compliance checklist for <strong>{selected.title}</strong>.
                Optionally describe your company for more targeted items.
              </p>
              <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 6 }}>Company context (optional)</label>
              <input
                placeholder="e.g. healthcare AI startup, Fortune 500 retailer, fintech platform…"
                value={companyCtx}
                onChange={e => setCompanyCtx(e.target.value)}
                style={{ marginBottom: 16 }}
              />
              <button className="btn-primary" onClick={generateChecklist} disabled={checklistLoading}>
                {checklistLoading ? <><Spinner size={13} /> Generating…</> : <><ListChecks size={13} />Generate Checklist</>}
              </button>
            </>
          ) : (
            <>
              <div className="markdown" style={{ maxHeight: 520, overflow: 'auto' }}>
                <ReactMarkdown>{checklist}</ReactMarkdown>
              </div>
              <div className="flex gap-2" style={{ marginTop: 16 }}>
                <button className="btn-secondary btn-sm" onClick={() => {
                  const blob = new Blob([checklist], { type: 'text/markdown' })
                  const url  = URL.createObjectURL(blob)
                  const a    = document.createElement('a')
                  a.href     = url
                  a.download = `checklist_${selected.id.slice(0,20)}.md`
                  a.click()
                }}>
                  <Download size={12} /> Download .md
                </button>
                <button className="btn-ghost btn-sm" onClick={() => setChecklist(null)}>Regenerate</button>
              </div>
            </>
          )}
        </Modal>
      )}

      {/* ── Diff modal ── */}
      {showDiff && selected && (
        <Modal title="Compare Documents" onClose={() => { setShowDiff(false); setDiffResult(null) }} width={680}>
          {!diffResult ? (
            <>
              <p style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 16 }}>
                Compare <strong style={{ color: 'var(--text)' }}>{selected.title}</strong> against another document.
              </p>
              <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 6 }}>Target document ID</label>
              <input
                placeholder="e.g. FR-2025-00456 or EU-CELEX-32024R1689"
                value={diffTarget}
                onChange={e => setDiffTarget(e.target.value)}
                style={{ marginBottom: 16 }}
              />
              <button className="btn-primary" onClick={runDiff} disabled={diffLoading || !diffTarget.trim()}>
                {diffLoading ? <><Spinner size={13} />Comparing…</> : <><GitCompare size={13} />Run Comparison</>}
              </button>
            </>
          ) : (
            <DiffResultView result={diffResult} />
          )}
        </Modal>
      )}
    </div>
  )
}

// ── Document row ──────────────────────────────────────────────────────────────

function DocRow({ doc, selected, onClick, archived = false }) {
  return (
    <div
      className="card card-hover"
      style={{
        padding: '12px 16px',
        borderColor: selected ? 'var(--accent-dim)' : 'var(--border)',
        background:  selected ? 'var(--bg-3)' : 'var(--bg-2)',
        opacity:     archived ? 0.75 : 1,
      }}
      onClick={onClick}
    >
      <div className="flex items-center gap-3">
        <UrgencyDot level={doc.urgency} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 500 }} className="truncate">{doc.title}</div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2, fontFamily: 'var(--font-mono)' }}>
            {doc.agency} · {(doc.published_date || doc.fetched_at)?.slice(0,10)}
          </div>
        </div>

        {/* Review badge - shown when doc has been marked relevant/partially */}
        <ReviewBadge status={doc.review_status} />

        <Badge level={doc.jurisdiction}>{doc.jurisdiction}</Badge>

        {doc.urgency === 'Skipped'
          ? <span className="badge" style={{ background: 'rgba(96,112,112,0.2)', color: 'var(--text-3)', fontFamily: 'var(--font-mono)', fontSize: 10 }} title={doc.plain_english}>Skipped</span>
          : doc.urgency
          ? <Badge level={doc.urgency} />
          : !archived && <span className="badge badge-neutral" title="Not yet summarized">Pending</span>
        }

        <ChevronRight size={13} style={{ color: 'var(--text-3)' }} />
      </div>

      {doc.urgency === 'Skipped' ? (
        <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 8, fontStyle: 'italic' }} className="truncate">
          {doc.plain_english?.replace('[Pre-filter skipped] ', '') || 'Filtered by relevance pre-filter'}
          {' '}
          <span style={{ color: 'var(--accent)', cursor: 'pointer' }}>Use Force Summarize to override</span>
        </div>
      ) : doc.plain_english ? (
        <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 8, lineHeight: 1.5 }} className="truncate">
          {doc.plain_english}
        </div>
      ) : !archived ? (
        <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 8, fontStyle: 'italic' }}>
          Awaiting AI summarization - run agents to generate summary
        </div>
      ) : null}
    </div>
  )
}

// ── Diff result ───────────────────────────────────────────────────────────────

function DiffResultView({ result }) {
  if (!result) return <div style={{ color: 'var(--text-3)' }}>No substantive difference found.</div>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="flex items-center gap-3">
        <Badge level={result.severity}>{result.severity}</Badge>
        <span style={{ fontWeight: 500 }}>{result.relationship_type || result.diff_type}</span>
      </div>
      <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6 }}>{result.change_summary}</p>
      {result.added_requirements?.length > 0 && (
        <RequirementList items={result.added_requirements}    label="New Requirements Added"  color="var(--red)" />
      )}
      {result.removed_requirements?.length > 0 && (
        <RequirementList items={result.removed_requirements}  label="Requirements Removed"    color="var(--green)" />
      )}
      {result.modified_requirements?.length > 0 && (
        <RequirementList items={result.modified_requirements} label="Modified Requirements"   color="var(--yellow)" />
      )}
      {result.deadline_changes?.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', textTransform: 'uppercase', color: 'var(--blue)', marginBottom: 6 }}>Deadline Changes</div>
          {result.deadline_changes.map((d, i) => (
            <div key={i} style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 4 }}>
              {d.description} - <span style={{ color: 'var(--red)' }}>{d.old_deadline}</span> → <span style={{ color: 'var(--green)' }}>{d.new_deadline}</span>
            </div>
          ))}
        </div>
      )}
      {result.new_action_items?.length > 0 && (
        <RequirementList items={result.new_action_items} label="New Action Items" color="var(--accent)" />
      )}
      {result.overall_assessment && (
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, fontSize: 13, color: 'var(--text-2)', fontStyle: 'italic', lineHeight: 1.6 }}>
          {result.overall_assessment}
        </div>
      )}
    </div>
  )
}

