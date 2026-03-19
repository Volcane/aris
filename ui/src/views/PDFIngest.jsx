import { useState, useEffect, useRef } from 'react'
import {
  FileText, Download, Upload, Inbox, CheckCircle2,
  AlertCircle, RefreshCw, Play, X, Plus
} from 'lucide-react'
import { Spinner, EmptyState, SectionHeader, Badge } from '../components.jsx'

// ── API helpers ───────────────────────────────────────────────────────────────

const pdfApi = {
  stats:       ()             => fetch('/api/pdf/stats').then(r => r.json()),
  inbox:       ()             => fetch('/api/pdf/inbox').then(r => r.json()),
  candidates:  (jur)          => fetch(`/api/pdf/candidates${jur ? `?jurisdiction=${jur}` : ''}`).then(r => r.json()),
  downloadAll: (jurisdiction, limit) => fetch(
    `/api/pdf/download-all?limit=${limit}${jurisdiction ? `&jurisdiction=${jurisdiction}` : ''}`,
    { method: 'POST' }
  ).then(r => r.json()),
  downloadIds: (ids)          => fetch('/api/pdf/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ document_ids: ids, limit: ids.length }),
  }).then(r => r.json()),
  ingest:      (payload)      => fetch('/api/pdf/ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(r => r.json()),
  upload:      (formData)     => fetch('/api/pdf/upload', { method: 'POST', body: formData }).then(r => r.json()),
  runLog:      (offset)       => fetch(`/api/run/log?offset=${offset}`).then(r => r.json()),
}

// All known jurisdictions + "Other" for custom
const KNOWN_JURISDICTIONS = [
  'Federal', 'PA', 'VA', 'CA', 'NY', 'TX', 'FL',
  'EU', 'GB', 'CA_FED', 'JP', 'CN', 'AU', 'SG', 'IN', 'BR',
]
const DOC_TYPES = [
  'PDF Document', 'Regulation', 'Directive', 'Act of Parliament',
  'Executive Order', 'Final Rule', 'Proposed Rule', 'Guidance',
  'Guidelines', 'Bill', 'Report', 'White Paper', 'Other',
]
const STATUSES = [
  'Unknown', 'In Force', 'Proposed', 'Enacted', 'Draft',
  'Under Consultation', 'Superseded', 'Withdrawn',
]

// ── Main view ─────────────────────────────────────────────────────────────────

export default function PDFIngest() {
  const [stats,      setStats]      = useState(null)
  const [tab,        setTab]        = useState('auto')  // auto | upload | inbox
  const [loading,    setLoading]    = useState(true)

  const load = async () => {
    setLoading(true)
    try { setStats(await pdfApi.stats()) }
    catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const tabs = [
    { id: 'auto',   label: 'Auto-Download',  icon: Download },
    { id: 'upload', label: 'Upload PDF',      icon: Upload   },
    { id: 'inbox',  label: 'Drop Folder',     icon: Inbox    },
  ]

  return (
    <div style={{ padding: '28px 32px', maxWidth: 960 }}>
      <SectionHeader
        title="PDF Ingestion"
        subtitle="Download PDFs automatically from known sources, or manually supply documents from any jurisdiction"
        action={<button className="btn-secondary btn-sm" onClick={load}><RefreshCw size={13} />Refresh</button>}
      />

      {/* Stats cards */}
      {stats && (
        <div className="flex gap-4" style={{ marginBottom: 28, flexWrap: 'wrap' }}>
          {[
            { label: 'Total PDFs',        value: stats.total_pdfs,        color: 'var(--text)' },
            { label: 'Auto-Downloaded',   value: stats.auto_downloaded,   color: 'var(--accent)' },
            { label: 'Manually Ingested', value: stats.manually_ingested, color: 'var(--green)' },
            { label: 'Inbox Pending',     value: stats.inbox_pending,     color: stats.inbox_pending > 0 ? 'var(--orange)' : 'var(--text-3)' },
            { label: 'Total Pages',       value: stats.total_pages?.toLocaleString(), color: 'var(--text-3)' },
          ].map(c => (
            <div key={c.label} className="card" style={{ flex: '1 1 120px', minWidth: 110 }}>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 6 }}>{c.label}</div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.5rem', fontWeight: 300, color: c.color }}>{c.value ?? 0}</div>
            </div>
          ))}
        </div>
      )}

      {/* Tab bar */}
      <div className="flex gap-0" style={{ borderBottom: '1px solid var(--border)', marginBottom: 24 }}>
        {tabs.map(({ id, label, icon: Icon }) => (
          <button key={id} onClick={() => setTab(id)} style={{
            background: 'transparent', border: 'none', cursor: 'pointer',
            padding: '8px 18px', fontSize: 13, display: 'flex', alignItems: 'center', gap: 6,
            fontWeight: tab === id ? 500 : 400,
            color: tab === id ? 'var(--text)' : 'var(--text-3)',
            borderBottom: tab === id ? '2px solid var(--accent)' : '2px solid transparent',
            marginBottom: -1,
          }}>
            <Icon size={13} />{label}
          </button>
        ))}
      </div>

      {tab === 'auto'   && <AutoDownloadTab onComplete={load} />}
      {tab === 'upload' && <UploadTab       onComplete={load} />}
      {tab === 'inbox'  && <InboxTab        onComplete={load} />}
    </div>
  )
}

