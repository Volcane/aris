import { useState, useEffect, useCallback } from 'react'
import { Search, ExternalLink, FileText, ListChecks, GitCompare, X, ChevronRight, Download } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api.js'
import { Badge, UrgencyDot, Spinner, EmptyState, Modal, Pagination, RequirementList, KeyValue, SectionHeader } from '../components.jsx'
import { FeedbackButtons } from './Learning.jsx'

const URGENCIES = ['', 'Critical', 'High', 'Medium', 'Low']
const JURISDICTIONS = ['', 'Federal', 'PA', 'EU', 'GB', 'CA', 'JP', 'CN', 'AU']

export default function Documents() {
  const [docs,     setDocs]     = useState([])
  const [total,    setTotal]    = useState(0)
  const [pages,    setPages]    = useState(1)
  const [page,     setPage]     = useState(1)
  const [loading,  setLoading]  = useState(true)
  const [selected, setSelected] = useState(null)
  const [detail,   setDetail]   = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [checklist, setChecklist] = useState(null)
  const [checklistLoading, setChecklistLoading] = useState(false)
  const [companyCtx, setCompanyCtx] = useState('')
  const [showChecklist, setShowChecklist] = useState(false)
  const [showDiff, setShowDiff] = useState(false)
  const [diffTarget, setDiffTarget] = useState('')
  const [diffResult, setDiffResult] = useState(null)
  const [diffLoading, setDiffLoading] = useState(false)

  // Filters
  const [search,       setSearch]       = useState('')
  const [urgency,      setUrgency]      = useState('')
  const [jurisdiction, setJurisdiction] = useState('')
  const [days,         setDays]         = useState(365)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await api.documents({ search, urgency, jurisdiction, days, page, page_size: 30 })
      setDocs(res.items || [])
      setTotal(res.total || 0)
      setPages(res.pages || 1)
    } finally { setLoading(false) }
  }, [search, urgency, jurisdiction, days, page])

  useEffect(() => { load() }, [load])

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
      // Poll for result
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

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* ── Document list ── */}
      <div style={{ flex: selected ? '0 0 55%' : '1', overflow: 'auto', padding: '28px 32px', borderRight: selected ? '1px solid var(--border)' : 'none' }}>
        <SectionHeader
          title="Documents"
          subtitle={`${total} total`}
          action={
            <a href={api.exportJson({ days })} download="aris_export.json">
              <button className="btn-secondary btn-sm"><Download size={13} />Export JSON</button>
            </a>
          }
        />

        {/* Filters */}
        <div className="flex gap-3" style={{ marginBottom: 20, flexWrap: 'wrap' }}>
          <div style={{ position: 'relative', flex: '1', minWidth: 180 }}>
            <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)' }} />
            <input
              placeholder="Search titles, summaries…"
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              style={{ paddingLeft: 30 }}
            />
          </div>
          <select value={jurisdiction} onChange={e => { setJurisdiction(e.target.value); setPage(1) }} style={{ width: 120 }}>
            {JURISDICTIONS.map(j => <option key={j} value={j}>{j || 'All Jurisdictions'}</option>)}
          </select>
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
        </div>

        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spinner /></div>
        ) : docs.length === 0 ? (
          <EmptyState title="No documents found" message="Try adjusting your filters or run the agents to fetch new data." />
        ) : (
          <>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {docs.map(doc => (
                <div
                  key={doc.id}
                  className="card card-hover"
                  style={{
                    padding: '12px 16px',
                    borderColor: selected?.id === doc.id ? 'var(--accent-dim)' : 'var(--border)',
                    background: selected?.id === doc.id ? 'var(--bg-3)' : 'var(--bg-2)',
                  }}
                  onClick={() => openDetail(doc)}
                >
                  <div className="flex items-center gap-3">
                    <UrgencyDot level={doc.urgency} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 500 }} className="truncate">{doc.title}</div>
                      <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2, fontFamily: 'var(--font-mono)' }}>
                        {doc.agency} · {(doc.published_date || doc.fetched_at)?.slice(0,10)}
                      </div>
                    </div>
                    <Badge level={doc.jurisdiction}>{doc.jurisdiction}</Badge>
                    {doc.urgency
                      ? <Badge level={doc.urgency} />
                      : <span className="badge badge-neutral" title="Not yet summarized">Pending</span>
                    }
                    <ChevronRight size={13} style={{ color: 'var(--text-3)' }} />
                  </div>
                  {doc.plain_english ? (
                    <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 8, lineHeight: 1.5 }} className="truncate">
                      {doc.plain_english}
                    </div>
                  ) : (
                    <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 8, fontStyle: 'italic' }}>
                      Awaiting AI summarization — run agents to generate summary
                    </div>
                  )}
                </div>
              ))}
            </div>
            <Pagination page={page} pages={pages} onChange={setPage} />
          </>
        )}
      </div>

      {/* ── Detail panel ── */}
      {selected && (
        <div style={{ flex: '0 0 45%', overflow: 'auto', padding: '28px 24px', background: 'var(--bg)' }}>
          <div className="flex items-center justify-between" style={{ marginBottom: 20 }}>
            <h2 style={{ fontWeight: 300, fontSize: '1rem', flex: 1, paddingRight: 12 }}>{selected.title}</h2>
            <button className="btn-icon" onClick={() => setSelected(null)}><X size={16} /></button>
          </div>

          {loadingDetail ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spinner /></div>
          ) : detail ? (
            <>
              {/* Metadata */}
              <div style={{ marginBottom: 20 }}>
                <KeyValue label="Jurisdiction" value={<Badge level={detail.jurisdiction}>{detail.jurisdiction}</Badge>} />
                <KeyValue label="Type" value={detail.doc_type} />
                <KeyValue label="Status" value={detail.status} />
                <KeyValue label="Agency" value={detail.agency} />
                <KeyValue label="Published" value={detail.published_date?.slice(0,10)} />
                <KeyValue label="Urgency" value={detail.summary ? <Badge level={detail.summary.urgency}>{detail.summary.urgency}</Badge> : null} />
                <KeyValue label="Deadline" value={detail.summary?.deadline} />
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

              {/* Requirements / Recommendations / Actions */}
              {detail.summary && (
                <>
                  <RequirementList items={detail.summary.requirements}    label="Mandatory Requirements" color="var(--red)" />
                  <RequirementList items={detail.summary.recommendations} label="Recommendations"         color="var(--yellow)" />
                  <RequirementList items={detail.summary.action_items}    label="Action Items"           color="var(--accent)" />
                </>
              )}

              {/* Feedback */}
              <div style={{ marginTop: 20, padding: '14px 16px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                <FeedbackButtons documentId={selected.id} onFeedback={() => {}} />
              </div>

              {/* Actions bar */}
              <div className="flex gap-2" style={{ marginTop: 24, flexWrap: 'wrap' }}>
                <button className="btn-secondary btn-sm" onClick={() => setShowChecklist(true)}>
                  <ListChecks size={13} />Checklist
                </button>
                <button className="btn-secondary btn-sm" onClick={() => setShowDiff(true)}>
                  <GitCompare size={13} />Compare
                </button>
              </div>

              {/* Related / history */}
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
              <button
                className="btn-primary"
                onClick={generateChecklist}
                disabled={checklistLoading}
              >
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
                  a.href = url
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
              <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 6 }}>
                Target document ID
              </label>
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
        <RequirementList items={result.added_requirements} label="New Requirements Added" color="var(--red)" />
      )}
      {result.removed_requirements?.length > 0 && (
        <RequirementList items={result.removed_requirements} label="Requirements Removed" color="var(--green)" />
      )}
      {result.modified_requirements?.length > 0 && (
        <RequirementList items={result.modified_requirements} label="Modified Requirements" color="var(--yellow)" />
      )}
      {result.deadline_changes?.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', textTransform: 'uppercase', color: 'var(--blue)', marginBottom: 6 }}>Deadline Changes</div>
          {result.deadline_changes.map((d, i) => (
            <div key={i} style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 4 }}>
              {d.description} — <span style={{ color: 'var(--red)' }}>{d.old_deadline}</span> → <span style={{ color: 'var(--green)' }}>{d.new_deadline}</span>
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
