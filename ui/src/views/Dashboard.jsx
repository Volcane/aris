import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { AlertTriangle, TrendingUp, Clock, CheckSquare } from 'lucide-react'
import { api } from '../api.js'
import { Badge, UrgencyDot, StatCard, Spinner, EmptyState } from '../components.jsx'

const URGENCY_COLORS = {
  Critical: 'var(--red)',
  High:     'var(--orange)',
  Medium:   'var(--yellow)',
  Low:      'var(--green)',
}

export default function Dashboard({ status }) {
  const [docs,    setDocs]    = useState([])
  const [changes, setChanges] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    Promise.all([
      api.documents({ days: 90, page_size: 8 }),
      api.changes({ days: 14 }),
    ]).then(([d, c]) => {
      setDocs(d.items || [])
      setChanges(c.slice(0, 6))
    }).finally(() => setLoading(false))
  }, [])

  const stats = status?.stats || {}

  // Build urgency breakdown for chart
  const urgencyCounts = docs.reduce((acc, d) => {
    const u = d.urgency || 'Low'
    acc[u] = (acc[u] || 0) + 1
    return acc
  }, {})
  const chartData = ['Critical', 'High', 'Medium', 'Low'].map(u => ({
    name: u, count: urgencyCounts[u] || 0, fill: URGENCY_COLORS[u],
  }))

  // Jurisdiction breakdown
  const jurCounts = docs.reduce((acc, d) => {
    const j = d.jurisdiction || 'Unknown'
    acc[j] = (acc[j] || 0) + 1
    return acc
  }, {})

  if (loading) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
      <Spinner size={24} />
    </div>
  )

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1200 }}>
      {/* Header */}
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontWeight: 300, fontSize: '1.8rem' }}>Intelligence Overview</h1>
        <p style={{ color: 'var(--text-3)', marginTop: 4, fontSize: 13 }}>
          {new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
        </p>
      </div>

      {/* Stat row */}
      <div className="flex gap-4" style={{ marginBottom: 28, flexWrap: 'wrap' }}>
        <StatCard label="Documents" value={stats.total_documents} sub="total tracked" />
        <StatCard label="Summarised" value={stats.total_summaries} sub={`${stats.pending_summaries || 0} pending`} />
        <StatCard label="Changes" value={stats.total_diffs} sub={`${stats.unreviewed_diffs || 0} unreviewed`} color="var(--accent)" />
        <StatCard label="Critical" value={stats.critical_diffs} sub="high-priority diffs" color="var(--red)" />
        <StatCard label="High" value={stats.high_severity_diffs} sub="severity diffs" color="var(--orange)" />
      </div>

      {/* Main grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 28 }}>
        {/* Urgency chart */}
        <div className="card">
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 16 }}>Urgency Distribution (last 14 days)</div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={chartData} barSize={32}>
              <XAxis dataKey="name" tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'var(--text-3)', fontSize: 11 }} axisLine={false} tickLine={false} width={24} />
              <Tooltip
                contentStyle={{ background: 'var(--bg-3)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
                cursor={{ fill: 'rgba(255,255,255,0.04)' }}
              />
              <Bar dataKey="count" radius={[3,3,0,0]}>
                {chartData.map((entry, i) => <Cell key={i} fill={entry.fill} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Jurisdiction breakdown */}
        <div className="card">
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 16 }}>By Jurisdiction (last 14 days)</div>
          {Object.entries(jurCounts).length === 0 ? (
            <div style={{ color: 'var(--text-3)', fontSize: 13, paddingTop: 12 }}>No data yet — run agents to populate</div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {Object.entries(jurCounts).sort((a,b) => b[1]-a[1]).map(([jur, count]) => (
                <div key={jur} className="flex items-center gap-3">
                  <span style={{ width: 48, fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text-2)' }}>{jur}</span>
                  <div style={{
                    flex: 1, height: 6, background: 'var(--bg-4)', borderRadius: 3, overflow: 'hidden',
                  }}>
                    <div style={{
                      height: '100%',
                      width: `${Math.round((count / Math.max(...Object.values(jurCounts))) * 100)}%`,
                      background: 'var(--accent)',
                      borderRadius: 3,
                    }} />
                  </div>
                  <span style={{ fontSize: 12, color: 'var(--text-3)', width: 24, textAlign: 'right' }}>{count}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent changes */}
      {changes.length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <div className="flex items-center justify-between" style={{ marginBottom: 12 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Recent Changes
            </div>
            <button className="btn-ghost btn-sm" onClick={() => navigate('/changes')}>View all →</button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {changes.map(c => (
              <div key={c.id} className="card card-hover" style={{ padding: '12px 16px' }}
                onClick={() => navigate('/changes')}>
                <div className="flex items-center gap-3">
                  <UrgencyDot level={c.severity} />
                  <span style={{ flex: 1, fontSize: 13, color: 'var(--text-2)' }} className="truncate">
                    {c.change_summary || 'Change detected'}
                  </span>
                  <Badge level={c.severity}>{c.severity}</Badge>
                  {!c.reviewed && <span style={{ fontSize: 11, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>NEW</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent documents */}
      <div>
        <div className="flex items-center justify-between" style={{ marginBottom: 12 }}>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Latest Documents
          </div>
          <button className="btn-ghost btn-sm" onClick={() => navigate('/documents')}>View all →</button>
        </div>
        {docs.length === 0 ? (
          <EmptyState title="No documents yet" message='Run agents to start populating the database.' />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {docs.slice(0, 6).map(doc => (
              <div key={doc.id} className="card card-hover" style={{ padding: '10px 16px' }}
                onClick={() => navigate('/documents')}>
                <div className="flex items-center gap-3">
                  <UrgencyDot level={doc.urgency} />
                  <span style={{ flex: 1, fontSize: 13 }} className="truncate">{doc.title}</span>
                  <Badge level={doc.jurisdiction}>{doc.jurisdiction}</Badge>
                  <Badge level={doc.urgency} />
                  <span style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', flexShrink: 0 }}>
                    {doc.published_date?.slice(0,10)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
