import { useState, useEffect, useCallback } from 'react'
import {
  Search, ExternalLink, FileText, ListChecks, GitCompare,
  X, Download, CheckCircle2, MinusCircle, Archive,
  ChevronUp, ChevronDown, LayoutList, LayoutGrid,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import { api } from '../api.js'
import {
  Badge, UrgencyDot, Spinner, EmptyState, Modal,
  RequirementList, KeyValue, DomainFilter, ViewHeader,
} from '../components.jsx'
import { FeedbackButtons } from './Learning.jsx'

// ── Constants ─────────────────────────────────────────────────────────────────

const URGENCIES     = ['Critical', 'High', 'Medium', 'Low', 'Skipped']
const DOC_TYPES     = [
  'Bill', 'Code of Practice', 'Commission Guidelines',
  'International Agreement', 'Legislation', 'Legislation (Enacted)',
  'Notice', 'Publication / Guidance', 'Regulation', 'Rule',
]
const DATE_OPTS = [
  { label: '14 days',  value: 14  },
  { label: '30 days',  value: 30  },
  { label: '90 days',  value: 90  },
  { label: '6 months', value: 180 },
  { label: '1 year',   value: 365 },
  { label: 'All time', value: 3650 },
]
const SORT_COLS = {
  urgency:      { label: 'Urgency'    },
  published_date:{ label: 'Published' },
  fetched_date:  { label: 'Fetched'   },
  jurisdiction:  { label: 'Jurisdiction' },
}

// ── Review badge ──────────────────────────────────────────────────────────────

function ReviewBadge({ status }) {
  if (status === 'relevant')
    return <CheckCircle2 size={13} style={{ color: 'var(--green)', flexShrink: 0 }} title="Reviewed — Relevant" />
  if (status === 'partially_relevant')
    return <MinusCircle  size={13} style={{ color: 'var(--yellow)', flexShrink: 0 }} title="Reviewed — Partially Relevant" />
  return null
}

// ── Urgency badge for table ───────────────────────────────────────────────────

function UrgencyBadge({ urgency }) {
  if (!urgency) return <span style={{ fontSize: 11, color: 'var(--text-3)', fontStyle: 'italic' }}>Pending</span>
  const colors = {
    Critical: { bg: 'rgba(224,82,82,.15)',   color: 'var(--red)'    },
    High:     { bg: 'rgba(224,131,74,.15)',  color: 'var(--orange)' },
    Medium:   { bg: 'rgba(212,168,67,.15)', color: 'var(--yellow)' },
    Low:      { bg: 'rgba(96,112,112,.15)', color: 'var(--text-3)' },
    Skipped:  { bg: 'rgba(96,112,112,.10)', color: 'var(--text-3)' },
  }
  const c = colors[urgency] || colors.Low
  return (
    <span style={{
      fontSize: 10, fontFamily: 'var(--font-mono)', fontWeight: 600,
      padding: '2px 6px', borderRadius: 3,
      background: c.bg, color: c.color,
    }}>
      {urgency.toUpperCase()}
    </span>
  )
}

// ── Sortable column header ────────────────────────────────────────────────────

function SortHeader({ col, sortBy, sortDir, onSort, children, style }) {
  const active = sortBy === col
  return (
    <div onClick={() => onSort(col)} style={{
      display: 'flex', alignItems: 'center', gap: 3, cursor: 'pointer',
      fontSize: 10, fontFamily: 'var(--font-mono)', textTransform: 'uppercase',
      letterSpacing: '.06em', userSelect: 'none',
      color: active ? 'var(--accent)' : 'var(--text-3)',
      ...style,
    }}>
      {children}
      {active
        ? (sortDir === 'asc' ? <ChevronUp size={10}/> : <ChevronDown size={10}/>)
        : <ChevronDown size={10} style={{ opacity: .3 }}/>}
    </div>
  )
}

// ── Active filter chip ────────────────────────────────────────────────────────

function FilterChip({ label, value, onRemove }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '2px 8px 2px 10px',
      background: 'var(--accent-dim)', border: '1px solid var(--accent)',
      borderRadius: 12, fontSize: 11, color: 'var(--accent)',
    }}>
      <span style={{ color: 'var(--text-3)', fontSize: 10 }}>{label}:</span> {value}
      <button onClick={onRemove} style={{
        background: 'none', border: 'none', cursor: 'pointer',
        color: 'var(--text-3)', lineHeight: 1, padding: 0, marginLeft: 2,
      }}>×</button>
    </span>
  )
}

