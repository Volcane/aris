import { useState, useEffect } from 'react'
import { Bell, Plus, Trash2, Eye, ChevronDown, ChevronUp } from 'lucide-react'
import { api } from '../api.js'
import { Spinner, EmptyState, Modal, SectionHeader, Badge, UrgencyDot } from '../components.jsx'

const JURISDICTIONS = ['Federal', 'PA', 'EU', 'GB', 'CA', 'JP', 'CN', 'AU']

export default function Watchlist() {
  const [items,     setItems]     = useState([])
  const [loading,   setLoading]   = useState(true)
  const [showAdd,   setShowAdd]   = useState(false)
  const [expanded,  setExpanded]  = useState({})
  const [matches,   setMatches]   = useState({})

  const load = async () => {
    setLoading(true)
    try { setItems(await api.watchlist()) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const remove = async (name) => {
    if (!confirm(`Remove watch "${name}"?`)) return
    await api.deleteWatch(name)
    load()
  }

  const toggleExpand = async (name) => {
    setExpanded(prev => ({ ...prev, [name]: !prev[name] }))
    if (!expanded[name] && !matches[name]) {
      const res = await api.watchMatches(name)
      setMatches(prev => ({ ...prev, [name]: res.matches }))
    }
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 860 }}>
      <SectionHeader
        title="Watchlist"
        subtitle="Saved searches that alert you when new matching documents are found"
        action={
          <button className="btn-primary btn-sm" onClick={() => setShowAdd(true)}>
            <Plus size={13} /> Add Watch
          </button>
        }
      />

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}><Spinner size={24} /></div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="No watchlist items"
          message="Create a watchlist entry to be alerted when documents matching your keywords are found."
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {items.map(item => (
            <WatchCard
              key={item.name}
              item={item}
              expanded={!!expanded[item.name]}
              matchDocs={matches[item.name]}
              onToggle={() => toggleExpand(item.name)}
              onRemove={() => remove(item.name)}
            />
          ))}
        </div>
      )}

      {showAdd && (
        <AddWatchModal
          onClose={() => setShowAdd(false)}
          onSaved={() => { setShowAdd(false); load() }}
        />
      )}
    </div>
  )
}

function WatchCard({ item, expanded, matchDocs, onToggle, onRemove }) {
  const count = item.match_count || 0
  return (
    <div style={{
      background: 'var(--bg-2)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden',
    }}>
      <div className="flex items-center gap-3" style={{ padding: '14px 18px', cursor: 'pointer' }} onClick={onToggle}>
        <Bell size={15} style={{ color: 'var(--accent)', flexShrink: 0 }} />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 500, fontSize: 14 }}>{item.name}</div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 3, fontFamily: 'var(--font-mono)' }}>
            Keywords: {item.keywords?.join(', ')}
            {item.jurisdictions?.length > 0 && ` · Jurisdictions: ${item.jurisdictions.join(', ')}`}
          </div>
        </div>
        <div style={{
          background: count > 0 ? 'var(--accent)' : 'var(--bg-4)',
          color: count > 0 ? '#0d0f0f' : 'var(--text-3)',
          fontFamily: 'var(--font-mono)',
          fontSize: 12, fontWeight: 600,
          padding: '3px 10px', borderRadius: 10,
        }}>
          {count} match{count !== 1 ? 'es' : ''}
        </div>
        <button className="btn-icon" onClick={e => { e.stopPropagation(); onRemove() }}>
          <Trash2 size={13} />
        </button>
        {expanded ? <ChevronUp size={14} style={{ color: 'var(--text-3)' }} /> : <ChevronDown size={14} style={{ color: 'var(--text-3)' }} />}
      </div>

      {expanded && (
        <div style={{ borderTop: '1px solid var(--border)', padding: '14px 18px' }}>
          {!matchDocs ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 20 }}><Spinner /></div>
          ) : matchDocs.length === 0 ? (
            <div style={{ fontSize: 13, color: 'var(--text-3)', fontStyle: 'italic' }}>No matching documents found in database.</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {matchDocs.slice(0, 10).map(doc => (
                <div key={doc.id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
                  <UrgencyDot level={doc.urgency} />
                  <span style={{ flex: 1, fontSize: 13, color: 'var(--text-2)' }} className="truncate">{doc.title}</span>
                  <Badge level={doc.jurisdiction}>{doc.jurisdiction}</Badge>
                  <span style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                    {doc.published_date?.slice(0,10)}
                  </span>
                </div>
              ))}
              {matchDocs.length > 10 && (
                <div style={{ fontSize: 12, color: 'var(--text-3)', paddingTop: 4 }}>
                  + {matchDocs.length - 10} more matches
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function AddWatchModal({ onClose, onSaved }) {
  const [name,         setName]         = useState('')
  const [keywords,     setKeywords]     = useState('')
  const [jurisdictions,setJurisdictions]= useState([])
  const [saving,       setSaving]       = useState(false)
  const [error,        setError]        = useState('')

  const save = async () => {
    if (!name.trim() || !keywords.trim()) { setError('Name and keywords are required.'); return }
    setSaving(true)
    try {
      await api.addWatch({
        name:          name.trim(),
        keywords:      keywords.split(',').map(k => k.trim()).filter(Boolean),
        jurisdictions: jurisdictions,
        notify_on:     ['new_doc', 'change'],
      })
      onSaved()
    } catch (e) { setError(e.message) }
    finally { setSaving(false) }
  }

  const toggleJur = (j) =>
    setJurisdictions(prev => prev.includes(j) ? prev.filter(x => x !== j) : [...prev, j])

  return (
    <Modal title="Add Watchlist Entry" onClose={onClose} width={500}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 6 }}>Name</label>
          <input placeholder="e.g. EU AI Act Updates" value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div>
          <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 6 }}>Keywords (comma-separated)</label>
          <input placeholder="e.g. artificial intelligence, high-risk AI, GPAI" value={keywords} onChange={e => setKeywords(e.target.value)} />
        </div>
        <div>
          <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 8 }}>Jurisdictions (optional — leave empty for all)</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {JURISDICTIONS.map(j => (
              <button
                key={j}
                className={jurisdictions.includes(j) ? 'btn-primary btn-sm' : 'btn-secondary btn-sm'}
                onClick={() => toggleJur(j)}
              >{j}</button>
            ))}
          </div>
        </div>
        {error && <div style={{ fontSize: 12, color: 'var(--red)' }}>{error}</div>}
        <button className="btn-primary" onClick={save} disabled={saving}>
          {saving ? <><Spinner size={13} /> Saving…</> : <><Bell size={13} /> Add to Watchlist</>}
        </button>
      </div>
    </Modal>
  )
}
