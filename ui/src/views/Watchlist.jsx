import { useState, useEffect } from 'react'
import { Bell, Plus, Trash2, Eye, ChevronDown, ChevronUp, Filter } from 'lucide-react'
import { api } from '../api.js'
import { Spinner, EmptyState, Modal, SectionHeader, Badge, UrgencyDot, DomainFilter } from '../components.jsx'

const DOMAIN_KEY = 'aris_domain_watchlist'
const JURISDICTIONS = ['Federal', 'PA', 'CA', 'CO', 'IL', 'EU', 'GB', 'CA_INTL', 'JP', 'AU']

export default function Watchlist() {
  const [items,     setItems]     = useState([])
  const [loading,   setLoading]   = useState(true)
  const [showAdd,   setShowAdd]   = useState(false)
  const [expanded,  setExpanded]  = useState({})
  const [matches,   setMatches]   = useState({})
  const [domain,    setDomain]    = useState(() => {
    try { return localStorage.getItem(DOMAIN_KEY) || 'both' } catch { return 'both' }
  })

  const load = async () => {
    setLoading(true)
    try { setItems(await api.watchlist()) }
    finally { setLoading(false) }
  }

  useEffect(() => { load() }, [])

  const handleDomain = (d) => {
    setDomain(d)
    try { localStorage.setItem(DOMAIN_KEY, d) } catch {}
    // Clear cached matches so they re-fetch with new domain
    setMatches({})
    setExpanded({})
  }

  const remove = async (name) => {
    if (!confirm(`Remove watch "${name}"?`)) return
    await api.deleteWatch(name)
    load()
  }

  const toggleExpand = async (name) => {
    const nowOpen = !expanded[name]
    setExpanded(prev => ({ ...prev, [name]: nowOpen }))
    if (nowOpen && !matches[name]) {
      try {
        const domainParam = domain !== 'both' ? `&domain=${domain}` : ''
        const res = await fetch(`/api/watchlist/${encodeURIComponent(name)}/matches?days=90${domainParam}`)
        const data = await res.json()
        setMatches(prev => ({ ...prev, [name]: data.matches || [] }))
      } catch {
        setMatches(prev => ({ ...prev, [name]: [] }))
      }
    }
  }

  return (
    <div style={{ padding: '28px 32px', maxWidth: 860 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
        <SectionHeader title="Watchlist" subtitle="Keyword alerts across all documents" />
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <DomainFilter value={domain} onChange={handleDomain} />
          <button className="btn-primary btn-sm" onClick={() => setShowAdd(true)}>
            <Plus size={13} /> Add Watch
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}><Spinner size={22} /></div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={Bell}
          title="No watches configured"
          message="Add keyword watches to get alerted when matching documents appear."
          action={{ label: 'Add Watch', onClick: () => setShowAdd(true) }}
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {items.map(item => (
            <WatchCard
              key={item.name}
              item={item}
              expanded={!!expanded[item.name]}
              matchList={matches[item.name]}
              onToggle={() => toggleExpand(item.name)}
              onDelete={() => remove(item.name)}
              domain={domain}
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

// ── Watch card ────────────────────────────────────────────────────────────────

function WatchCard({ item, expanded, matchList, onToggle, onDelete, domain }) {
  const isLoading = expanded && matchList === undefined

  return (
    <div style={{
      background: 'var(--bg-2)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)', overflow: 'hidden',
    }}>
      {/* Header row */}
      <div
        onClick={onToggle}
        style={{ padding: '13px 16px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 10 }}
      >
        <Bell size={13} style={{ color: 'var(--accent)', flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text)', marginBottom: 3 }}>
            {item.name}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {(item.keywords || []).map(kw => (
              <span key={kw} style={{
                background: 'var(--accent-dim)', color: 'var(--accent)',
                padding: '1px 6px', borderRadius: 3, fontFamily: 'var(--font-mono)',
              }}>{kw}</span>
            ))}
            {(item.jurisdictions || []).length > 0 && (
              <span style={{ color: 'var(--text-3)' }}>
                · {item.jurisdictions.join(', ')}
              </span>
            )}
          </div>
        </div>
        {isLoading
          ? <Spinner size={13} />
          : matchList !== undefined
            ? <span style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                {matchList.length} match{matchList.length !== 1 ? 'es' : ''}
                {domain !== 'both' && <span style={{ color: 'var(--accent)', marginLeft: 4 }}>({domain})</span>}
              </span>
            : null
        }
        <button
          className="btn-icon btn-danger"
          onClick={e => { e.stopPropagation(); onDelete() }}
          style={{ flexShrink: 0 }}
        >
          <Trash2 size={13} />
        </button>
        {expanded ? <ChevronUp size={13} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
                  : <ChevronDown size={13} style={{ color: 'var(--text-3)', flexShrink: 0 }} />}
      </div>

      {/* Matches */}
      {expanded && (
        <div style={{ borderTop: '1px solid var(--border)' }}>
          {isLoading ? (
            <div style={{ padding: 20, display: 'flex', justifyContent: 'center' }}><Spinner size={18} /></div>
          ) : !matchList || matchList.length === 0 ? (
            <div style={{ padding: '14px 16px', fontSize: 13, color: 'var(--text-3)', fontStyle: 'italic' }}>
              No matching documents in the last 90 days
              {domain !== 'both' && ` for domain: ${domain}`}.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {matchList.slice(0, 20).map((doc, i) => (
                <div key={doc.id || i} style={{
                  padding: '10px 16px',
                  borderBottom: i < matchList.length - 1 ? '1px solid var(--border)' : 'none',
                  display: 'flex', alignItems: 'flex-start', gap: 10,
                }}>
                  <UrgencyDot urgency={doc.urgency} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, color: 'var(--text)', marginBottom: 2 }} className="truncate">
                      {doc.title || doc.id}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                      <span>{doc.jurisdiction}</span>
                      {doc.domain && doc.domain !== 'ai' && (
                        <span style={{ color: '#7c9ef7' }}>{doc.domain}</span>
                      )}
                      {doc.published_date && (
                        <span>{new Date(doc.published_date).toLocaleDateString()}</span>
                      )}
                    </div>
                  </div>
                  {doc.url && (
                    <a href={doc.url} target="_blank" rel="noopener noreferrer"
                      style={{ fontSize: 11, color: 'var(--accent)', flexShrink: 0 }}>
                      <Eye size={13} />
                    </a>
                  )}
                </div>
              ))}
              {matchList.length > 20 && (
                <div style={{ padding: '10px 16px', fontSize: 11, color: 'var(--text-3)', textAlign: 'center' }}>
                  +{matchList.length - 20} more — narrow your search or add jurisdiction filters
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Add watch modal ───────────────────────────────────────────────────────────

function AddWatchModal({ onClose, onSaved }) {
  const [name,          setName]          = useState('')
  const [keywords,      setKeywords]      = useState('')
  const [jurisdictions, setJurisdictions] = useState([])
  const [saving,        setSaving]        = useState(false)
  const [error,         setError]         = useState(null)

  const toggleJur = (j) =>
    setJurisdictions(prev => prev.includes(j) ? prev.filter(x => x !== j) : [...prev, j])

  const save = async () => {
    if (!name.trim() || !keywords.trim()) { setError('Name and keywords are required'); return }
    setSaving(true)
    setError(null)
    try {
      await api.addWatch({
        name:          name.trim(),
        keywords:      keywords.split(',').map(k => k.trim()).filter(Boolean),
        jurisdictions,
      })
      onSaved()
    } catch (e) {
      setError(e.message || 'Save failed')
      setSaving(false)
    }
  }

  return (
    <Modal title="Add Watch" onClose={onClose}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div>
          <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 5 }}>
            Watch name
          </label>
          <input
            placeholder="e.g. Consent Requirements"
            value={name}
            onChange={e => setName(e.target.value)}
            autoFocus
          />
        </div>
        <div>
          <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 5 }}>
            Keywords (comma-separated)
          </label>
          <input
            placeholder="e.g. consent, opt-out, legitimate interest"
            value={keywords}
            onChange={e => setKeywords(e.target.value)}
          />
          <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 4 }}>
            Matched against document titles and summaries
          </div>
        </div>
        <div>
          <label style={{ fontSize: 12, color: 'var(--text-3)', display: 'block', marginBottom: 8 }}>
            Jurisdictions (optional — leave empty to match all)
          </label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {JURISDICTIONS.map(j => (
              <button
                key={j}
                onClick={() => toggleJur(j)}
                style={{
                  fontSize: 11, padding: '3px 8px', borderRadius: 4, cursor: 'pointer',
                  background: jurisdictions.includes(j) ? 'var(--accent-dim)' : 'var(--bg-3)',
                  border: `1px solid ${jurisdictions.includes(j) ? 'var(--accent)' : 'var(--border)'}`,
                  color: jurisdictions.includes(j) ? 'var(--accent)' : 'var(--text-3)',
                }}
              >{j}</button>
            ))}
          </div>
        </div>
        {error && <div style={{ fontSize: 12, color: 'var(--red)' }}>{error}</div>}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 4 }}>
          <button className="btn-secondary" onClick={onClose}>Cancel</button>
          <button className="btn-primary" onClick={save} disabled={saving}>
            {saving ? <><Spinner size={12} /> Saving…</> : 'Save Watch'}
          </button>
        </div>
      </div>
    </Modal>
  )
}