// ── Auto-Download tab ─────────────────────────────────────────────────────────

function AutoDownloadTab({ onComplete }) {
  const [candidates, setCandidates]   = useState([])
  const [loading,    setLoading]      = useState(true)
  const [selected,   setSelected]     = useState(new Set())
  const [running,    setRunning]      = useState(false)
  const [logLines,   setLogLines]     = useState([])
  const [logOffset,  setLogOffset]    = useState(0)
  const [jurFilter,  setJurFilter]    = useState('')

  const load = async () => {
    setLoading(true)
    try { setCandidates(await pdfApi.candidates(jurFilter || null)) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [jurFilter])

  // Poll log while running
  useEffect(() => {
    if (!running) return
    const id = setInterval(async () => {
      const res = await pdfApi.runLog(logOffset)
      if (res.lines?.length) {
        setLogLines(p => [...p, ...res.lines])
        setLogOffset(res.total)
      }
      if (!res.running) { setRunning(false); clearInterval(id); onComplete() }
    }, 1500)
    return () => clearInterval(id)
  }, [running, logOffset])

  const toggleAll = () => {
    if (selected.size === candidates.length) setSelected(new Set())
    else setSelected(new Set(candidates.map(c => c.id)))
  }

  const downloadSelected = async () => {
    if (!selected.size) return
    setRunning(true); setLogLines([]); setLogOffset(0)
    await pdfApi.downloadIds([...selected])
  }

  const downloadAll = async () => {
    setRunning(true); setLogLines([]); setLogOffset(0)
    await pdfApi.downloadAll(jurFilter || null, Math.min(candidates.length, 50))
  }

  return (
    <div>
      <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 20, lineHeight: 1.65 }}>
        These documents are already in your database from API fetches. The system has located a PDF
        version of each one — downloading it will extract the full text, which gives the AI agents
        significantly more content to analyse than the abstract alone.
      </div>

      {/* Controls */}
      <div className="flex gap-3 items-center" style={{ marginBottom: 16, flexWrap: 'wrap' }}>
        <select value={jurFilter} onChange={e => setJurFilter(e.target.value)} style={{ width: 150 }}>
          <option value="">All Jurisdictions</option>
          {['Federal','EU','GB','CA','PA'].map(j => <option key={j} value={j}>{j}</option>)}
        </select>
        <button className="btn-secondary btn-sm" onClick={toggleAll}>
          {selected.size === candidates.length ? 'Deselect All' : 'Select All'}
        </button>
        {selected.size > 0 && (
          <button className="btn-primary btn-sm" onClick={downloadSelected} disabled={running}>
            <Download size={13} /> Download Selected ({selected.size})
          </button>
        )}
        {candidates.length > 0 && (
          <button className="btn-secondary btn-sm" onClick={downloadAll} disabled={running}>
            <Play size={13} /> Download All ({candidates.length})
          </button>
        )}
        <button className="btn-ghost btn-sm" onClick={load}><RefreshCw size={12} /></button>
      </div>

      {/* Live log */}
      {(running || logLines.length > 0) && (
        <div style={{ marginBottom: 16, padding: '10px 12px', background: 'var(--bg-3)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', fontSize: 11, fontFamily: 'var(--font-mono)', maxHeight: 130, overflow: 'auto' }}>
          {running && <div style={{ color: 'var(--accent)', marginBottom: 4 }}>⟳ Downloading…</div>}
          {logLines.slice(-10).map((l, i) => <div key={i} style={{ color: 'var(--text-3)' }}>{l}</div>)}
        </div>
      )}

      {/* Candidate list */}
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spinner /></div>
      ) : candidates.length === 0 ? (
        <EmptyState icon={Download} title="No PDF candidates found"
          message="All eligible documents have already been PDF-extracted, or no PDF URLs are available for documents in this jurisdiction." />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {candidates.map(c => (
            <div key={c.id}
              className="card"
              style={{ padding: '10px 14px', borderColor: selected.has(c.id) ? 'var(--accent-dim)' : 'var(--border)', background: selected.has(c.id) ? 'var(--bg-3)' : 'var(--bg-2)', cursor: 'pointer' }}
              onClick={() => setSelected(p => { const n = new Set(p); n.has(c.id) ? n.delete(c.id) : n.add(c.id); return n })}
            >
              <div className="flex items-center gap-3">
                <input type="checkbox" checked={selected.has(c.id)} onChange={() => {}} style={{ width: 'auto', accentColor: 'var(--accent)' }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 500 }} className="truncate">{c.title}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
                    {c.id} · {c.has_text ? `${c.text_length} chars existing` : 'No text yet'}
                  </div>
                </div>
                <Badge level={c.jurisdiction}>{c.jurisdiction}</Badge>
                <a href={c.pdf_url} target="_blank" rel="noopener noreferrer"
                  style={{ color: 'var(--accent)', fontSize: 11, flexShrink: 0 }}
                  onClick={e => e.stopPropagation()}>
                  PDF ↗
                </a>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Upload tab ────────────────────────────────────────────────────────────────

function UploadTab({ onComplete }) {
  const fileRef            = useRef(null)
  const dropRef            = useRef(null)
  const [file,    setFile] = useState(null)
  const [dragging,setDrag] = useState(false)
  const [result,  setResult] = useState(null)
  const [error,   setError]  = useState('')
  const [uploading,setUploading] = useState(false)
  const [form,    setForm]   = useState({
    title: '', jurisdiction: 'Federal', jurisdictionOther: '',
    agency: '', doc_type: 'PDF Document', status: 'Unknown',
    url: '', published_date: '', notes: '',
  })

  const handleDrop = (e) => {
    e.preventDefault(); setDrag(false)
    const f = e.dataTransfer.files[0]
    if (f?.name.toLowerCase().endsWith('.pdf')) {
      setFile(f)
      if (!form.title) setForm(p => ({...p, title: f.name.replace('.pdf', '')}))
    }
  }

  const handleFile = (e) => {
    const f = e.target.files[0]
    if (f) {
      setFile(f)
      if (!form.title) setForm(p => ({...p, title: f.name.replace('.pdf', '')}))
    }
  }

  const submit = async () => {
    if (!file) { setError('Please select a PDF file'); return }
    if (!form.title.trim()) { setError('Title is required'); return }
    setError(''); setUploading(true); setResult(null)
    const fd = new FormData()
    fd.append('file', file)
    const jur = form.jurisdiction === 'Other' ? form.jurisdictionOther : form.jurisdiction
    Object.entries({...form, jurisdiction: jur}).forEach(([k, v]) => {
      if (k !== 'jurisdictionOther') fd.append(k, v)
    })
    try {
      const res = await pdfApi.upload(fd)
      if (res.ok) {
        setResult(res)
        setFile(null)
        setForm({ title: '', jurisdiction: 'Federal', jurisdictionOther: '', agency: '', doc_type: 'PDF Document', status: 'Unknown', url: '', published_date: '', notes: '' })
        onComplete()
      } else {
        setError(res.detail || 'Upload failed')
      }
    } catch (e) { setError(String(e)) }
    finally { setUploading(false) }
  }

  return (
    <div style={{ maxWidth: 680 }}>
      <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 20, lineHeight: 1.65 }}>
        Upload any PDF regulation document. Fill in the metadata below — the document will be
        treated identically to a document fetched via the API and will be available for AI
        summarization, change detection, and synthesis.
      </div>

      {/* Drop zone */}
      <div
        ref={dropRef}
        onDragOver={e => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={handleDrop}
        onClick={() => fileRef.current?.click()}
        style={{
          border: `2px dashed ${dragging ? 'var(--accent)' : file ? 'var(--green)' : 'var(--border)'}`,
          borderRadius: 'var(--radius-lg)', padding: '32px 24px',
          textAlign: 'center', cursor: 'pointer',
          background: dragging ? 'var(--bg-3)' : 'var(--bg-2)',
          transition: 'all 0.2s', marginBottom: 24,
        }}
      >
        <input ref={fileRef} type="file" accept=".pdf" onChange={handleFile} style={{ display: 'none' }} />
        {file ? (
          <div>
            <CheckCircle2 size={28} style={{ color: 'var(--green)', marginBottom: 8 }} />
            <div style={{ fontSize: 14, fontWeight: 500 }}>{file.name}</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>
              {(file.size / 1024).toFixed(0)} KB — click to change
            </div>
          </div>
        ) : (
          <div>
            <Upload size={28} style={{ color: 'var(--text-3)', marginBottom: 8 }} />
            <div style={{ fontSize: 14, color: 'var(--text-2)' }}>Drop a PDF here or click to browse</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>PDF files only</div>
          </div>
        )}
      </div>

      {/* Metadata form */}
      <MetadataForm form={form} onChange={setForm} />

      {error && (
        <div style={{ marginTop: 12, padding: '8px 12px', background: 'rgba(224,82,82,0.1)', border: '1px solid var(--red)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--red)' }}>
          {error}
        </div>
      )}

      {result && (
        <div style={{ marginTop: 12, padding: '10px 14px', background: 'rgba(82,168,120,0.1)', border: '1px solid var(--green)', borderRadius: 'var(--radius)', fontSize: 13, color: 'var(--green)' }}>
          ✓ Ingested: <strong>{result.title}</strong> ({result.word_count?.toLocaleString()} words extracted)
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>ID: {result.document_id}</div>
        </div>
      )}

      <div style={{ marginTop: 20, display: 'flex', gap: 10 }}>
        <button className="btn-primary" onClick={submit} disabled={uploading || !file} style={{ flex: 1, justifyContent: 'center' }}>
          {uploading ? <><Spinner size={14} /> Uploading…</> : <><Upload size={14} /> Upload & Ingest</>}
        </button>
      </div>
    </div>
  )
}

// ── Drop Folder (Inbox) tab ───────────────────────────────────────────────────

function InboxTab({ onComplete }) {
  const [files,    setFiles]    = useState([])
  const [loading,  setLoading]  = useState(true)
  const [selected, setSelected] = useState(null)
  const [form,     setForm]     = useState({
    title: '', jurisdiction: 'Federal', jurisdictionOther: '',
    agency: '', doc_type: 'PDF Document', status: 'Unknown',
    url: '', published_date: '', notes: '',
  })
  const [ingesting, setIngesting] = useState(false)
  const [result,    setResult]    = useState(null)
  const [error,     setError]     = useState('')

  const load = async () => {
    setLoading(true)
    try { setFiles(await pdfApi.inbox()) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const selectFile = (f) => {
    setSelected(f)
    setResult(null); setError('')
    setForm(p => ({ ...p, title: f.filename.replace('.pdf', '') }))
  }

  const ingest = async () => {
    if (!selected) return
    setIngesting(true); setError(''); setResult(null)
    const jur = form.jurisdiction === 'Other' ? form.jurisdictionOther : form.jurisdiction
    try {
      const res = await pdfApi.ingest({ filename: selected.filename, ...form, jurisdiction: jur })
      if (res.ok) {
        setResult(res); setSelected(null)
        await load(); onComplete()
      } else {
        setError(res.detail || 'Ingest failed')
      }
    } catch (e) { setError(String(e)) }
    finally { setIngesting(false) }
  }

  return (
    <div>
      <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 16, lineHeight: 1.65 }}>
        Place PDF files in <code style={{ background: 'var(--bg-3)', padding: '1px 5px', borderRadius: 3, fontSize: 12 }}>output/pdf_inbox/</code> on your machine.
        They will appear here for tagging and ingestion. This is the recommended workflow for
        bulk imports or documents from jurisdictions not covered by existing agents.
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spinner /></div>
      ) : files.length === 0 ? (
        <EmptyState icon={Inbox} title="Drop folder is empty"
          message={`Place PDF files in output/pdf_inbox/ to ingest them here.`} />
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, alignItems: 'start' }}>
          {/* File list */}
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 10 }}>
              {files.length} file{files.length !== 1 ? 's' : ''} waiting
            </div>
            {files.map(f => (
              <div key={f.filename}
                className="card card-hover"
                style={{ padding: '10px 14px', marginBottom: 6, borderColor: selected?.filename === f.filename ? 'var(--accent-dim)' : 'var(--border)', background: selected?.filename === f.filename ? 'var(--bg-3)' : 'var(--bg-2)' }}
                onClick={() => selectFile(f)}
              >
                <div className="flex items-center gap-2">
                  <FileText size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500 }} className="truncate">{f.filename}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>
                      {f.size_kb} KB · {f.modified.slice(0, 10)}
                    </div>
                  </div>
                </div>
              </div>
            ))}
            <button className="btn-ghost btn-sm" onClick={load} style={{ marginTop: 6 }}>
              <RefreshCw size={12} /> Refresh
            </button>
          </div>

          {/* Tag form */}
          {selected && (
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', marginBottom: 10 }}>
                Tag: {selected.filename}
              </div>
              <MetadataForm form={form} onChange={setForm} />

              {error && (
                <div style={{ marginTop: 10, padding: '8px 12px', background: 'rgba(224,82,82,0.1)', border: '1px solid var(--red)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--red)' }}>
                  {error}
                </div>
              )}
              {result && (
                <div style={{ marginTop: 10, padding: '8px 12px', background: 'rgba(82,168,120,0.1)', border: '1px solid var(--green)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--green)' }}>
                  ✓ {result.title} ingested ({result.word_count?.toLocaleString()} words)
                </div>
              )}

              <button className="btn-primary" onClick={ingest} disabled={ingesting} style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}>
                {ingesting ? <><Spinner size={13} /> Ingesting…</> : <><Plus size={13} /> Ingest This File</>}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Shared metadata form ──────────────────────────────────────────────────────

function MetadataForm({ form, onChange }) {
  const set = (k, v) => onChange(p => ({...p, [k]: v}))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div>
        <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Title <span style={{ color: 'var(--red)' }}>*</span></label>
        <input value={form.title} onChange={e => set('title', e.target.value)} placeholder="Document title" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        <div>
          <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Jurisdiction</label>
          <select value={form.jurisdiction} onChange={e => set('jurisdiction', e.target.value)}>
            {KNOWN_JURISDICTIONS.map(j => <option key={j} value={j}>{j}</option>)}
            <option value="Other">Other (specify below)</option>
          </select>
          {form.jurisdiction === 'Other' && (
            <input
              style={{ marginTop: 6 }}
              value={form.jurisdictionOther}
              onChange={e => set('jurisdictionOther', e.target.value)}
              placeholder="e.g. Singapore, Brazil, India…"
            />
          )}
        </div>

        <div>
          <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Document Type</label>
          <select value={form.doc_type} onChange={e => set('doc_type', e.target.value)}>
            {DOC_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>

        <div>
          <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Agency / Author</label>
          <input value={form.agency} onChange={e => set('agency', e.target.value)} placeholder="e.g. Ministry of Digital Affairs" />
        </div>

        <div>
          <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Status</label>
          <select value={form.status} onChange={e => set('status', e.target.value)}>
            {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div>
          <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Published Date</label>
          <input type="date" value={form.published_date} onChange={e => set('published_date', e.target.value)} />
        </div>

        <div>
          <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Source URL (optional)</label>
          <input value={form.url} onChange={e => set('url', e.target.value)} placeholder="https://…" />
        </div>
      </div>

      <div>
        <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 4 }}>Notes (optional)</label>
        <textarea
          value={form.notes}
          onChange={e => set('notes', e.target.value)}
          placeholder="Internal notes — e.g. 'Obtained from ministry website, covers AI Act implementation in Singapore'"
          style={{ height: 60, resize: 'vertical' }}
        />
      </div>
    </div>
  )
}
