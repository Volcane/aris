import { X, Loader2, AlertTriangle, FileText } from 'lucide-react'

export function Badge({ level, children }) {
  const cls = {
    Critical: 'badge-critical',
    High:     'badge-high',
    Medium:   'badge-medium',
    Low:      'badge-low',
    Federal:  'badge-blue',
    EU:       'badge-blue',
    GB:       'badge-neutral',
    CA:       'badge-neutral',
    PA:       'badge-neutral',
  }[level] || 'badge-neutral'
  return <span className={`badge ${cls}`}>{children || level}</span>
}

export function UrgencyDot({ level }) {
  const color = {
    Critical: 'var(--red)',
    High:     'var(--orange)',
    Medium:   'var(--yellow)',
    Low:      'var(--green)',
  }[level] || 'var(--text-3)'
  return (
    <span style={{
      display: 'inline-block',
      width: 8, height: 8,
      borderRadius: '50%',
      background: color,
      flexShrink: 0,
    }} />
  )
}

export function Spinner({ size = 16 }) {
  return <Loader2 size={size} className="spin" style={{ color: 'var(--accent)' }} />
}

export function EmptyState({ icon: Icon = FileText, title, message }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      gap: 12, padding: '60px 20px', color: 'var(--text-3)',
    }}>
      <Icon size={36} strokeWidth={1} />
      <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.1rem', color: 'var(--text-2)' }}>{title}</div>
      {message && <div style={{ fontSize: 13, maxWidth: 320, textAlign: 'center' }}>{message}</div>}
    </div>
  )
}

export function Modal({ title, onClose, children, width = 640 }) {
  return (
    <div
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.7)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000, padding: 24,
      }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div style={{
        background: 'var(--bg-2)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        width: '100%', maxWidth: width,
        maxHeight: '85vh', overflow: 'hidden',
        display: 'flex', flexDirection: 'column',
        boxShadow: 'var(--shadow-lg)',
      }}>
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 20px',
          borderBottom: '1px solid var(--border)',
          flexShrink: 0,
        }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 300 }}>{title}</h3>
          <button className="btn-icon" onClick={onClose}><X size={16} /></button>
        </div>
        <div style={{ overflow: 'auto', padding: '20px', flex: 1 }}>
          {children}
        </div>
      </div>
    </div>
  )
}

export function Pagination({ page, pages, onChange }) {
  if (pages <= 1) return null
  return (
    <div className="flex items-center gap-2 justify-between" style={{ marginTop: 16 }}>
      <span style={{ fontSize: 12, color: 'var(--text-3)' }}>Page {page} of {pages}</span>
      <div className="flex gap-2">
        <button className="btn-secondary btn-sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>← Prev</button>
        <button className="btn-secondary btn-sm" disabled={page >= pages} onClick={() => onChange(page + 1)}>Next →</button>
      </div>
    </div>
  )
}

export function SectionHeader({ title, subtitle, action }) {
  return (
    <div className="flex items-center justify-between" style={{ marginBottom: 20 }}>
      <div>
        <h2 style={{ fontWeight: 300 }}>{title}</h2>
        {subtitle && <p style={{ color: 'var(--text-3)', fontSize: 13, marginTop: 2 }}>{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}

export function StatCard({ label, value, sub, color = 'var(--text)' }) {
  return (
    <div className="card" style={{ flex: 1, minWidth: 120 }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.8rem', fontWeight: 300, color, lineHeight: 1 }}>{value ?? '—'}</div>
      {sub && <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

export function KeyValue({ label, value }) {
  if (!value) return null
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '130px 1fr', gap: 8, padding: '6px 0', borderBottom: '1px solid var(--border)' }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', paddingTop: 1 }}>{label}</span>
      <span style={{ fontSize: 13 }}>{value}</span>
    </div>
  )
}

export function RequirementList({ items = [], color = 'var(--red)', label }) {
  if (!items.length) return null
  const list = items.map(i => typeof i === 'string' ? i : i.description || JSON.stringify(i))
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.06em', color, marginBottom: 6 }}>{label}</div>
      <ul style={{ paddingLeft: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {list.map((item, i) => (
          <li key={i} style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5 }}>{item}</li>
        ))}
      </ul>
    </div>
  )
}
