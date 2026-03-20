import { Routes, Route, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import {
  LayoutDashboard, FileText, GitCompare, Play,
  Eye, Network, Settings, Loader2, AlertCircle,
  CheckSquare, Bell, Brain, Layers, FileInput,
  BarChart3, BookOpen, TrendingUp, CalendarDays,
  Sparkles, Map, Clock, ScrollText, Shield,
} from 'lucide-react'
import { api } from './api.js'
import Dashboard    from './views/Dashboard.jsx'
import Documents    from './views/Documents.jsx'
import Changes      from './views/Changes.jsx'
import RunAgents    from './views/RunAgents.jsx'
import Watchlist    from './views/Watchlist.jsx'
import Graph        from './views/Graph.jsx'
import Learning     from './views/Learning.jsx'
import Synthesis    from './views/Synthesis.jsx'
import PDFIngest    from './views/PDFIngest.jsx'
import GapAnalysis  from './views/GapAnalysis.jsx'
import Baselines    from './views/Baselines.jsx'
import Trends       from './views/Trends.jsx'
import Horizon      from './views/Horizon.jsx'
import AskAris      from './views/AskAris.jsx'
import ConceptMap   from './views/ConceptMap.jsx'
import Timeline     from './views/Timeline.jsx'
import Brief        from './views/Brief.jsx'
import Enforcement  from './views/Enforcement.jsx'
import SettingsView from './views/Settings.jsx'

// Nav grouped by function — Settings is pinned to the sidebar footer separately
const NAV_GROUPS = [
  {
    label: 'Intelligence',
    items: [
      { to: '/',         icon: LayoutDashboard, label: 'Dashboard'   },
      { to: '/ask',      icon: Sparkles,        label: 'Ask ARIS'    },
      { to: '/concepts', icon: Map,             label: 'Concept Map' },
      { to: '/briefs',   icon: ScrollText,      label: 'Briefs'      },
      { to: '/timeline', icon: Clock,           label: 'Timeline'    },
      { to: '/graph',    icon: Network,         label: 'Graph'       },
    ],
  },
  {
    label: 'Monitor',
    items: [
      { to: '/documents',   icon: FileText,     label: 'Documents'   },
      { to: '/changes',     icon: GitCompare,   label: 'Changes'     },
      { to: '/baselines',   icon: BookOpen,     label: 'Baselines'   },
      { to: '/trends',      icon: TrendingUp,   label: 'Trends'      },
      { to: '/horizon',     icon: CalendarDays, label: 'Horizon'     },
      { to: '/enforcement', icon: Shield,       label: 'Enforcement' },
    ],
  },
  {
    label: 'Analyse',
    items: [
      { to: '/synthesis', icon: Layers,   label: 'Synthesis'    },
      { to: '/gap',       icon: BarChart3, label: 'Gap Analysis' },
      { to: '/watchlist', icon: Bell,     label: 'Watchlist'    },
    ],
  },
  {
    label: 'System',
    items: [
      { to: '/pdf',      icon: FileInput, label: 'PDF Ingest' },
      { to: '/run',      icon: Play,      label: 'Run Agents' },
      { to: '/learning', icon: Brain,     label: 'Learning'   },
    ],
  },
]

function NavItem({ to, icon: Icon, label, badge }) {
  return (
    <NavLink
      key={to} to={to} end={to === '/'}
      style={({ isActive }) => ({
        display:        'flex',
        alignItems:     'center',
        gap:            9,
        padding:        '6px 10px',
        borderRadius:   'var(--radius)',
        color:          isActive ? 'var(--text)' : 'var(--text-3)',
        background:     isActive ? 'var(--bg-4)' : 'transparent',
        textDecoration: 'none',
        fontSize:       12,
        fontWeight:     isActive ? 500 : 400,
        marginBottom:   1,
        transition:     'all 0.12s',
        borderLeft:     isActive ? '2px solid var(--accent)' : '2px solid transparent',
      })}
    >
      <Icon size={14} style={{ flexShrink: 0 }} />
      <span style={{ flex: 1 }}>{label}</span>
      {badge > 0 && (
        <span style={{
          background:  'var(--red)',
          color:       '#fff',
          fontSize:    10,
          borderRadius: 10,
          padding:     '1px 5px',
          fontFamily:  'var(--font-mono)',
          lineHeight:  '14px',
        }}>{badge}</span>
      )}
    </NavLink>
  )
}

export default function App() {
  const [status,     setStatus]     = useState(null)
  const [jobRunning, setJobRunning] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()

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
        width:       210,
        background:  'var(--bg-2)',
        borderRight: '1px solid var(--border)',
        display:     'flex',
        flexDirection: 'column',
        flexShrink:  0,
      }}>

        {/* Wordmark */}
        <div style={{ padding: '20px 16px 12px', flexShrink: 0 }}>
          <div style={{
            fontFamily:    'var(--font-display)',
            fontSize:      '1.4rem',
            fontWeight:    300,
            color:         'var(--accent)',
            letterSpacing: '-0.01em',
          }}>ARIS</div>
          <div style={{ fontSize: 10, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginTop: 1 }}>
            AI Reg Intelligence
          </div>
        </div>

        {/* Grouped nav — scrollable if viewport is very short */}
        <nav style={{ flex: 1, padding: '4px 8px', overflowY: 'auto' }}>
          {NAV_GROUPS.map(({ label, items }) => (
            <div key={label} style={{ marginBottom: 10 }}>
              {/* Group label */}
              <div style={{
                fontSize:      9,
                fontFamily:    'var(--font-mono)',
                color:         'var(--text-3)',
                textTransform: 'uppercase',
                letterSpacing: '0.08em',
                padding:       '4px 10px 3px',
                opacity:       0.7,
              }}>
                {label}
              </div>

              {/* Items */}
              {items.map(({ to, icon, label: lbl }) => (
                <NavItem
                  key={to}
                  to={to}
                  icon={icon}
                  label={lbl}
                  badge={lbl === 'Changes' ? stats.unreviewed_diffs : 0}
                />
              ))}
            </div>
          ))}
        </nav>

        {/* Footer — Settings + status, always visible */}
        <div style={{
          borderTop: '1px solid var(--border)',
          padding:   '8px 8px 6px',
          flexShrink: 0,
        }}>
          <NavItem to="/settings" icon={Settings} label="Settings" />
          <div style={{
            padding:   '6px 10px 2px',
            fontSize:  11,
            color:     'var(--text-3)',
          }}>
            {jobRunning ? (
              <div className="flex items-center gap-2" style={{ color: 'var(--accent)' }}>
                <Loader2 size={12} className="spin" />
                <span>Agent running…</span>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <div style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: status ? 'var(--green)' : 'var(--red-dim)',
                  flexShrink: 0,
                }} />
                <span>{stats.total_documents ?? '—'} docs · {stats.total_summaries ?? '—'} summarised</span>
              </div>
            )}
            {status?.job?.last_run && (
              <div style={{ marginTop: 3, fontSize: 10, fontFamily: 'var(--font-mono)' }}>
                Last run: {new Date(status.job.last_run).toLocaleTimeString()}
              </div>
            )}
          </div>
        </div>

      </aside>

      {/* ── Main content ── */}
      <main style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
        <Routes>
          <Route path="/"          element={<Dashboard  status={status} />} />
          <Route path="/ask"       element={<AskAris />} />
          <Route path="/concepts"  element={<ConceptMap />} />
          <Route path="/briefs"    element={<Brief />} />
          <Route path="/timeline"  element={<Timeline />} />
          <Route path="/documents" element={<Documents />} />
          <Route path="/changes"   element={<Changes />} />
          <Route path="/baselines" element={<Baselines />} />
          <Route path="/trends"    element={<Trends />} />
          <Route path="/horizon"   element={<Horizon />} />
          <Route path="/enforcement" element={<Enforcement />} />
          <Route path="/synthesis" element={<Synthesis />} />
          <Route path="/gap"       element={<GapAnalysis />} />
          <Route path="/pdf"       element={<PDFIngest />} />
          <Route path="/run"       element={<RunAgents onJobStart={() => setJobRunning(true)} />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/graph"     element={<Graph navigate={navigate} />} />
          <Route path="/learning"  element={<Learning />} />
          <Route path="/settings"  element={<SettingsView status={status} />} />
        </Routes>
      </main>

    </div>
  )
}

