import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { useState, useEffect } from 'react'
import {
  LayoutDashboard, FileText, GitCompare, Play,
  Eye, Network, Settings, Loader2, AlertCircle,
  CheckSquare, Bell
} from 'lucide-react'
import { api } from './api.js'
import Dashboard   from './views/Dashboard.jsx'
import Documents   from './views/Documents.jsx'
import Changes     from './views/Changes.jsx'
import RunAgents   from './views/RunAgents.jsx'
import Watchlist   from './views/Watchlist.jsx'
import Graph       from './views/Graph.jsx'
import SettingsView from './views/Settings.jsx'

const NAV = [
  { to: '/',          icon: LayoutDashboard, label: 'Dashboard'  },
  { to: '/documents', icon: FileText,        label: 'Documents'  },
  { to: '/changes',   icon: GitCompare,      label: 'Changes'    },
  { to: '/run',       icon: Play,            label: 'Run Agents' },
  { to: '/watchlist', icon: Bell,            label: 'Watchlist'  },
  { to: '/graph',     icon: Network,         label: 'Graph'      },
  { to: '/settings',  icon: Settings,        label: 'Settings'   },
]

export default function App() {
  const [status,  setStatus]  = useState(null)
  const [jobRunning, setJobRunning] = useState(false)
  const location = useLocation()

  useEffect(() => {
    const load = async () => {
      try {
        const s = await api.status()
        setStatus(s)
        setJobRunning(s.job?.running || false)
      } catch {}
    }
    load()
    const id = setInterval(load, 8000)
    return () => clearInterval(id)
  }, [])

  const stats = status?.stats || {}

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {/* ── Sidebar ── */}
      <aside style={{
        width: 220,
        background: 'var(--bg-2)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        flexShrink: 0,
      }}>
        {/* Wordmark */}
        <div style={{ padding: '24px 20px 16px' }}>
          <div style={{
            fontFamily: 'var(--font-display)',
            fontSize: '1.5rem',
            fontWeight: 300,
            color: 'var(--accent)',
            letterSpacing: '-0.01em',
          }}>ARIS</div>
          <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
            AI Reg Intelligence
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: '8px 8px' }}>
          {NAV.map(({ to, icon: Icon, label }) => (
            <NavLink key={to} to={to} end={to === '/'}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '8px 12px',
                borderRadius: 'var(--radius)',
                color: isActive ? 'var(--text)' : 'var(--text-3)',
                background: isActive ? 'var(--bg-4)' : 'transparent',
                textDecoration: 'none',
                fontSize: 13,
                fontWeight: isActive ? 500 : 400,
                marginBottom: 2,
                transition: 'all 0.15s',
                borderLeft: isActive ? '2px solid var(--accent)' : '2px solid transparent',
              })}
            >
              <Icon size={15} />
              {label}
              {label === 'Changes' && stats.unreviewed_diffs > 0 && (
                <span style={{
                  marginLeft: 'auto',
                  background: 'var(--red)',
                  color: '#fff',
                  fontSize: 10,
                  borderRadius: 10,
                  padding: '1px 6px',
                  fontFamily: 'var(--font-mono)',
                }}>{stats.unreviewed_diffs}</span>
              )}
            </NavLink>
          ))}
        </nav>

        {/* Bottom status */}
        <div style={{
          padding: '12px 16px',
          borderTop: '1px solid var(--border)',
          fontSize: 12,
          color: 'var(--text-3)',
        }}>
          {jobRunning ? (
            <div className="flex items-center gap-2" style={{ color: 'var(--accent)' }}>
              <Loader2 size={13} className="spin" />
              <span>Agent running…</span>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <div style={{ width: 7, height: 7, borderRadius: '50%', background: status ? 'var(--green)' : 'var(--red-dim)' }} />
              <span>{stats.total_documents ?? '—'} docs · {stats.total_summaries ?? '—'} summarised</span>
            </div>
          )}
          {status?.job?.last_run && (
            <div style={{ marginTop: 4, fontSize: 11 }}>
              Last run: {new Date(status.job.last_run).toLocaleTimeString()}
            </div>
          )}
        </div>
      </aside>

      {/* ── Main content ── */}
      <main style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
        <Routes>
          <Route path="/"          element={<Dashboard  status={status} />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/changes"   element={<Changes />} />
          <Route path="/run"       element={<RunAgents onJobStart={() => setJobRunning(true)} />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/graph"     element={<Graph />} />
          <Route path="/settings"  element={<SettingsView status={status} />} />
        </Routes>
      </main>
    </div>
  )
}