// ── Doc table row ─────────────────────────────────────────────────────────────

function DocTableRow({ doc, selected, onClick, archived }) {
  const isPending = !doc.urgency && !archived
  return (
    <div
      onClick={onClick}
      style={{
        display: 'grid',
        gridTemplateColumns: '12px 1fr 96px 88px 88px 110px 88px 20px',
        gap: 0,
        padding: '0 12px',
        height: 40,
        alignItems: 'center',
        cursor: 'pointer',
        borderBottom: '1px solid var(--border)',
        background: selected ? 'var(--bg-3)' : 'transparent',
        opacity: archived ? 0.65 : isPending ? 0.7 : 1,
        transition: 'background 0.1s',
      }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.background = 'var(--bg-2)' }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.background = 'transparent' }}
    >
      {/* Urgency dot */}
      <UrgencyDot level={doc.urgency} />

      {/* Title + agency */}
      <div style={{ minWidth: 0, paddingRight: 16 }}>
        <div style={{
          fontSize: 12, fontWeight: 500, color: 'var(--text)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {doc.title}
        </div>
        <div style={{
          fontSize: 10, color: 'var(--text-3)', marginTop: 1,
          fontFamily: 'var(--font-mono)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {doc.agency || doc.source}
        </div>
      </div>

      {/* Published date — blank dash if missing */}
      <div style={{ fontSize: 11, color: doc.published_date ? 'var(--text-2)' : 'var(--text-3)' }}>
        {doc.published_date?.slice(0, 10) || '—'}
      </div>

      {/* Fetched date */}
      <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
        {doc.fetched_at?.slice(0, 10) || '—'}
      </div>

      {/* Jurisdiction */}
      <div>
        <Badge level={doc.jurisdiction}>{doc.jurisdiction}</Badge>
      </div>

      {/* Doc type */}
      <div style={{ fontSize: 11, color: 'var(--text-2)',
        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {doc.doc_type || '—'}
      </div>

      {/* Urgency badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <ReviewBadge status={doc.review_status} />
        <UrgencyBadge urgency={doc.urgency} />
      </div>

      {/* Chevron */}
      <div style={{ fontSize: 12, color: 'var(--text-3)' }}>›</div>
    </div>
  )
}

// ── Doc card (grid view) ──────────────────────────────────────────────────────

function DocCard({ doc, selected, onClick, archived }) {
  return (
    <div
      onClick={onClick}
      className="card card-hover"
      style={{
        padding: '12px 14px', cursor: 'pointer',
        borderColor: selected ? 'var(--accent-dim)' : 'var(--border)',
        background: selected ? 'var(--bg-3)' : 'var(--bg-2)',
        opacity: archived ? 0.65 : 1,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 6 }}>
        <UrgencyDot level={doc.urgency} style={{ marginTop: 3 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text)', lineHeight: 1.4,
            overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
            {doc.title}
          </div>
        </div>
      </div>
      <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginBottom: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {doc.agency || doc.source}
      </div>
      {doc.plain_english && (
        <div style={{ fontSize: 11, color: 'var(--text-3)', lineHeight: 1.5, marginBottom: 8,
          overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical' }}>
          {doc.plain_english}
        </div>
      )}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
        <Badge level={doc.jurisdiction}>{doc.jurisdiction}</Badge>
        {doc.doc_type && <span style={{ fontSize: 10, color: 'var(--text-3)' }}>{doc.doc_type}</span>}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4, alignItems: 'center' }}>
          <ReviewBadge status={doc.review_status} />
          <UrgencyBadge urgency={doc.urgency} />
        </div>
      </div>
      <div style={{ display: 'flex', gap: 12, marginTop: 6 }}>
        {doc.published_date && (
          <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
            Published {doc.published_date.slice(0, 10)}
          </span>
        )}
        {doc.fetched_at && (
          <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
            Fetched {doc.fetched_at.slice(0, 10)}
          </span>
        )}
      </div>
    </div>
  )
}

// ── Pagination ────────────────────────────────────────────────────────────────

function DocPagination({ page, pages, total, pageSize, onPage, onPageSize }) {
  const [jumpVal, setJumpVal] = useState('')

  const handleJump = (e) => {
    if (e.key === 'Enter') {
      const n = parseInt(jumpVal)
      if (n >= 1 && n <= pages) { onPage(n); setJumpVal('') }
    }
  }

  const pageNums = () => {
    if (pages <= 7) return Array.from({ length: pages }, (_, i) => i + 1)
    if (page <= 4) return [1, 2, 3, 4, 5, '…', pages]
    if (page >= pages - 3) return [1, '…', pages-4, pages-3, pages-2, pages-1, pages]
    return [1, '…', page-1, page, page+1, '…', pages]
  }

  const btnStyle = (active) => ({
    padding: '4px 9px', fontSize: 12, background: active ? 'var(--bg-3)' : 'var(--bg-2)',
    border: `1px solid ${active ? 'var(--accent-dim)' : 'var(--border)'}`,
    borderRadius: 5, cursor: active ? 'default' : 'pointer',
    color: active ? 'var(--accent)' : 'var(--text-2)',
  })

  const start = (page - 1) * pageSize + 1
  const end   = Math.min(page * pageSize, total)

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '12px 0', borderTop: '1px solid var(--border)', marginTop: 4 }}>

      <div style={{ fontSize: 12, color: 'var(--text-3)' }}>
        {total > 0 ? `${start}–${end} of ${total}` : '0 results'}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
        <button
          style={{ ...btnStyle(false), opacity: page === 1 ? 0.4 : 1 }}
          disabled={page === 1} onClick={() => onPage(page - 1)}>‹</button>

        {pageNums().map((n, i) =>
          n === '…'
            ? <span key={`e${i}`} style={{ padding: '0 4px', fontSize: 12, color: 'var(--text-3)' }}>…</span>
            : <button key={n} style={btnStyle(n === page)} onClick={() => n !== page && onPage(n)}>{n}</button>
        )}

        <button
          style={{ ...btnStyle(false), opacity: page === pages ? 0.4 : 1 }}
          disabled={page === pages} onClick={() => onPage(page + 1)}>›</button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginLeft: 10 }}>
          <span style={{ fontSize: 12, color: 'var(--text-3)' }}>Go to</span>
          <input
            value={jumpVal} onChange={e => setJumpVal(e.target.value)} onKeyDown={handleJump}
            placeholder="pg" style={{ width: 44, padding: '3px 6px', fontSize: 12, textAlign: 'center' }}
          />
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 12, color: 'var(--text-3)' }}>Per page</span>
        <select value={pageSize} onChange={e => onPageSize(Number(e.target.value))}
          style={{ fontSize: 12, padding: '3px 8px' }}>
          <option value={50}>50</option>
          <option value={100}>100</option>
          <option value={200}>200</option>
        </select>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Documents() {
  // Domain
  const [domain, setDomain] = useState(() => {
    try { return localStorage.getItem('aris_domain_documents') ?? null } catch { return null }
  })
  const handleDomainChange = (d) => {
    setDomain(d)
    try { localStorage.setItem('aris_domain_documents', d ?? '') } catch {}
  }

  // Tab
  const [tab, setTab] = useState('active')

  // Active tab state
  const [docs,    setDocs]    = useState([])
  const [total,   setTotal]   = useState(0)
  const [pages,   setPages]   = useState(1)
  const [page,    setPage]    = useState(1)
  const [pageSize,setPageSize]= useState(50)
  const [loading, setLoading] = useState(true)

  // Archived tab state
  const [archived,        setArchived]       = useState([])
  const [archivedTotal,   setArchivedTotal]  = useState(0)
  const [archivedPages,   setArchivedPages]  = useState(1)
  const [archivedPage,    setArchivedPage]   = useState(1)
  const [archivedLoading, setArchivedLoading]= useState(false)

  // Pending count for header badge
  const [pendingCount, setPendingCount] = useState(0)

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

  // Filters
  const [search,       setSearch]       = useState('')
  const [urgency,      setUrgency]      = useState('')
  const [docType,      setDocType]      = useState('')
  const [jurisdiction, setJurisdiction] = useState('')
  const [days,         setDays]         = useState(365)

  // Sort — column + direction
  const [sortBy,  setSortBy]  = useState('fetched_date')
  const [sortDir, setSortDir] = useState('desc')

  // View density
  const [viewMode, setViewMode] = useState('table')  // 'table' | 'grid'

  // ── Pending count ─────────────────────────────────────────────────────────

  useEffect(() => {
    api.status().then(s => {
      setPendingCount(s?.stats?.pending_summaries || 0)
    }).catch(() => {})
  }, [])

  // ── Sort handler ──────────────────────────────────────────────────────────

  const handleSort = (col) => {
    if (sortBy === col) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortBy(col)
      setSortDir('desc')
    }
    setPage(1)
  }

  // server sort_by values are always by descending; for asc we sort client-side after
  const serverSortBy = sortBy

  // ── Data loading ──────────────────────────────────────────────────────────

  const loadActive = useCallback(async () => {
    setLoading(true)
    try {
      let res
      if (search.trim()) {
        const params = new URLSearchParams({ q: search.trim(), limit: pageSize, days })
        if (jurisdiction) params.set('jurisdiction', jurisdiction)
        if (urgency)      params.set('urgency', urgency)
        if (docType)      params.set('doc_type', docType)
        if (domain)       params.set('domain', domain)
        res = await fetch(`/api/search?${params}`).then(r => r.json())
        setDocs(res.items || [])
        setTotal(res.total || 0)
        setPages(1)
      } else {
        res = await api.documents({
          urgency, jurisdiction, days, page, page_size: pageSize,
          sort_by: serverSortBy, doc_type: docType,
          ...(domain ? { domain } : {}),
        })
        let items = res.items || []
        // Client-side ascending sort flip
        if (sortDir === 'asc') items = [...items].reverse()
        setDocs(items)
        setTotal(res.total || 0)
        setPages(res.pages || 1)
      }
    } finally { setLoading(false) }
  }, [search, urgency, docType, jurisdiction, days, page, pageSize, domain, serverSortBy, sortDir])

  const loadArchived = useCallback(async () => {
    setArchivedLoading(true)
    try {
      const params = new URLSearchParams({ page: archivedPage, page_size: pageSize })
      if (jurisdiction) params.set('jurisdiction', jurisdiction)
      if (search)       params.set('search', search)
      const res = await fetch(`/api/documents/archived?${params}`).then(r => r.json())
      setArchived(res.items || [])
      setArchivedTotal(res.total || 0)
      setArchivedPages(res.pages || 1)
    } finally { setArchivedLoading(false) }
  }, [jurisdiction, search, archivedPage, pageSize])

  useEffect(() => {
    if (tab === 'active')   loadActive()
    if (tab === 'archived') loadArchived()
  }, [tab, loadActive, loadArchived])

  // ── Active filters list (for chip strip) ─────────────────────────────────

  const activeFilters = [
    jurisdiction && { key: 'jurisdiction', label: 'Jurisdiction', value: jurisdiction, clear: () => { setJurisdiction(''); setPage(1) } },
    urgency      && { key: 'urgency',      label: 'Urgency',      value: urgency,      clear: () => { setUrgency('');      setPage(1) } },
    docType      && { key: 'docType',      label: 'Doc type',     value: docType,      clear: () => { setDocType('');      setPage(1) } },
    days !== 365 && { key: 'days',         label: 'Date range',   value: DATE_OPTS.find(d => d.value === days)?.label || `${days}d`, clear: () => { setDays(365); setPage(1) } },
  ].filter(Boolean)

  const clearAll = () => {
    setJurisdiction(''); setUrgency(''); setDocType(''); setDays(365)
    setSearch(''); setPage(1)
  }

  // ── Feedback handler ──────────────────────────────────────────────────────

  const handleFeedback = useCallback((feedback) => {
    if (feedback === 'not_relevant') {
      setDocs(prev => prev.filter(d => d.id !== selected?.id))
      setTotal(prev => Math.max(0, prev - 1))
      setSelected(null); setDetail(null)
    } else {
      setDocs(prev => prev.map(d =>
        d.id === selected?.id ? { ...d, review_status: feedback } : d
      ))
    }
  }, [selected])

  // ── Detail panel ──────────────────────────────────────────────────────────

  const openDetail = async (doc) => {
    setSelected(doc); setDetail(null); setChecklist(null)
    setDiffResult(null); setLoadingDetail(true)
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
      setChecklist(res.checklist); setShowChecklist(true)
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
        if (!status.running) { clearInterval(poll); setDiffResult(status.last_result); setDiffLoading(false) }
        if (++attempts > 30) { clearInterval(poll); setDiffLoading(false) }
      }, 2000)
    } catch (e) { alert(e.message); setDiffLoading(false) }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const showingDocs = tab === 'active' ? docs : archived
  const currentLoading = tab === 'active' ? loading : archivedLoading

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>

      {/* ── Left panel — list ──────────────────────────────────────────────── */}
      <div style={{
        flex: selected ? '0 0 58%' : '1',
        overflow: 'auto', padding: '20px 24px',
        borderRight: selected ? '1px solid var(--border)' : 'none',
        display: 'flex', flexDirection: 'column',
      }}>

        {/* ── Page header ────────────────────────────────────────────────── */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
          <div>
            <h1 style={{ fontSize: '1.25rem', fontWeight: 300, marginBottom: 3 }}>Documents</h1>
            <div style={{ fontSize: 12, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', display: 'flex', gap: 10 }}>
              <span><span style={{ color: 'var(--text-2)' }}>{total}</span> active</span>
              {pendingCount > 0 && (
                <span style={{ color: 'var(--orange)' }}>
                  {pendingCount} pending
                </span>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            {/* Domain toggle */}
            <DomainFilter value={domain} onChange={handleDomainChange} />

            {/* Process pending quick-action */}
            {pendingCount > 0 && (
              <a href="/run" style={{ textDecoration: 'none' }}>
                <button className="btn-secondary btn-sm" style={{ borderColor: 'rgba(224,131,74,.4)', color: 'var(--orange)' }}>
                  ⟳ Process {pendingCount} pending
                </button>
              </a>
            )}

            {/* Export */}
            <a href={api.exportJson({ days })} download="aris_export.json">
              <button className="btn-secondary btn-sm"><Download size={12} /> Export</button>
            </a>

            {/* View toggle */}
            <div style={{ display: 'flex', background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
              {[
                { id: 'table', Icon: LayoutList,  title: 'Table view'  },
                { id: 'grid',  Icon: LayoutGrid,  title: 'Grid view'   },
              ].map(({ id, Icon, title }) => (
                <button key={id} title={title} onClick={() => setViewMode(id)} style={{
                  padding: '5px 9px', background: viewMode === id ? 'var(--bg-3)' : 'transparent',
                  border: 'none', cursor: 'pointer',
                  color: viewMode === id ? 'var(--accent)' : 'var(--text-3)',
                  borderRight: id === 'table' ? '1px solid var(--border)' : 'none',
                }}>
                  <Icon size={13} />
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* ── Active / Archived tabs ──────────────────────────────────────── */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border)', marginBottom: 12 }}>
          {[
            { id: 'active',   label: `Active (${total})` },
            { id: 'archived', label: `Archived (${archivedTotal})` },
          ].map(t => (
            <button key={t.id} onClick={() => { setTab(t.id); setSelected(null) }} style={{
              background: 'transparent', border: 'none', cursor: 'pointer',
              padding: '7px 14px', fontSize: 13,
              fontWeight: tab === t.id ? 500 : 400,
              color: tab === t.id ? 'var(--text)' : 'var(--text-3)',
              borderBottom: tab === t.id ? '2px solid var(--accent)' : '2px solid transparent',
              marginBottom: -1, display: 'flex', alignItems: 'center', gap: 6,
            }}>
              {t.id === 'archived' && <Archive size={12} style={{ opacity: .7 }} />}
              {t.label}
            </button>
          ))}
        </div>

        {/* ── Filter row ─────────────────────────────────────────────────── */}
        <div style={{ display: 'flex', gap: 5, marginBottom: 6, flexWrap: 'nowrap', alignItems: 'center', overflowX: 'auto' }}>

          {/* Search */}
          <div style={{ position: 'relative', flex: '1', minWidth: 150 }}>
            <Search size={11} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-3)', pointerEvents: 'none' }} />
            <input
              placeholder="Search titles, summaries…"
              value={search}
              onChange={e => { setSearch(e.target.value); setPage(1) }}
              style={{ paddingLeft: 27, height: 30, fontSize: 12, width: '100%' }}
            />
          </div>

          {/* Jurisdiction */}
          <select value={jurisdiction} onChange={e => { setJurisdiction(e.target.value); setPage(1) }}
            style={{ height: 30, fontSize: 12, minWidth: 0, flexShrink: 0 }}>
            <option value="">Jurisdiction</option>
            {['Federal','EU','GB','CA','AU','JP','SG','BR','IN','KR',
              'CO','IL','MN','NY','NJ','PA','VA','GA','TX','OR','CA_STATE','INTL'].map(j => (
              <option key={j} value={j}>{j}</option>
            ))}
          </select>

          {/* Urgency */}
          {tab === 'active' && (
            <select value={urgency} onChange={e => { setUrgency(e.target.value); setPage(1) }}
              style={{ height: 30, fontSize: 12, minWidth: 0, flexShrink: 0 }}>
              <option value="">Urgency</option>
              {URGENCIES.map(u => <option key={u} value={u}>{u}</option>)}
            </select>
          )}

          {/* Doc type */}
          {tab === 'active' && (
            <select value={docType} onChange={e => { setDocType(e.target.value); setPage(1) }}
              style={{ height: 30, fontSize: 12, minWidth: 0, flexShrink: 0 }}>
              <option value="">Doc type</option>
              {DOC_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          )}

          {/* Date range */}
          {tab === 'active' && (
            <select value={days} onChange={e => { setDays(Number(e.target.value)); setPage(1) }}
              style={{ height: 30, fontSize: 12, minWidth: 0, flexShrink: 0 }}>
              {DATE_OPTS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          )}
        </div>

        {/* ── Active filter chips ─────────────────────────────────────────── */}
        {activeFilters.length > 0 && (
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 8, minHeight: 24 }}>
            <span style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '.06em' }}>
              Filters:
            </span>
            {activeFilters.map(f => (
              <FilterChip key={f.key} label={f.label} value={f.value} onRemove={f.clear} />
            ))}
            <button onClick={clearAll} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontSize: 11, color: 'var(--text-3)', padding: '2px 6px',
              textDecoration: 'underline',
            }}>
              Clear all
            </button>
            <span style={{ fontSize: 11, color: 'var(--text-3)', marginLeft: 4 }}>
              {total} result{total !== 1 ? 's' : ''}
            </span>
          </div>
        )}

        {/* ── Table header (table view only) ──────────────────────────────── */}
        {viewMode === 'table' && tab === 'active' && !currentLoading && docs.length > 0 && (
          <div style={{
            display: 'grid',
            gridTemplateColumns: '12px 1fr 96px 88px 88px 110px 88px 20px',
            gap: 0, padding: '0 12px 6px',
            borderBottom: '2px solid var(--border)',
            marginBottom: 0,
          }}>
            <div />
            <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-3)' }}>Title</div>
            <SortHeader col="published_date" sortBy={sortBy} sortDir={sortDir} onSort={handleSort}>Published</SortHeader>
            <SortHeader col="fetched_date"   sortBy={sortBy} sortDir={sortDir} onSort={handleSort}>Fetched</SortHeader>
            <SortHeader col="jurisdiction"   sortBy={sortBy} sortDir={sortDir} onSort={handleSort}>Jurisdiction</SortHeader>
            <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '.06em', color: 'var(--text-3)' }}>Doc type</div>
            <SortHeader col="urgency" sortBy={sortBy} sortDir={sortDir} onSort={handleSort}>Urgency</SortHeader>
            <div />
          </div>
        )}

        {/* ── Document list ───────────────────────────────────────────────── */}
        {currentLoading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spinner /></div>
        ) : showingDocs.length === 0 ? (
          <EmptyState
            title={domain
              ? `No ${domain === 'privacy' ? 'data privacy' : 'AI regulation'} documents found`
              : 'No documents found'}
            message={activeFilters.length > 0
              ? 'Try adjusting or clearing your filters.'
              : 'Run agents to fetch documents.'}
          />
        ) : viewMode === 'table' ? (
          <>
            <div>
              {showingDocs.map(doc => (
                <DocTableRow
                  key={doc.id}
                  doc={doc}
                  selected={selected?.id === doc.id}
                  onClick={() => openDetail(doc)}
                  archived={tab === 'archived'}
                />
              ))}
            </div>
            {tab === 'active' ? (
              <DocPagination
                page={page} pages={pages} total={total} pageSize={pageSize}
                onPage={p => { setPage(p) }} onPageSize={s => { setPageSize(s); setPage(1) }}
              />
            ) : (
              <DocPagination
                page={archivedPage} pages={archivedPages} total={archivedTotal} pageSize={pageSize}
                onPage={p => setArchivedPage(p)} onPageSize={s => { setPageSize(s); setArchivedPage(1) }}
              />
            )}
          </>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10, marginTop: 4 }}>
              {showingDocs.map(doc => (
                <DocCard
                  key={doc.id}
                  doc={doc}
                  selected={selected?.id === doc.id}
                  onClick={() => openDetail(doc)}
                  archived={tab === 'archived'}
                />
              ))}
            </div>
            {tab === 'active' ? (
              <DocPagination
                page={page} pages={pages} total={total} pageSize={pageSize}
                onPage={p => setPage(p)} onPageSize={s => { setPageSize(s); setPage(1) }}
              />
            ) : (
              <DocPagination
                page={archivedPage} pages={archivedPages} total={archivedTotal} pageSize={pageSize}
                onPage={p => setArchivedPage(p)} onPageSize={s => { setPageSize(s); setArchivedPage(1) }}
              />
            )}
          </>
        )}
      </div>

      {/* ── Right panel — detail ───────────────────────────────────────────── */}
      {selected && (
        <div style={{ flex: '0 0 42%', overflow: 'auto', padding: '20px 22px', background: 'var(--bg)' }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16, gap: 10 }}>
            <h2 style={{ fontWeight: 300, fontSize: '.95rem', flex: 1, lineHeight: 1.4 }}>{selected.title}</h2>
            <button className="btn-icon" onClick={() => { setSelected(null); setDetail(null) }}><X size={16} /></button>
          </div>

          {loadingDetail ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spinner /></div>
          ) : detail ? (
            <>
              <div style={{ marginBottom: 18 }}>
                <KeyValue label="Jurisdiction" value={<Badge level={detail.jurisdiction}>{detail.jurisdiction}</Badge>} />
                <KeyValue label="Type"         value={detail.doc_type} />
                <KeyValue label="Status"       value={detail.status} />
                <KeyValue label="Agency"       value={detail.agency} />
                <KeyValue label="Published"    value={detail.published_date?.slice(0, 10)} />
                <KeyValue label="Fetched"      value={detail.fetched_at?.slice(0, 10)} />
                <KeyValue label="Urgency"      value={detail.summary ? <Badge level={detail.summary.urgency}>{detail.summary.urgency}</Badge> : null} />
                <KeyValue label="Deadline"     value={detail.summary?.deadline} />
                {detail.url && (
                  <div style={{ display: 'grid', gridTemplateColumns: '130px 1fr', gap: 8, padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.05em' }}>Source</span>
                    <a href={detail.url} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: 4 }}>
                      View original <ExternalLink size={11} />
                    </a>
                  </div>
                )}
              </div>

              {detail.summary?.plain_english && (
                <div style={{ marginBottom: 18 }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>Summary</div>
                  <p style={{ fontSize: 13, lineHeight: 1.65, color: 'var(--text-2)' }}>{detail.summary.plain_english}</p>
                </div>
              )}

              {detail.summary?.impact_areas?.length > 0 && (
                <div style={{ marginBottom: 14, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                  {detail.summary.impact_areas.map(a => (
                    <span key={a} className="badge badge-neutral">{a}</span>
                  ))}
                </div>
              )}

              {detail.summary && (
                <>
                  <RequirementList items={detail.summary.requirements    ?? []} label="Mandatory Requirements" color="var(--red)" />
                  <RequirementList items={detail.summary.recommendations ?? []} label="Recommendations"        color="var(--yellow)" />
                  <RequirementList items={detail.summary.action_items    ?? []} label="Action Items"           color="var(--accent)" />
                </>
              )}

              {tab !== 'archived' && (
                <div style={{ marginTop: 18, padding: '14px 16px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}>
                  <FeedbackButtons
                    documentId={selected.id}
                    initialStatus={selected.review_status}
                    onFeedback={handleFeedback}
                  />
                </div>
              )}

              {tab === 'archived' && (
                <div style={{ marginTop: 18, padding: '10px 14px', background: 'rgba(224,82,82,.07)', border: '1px solid rgba(224,82,82,.25)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--text-3)', display: 'flex', alignItems: 'center', gap: 8 }}>
                  <Archive size={13} style={{ color: 'var(--red)', flexShrink: 0 }} />
                  Archived — marked Not Relevant. Feedback recorded.
                </div>
              )}

              <div style={{ display: 'flex', gap: 8, marginTop: 20, flexWrap: 'wrap' }}>
                <button className="btn-secondary btn-sm" onClick={() => setShowChecklist(true)}>
                  <ListChecks size={13} /> Checklist
                </button>
                <button className="btn-secondary btn-sm" onClick={() => setShowDiff(true)}>
                  <GitCompare size={13} /> Compare
                </button>
              </div>

              {detail.diffs?.length > 0 && (
                <div style={{ marginTop: 18 }}>
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 8 }}>
                    Change History ({detail.diffs.length})
                  </div>
                  {detail.diffs.slice(0, 4).map(d => (
                    <div key={d.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--border)', fontSize: 12 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <Badge level={d.severity}>{d.severity}</Badge>
                        <span style={{ color: 'var(--text-2)' }}>{d.relationship_type || d.diff_type}</span>
                        <span style={{ marginLeft: 'auto', color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>{d.detected_at?.slice(0, 10)}</span>
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

      {/* ── Checklist modal ───────────────────────────────────────────────── */}
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
                placeholder="e.g. healthcare AI startup, Fortune 500 retailer…"
                value={companyCtx} onChange={e => setCompanyCtx(e.target.value)}
                style={{ marginBottom: 16 }}
              />
              <button className="btn-primary" onClick={generateChecklist} disabled={checklistLoading}>
                {checklistLoading ? <><Spinner size={13} /> Generating…</> : <><ListChecks size={13} /> Generate Checklist</>}
              </button>
            </>
          ) : (
            <>
              <div className="markdown" style={{ maxHeight: 520, overflow: 'auto' }}>
                <ReactMarkdown>{checklist}</ReactMarkdown>
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
                <button className="btn-secondary btn-sm" onClick={() => {
                  const blob = new Blob([checklist], { type: 'text/markdown' })
                  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `checklist_${selected.id.slice(0,20)}.md` })
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

      {/* ── Diff modal ───────────────────────────────────────────────────── */}
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
                value={diffTarget} onChange={e => setDiffTarget(e.target.value)}
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

// ── Diff result view ──────────────────────────────────────────────────────────

function DiffResultView({ result }) {
  if (!result) return <div style={{ color: 'var(--text-3)' }}>No substantive difference found.</div>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <Badge level={result.severity}>{result.severity}</Badge>
        <span style={{ fontWeight: 500 }}>{result.relationship_type || result.diff_type}</span>
      </div>
      <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6 }}>{result.change_summary}</p>
      <RequirementList items={result.added_requirements    ?? []} label="New Requirements Added" color="var(--red)" />
      <RequirementList items={result.removed_requirements  ?? []} label="Requirements Removed"   color="var(--green)" />
      <RequirementList items={result.modified_requirements ?? []} label="Modified Requirements"  color="var(--yellow)" />
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
      <RequirementList items={result.new_action_items ?? []} label="New Action Items" color="var(--accent)" />
      {result.overall_assessment && (
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, fontSize: 13, color: 'var(--text-2)', fontStyle: 'italic', lineHeight: 1.6 }}>
          {result.overall_assessment}
        </div>
      )}
    </div>
  )
}
