import { Routes, Route, NavLink, useLocation, useNavigate } from 'react-router-dom'
import { useState, useEffect, createContext, useContext, useCallback } from 'react'
import {
  LayoutDashboard, FileText, GitCompare, Play,
  Network, Settings, Loader2,
  Bell, Brain, Layers, FileInput,
  BarChart3, BookOpen, TrendingUp, CalendarDays,
  Sparkles, Map, Clock, ScrollText, Shield,
  ChevronDown, ChevronRight, Bot, Lock,
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

// ── Domain Context ─────────────────────────────────────────────────────────
export const DomainContext = createContext({ domain: 'ai', setDomain: () => {} })
export function useDomain() { return useContext(DomainContext) }

function DomainProvider({ children }) {
  const [domain, setDomainState] = useState(() => {
    try { return localStorage.getItem('aris_domain') || 'ai' } catch { return 'ai' }
  })
  const setDomain = useCallback((d) => {
    setDomainState(d)
    try { localStorage.setItem('aris_domain', d) } catch {}
  }, [])
  return (
    <DomainContext.Provider value={{ domain, setDomain }}>
      {children}
    </DomainContext.Provider>
  )
}

// ── Nav config ─────────────────────────────────────────────────────────────
const INTELLIGENCE_ITEMS = [
  { to: '/',          icon: LayoutDashboard, label: 'Dashboard'   },
  { to: '/ask',       icon: Sparkles,        label: 'Ask ARIS'    },
  { to: '/baselines', icon: BookOpen,        label: 'Baselines'   },
  { to: '/concepts',  icon: Map,             label: 'Concept Map' },
  { to: '/timeline',  icon: Clock,           label: 'Timeline'    },
  { to: '/graph',     icon: Network,         label: 'Graph'       },
  { to: '/briefs',    icon: ScrollText,      label: 'Briefs'      },
]

const MONITOR_ITEMS = [
  { to: '/documents',    icon: FileText,     label: 'Documents'   },
  { to: '/changes',      icon: GitCompare,   label: 'Changes'     },
  { to: '/trends',       icon: TrendingUp,   label: 'Trends'      },
  { to: '/horizon',      icon: CalendarDays, label: 'Horizon'     },
  { to: '/enforcement',  icon: Shield,       label: 'Enforcement' },
]

const ANALYSE_ITEMS = [
  { to: '/synthesis', icon: Layers,    label: 'Synthesis'    },
  { to: '/gap',       icon: BarChart3, label: 'Gap Analysis' },
  { to: '/watchlist', icon: Bell,      label: 'Watchlist'    },
]

const SYSTEM_ITEMS = [
  { to: '/pdf',      icon: FileInput, label: 'PDF Ingest' },
  { to: '/run',      icon: Play,      label: 'Run Agents' },
  { to: '/learning', icon: Brain,     label: 'Learning'   },
]

// ── NavItem ────────────────────────────────────────────────────────────────
function NavItem({ to, icon: Icon, label, badge }) {
  return (
    <NavLink to={to} end={to === '/'} style={({ isActive }) => ({
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '5px 10px', borderRadius: 'var(--radius)',
      color: isActive ? 'var(--text)' : 'var(--text-3)',
      background: isActive ? 'var(--bg-4)' : 'transparent',
      textDecoration: 'none', fontSize: 12, fontWeight: isActive ? 500 : 400,
      marginBottom: 1, transition: 'color 0.1s, background 0.1s',
      borderLeft: isActive ? '2px solid var(--accent)' : '2px solid transparent',
    })}>
      <Icon size={13} style={{ flexShrink: 0 }} />
      <span style={{ flex: 1 }}>{label}</span>
      {badge > 0 && (
        <span style={{
          background: 'var(--red)', color: '#fff', fontSize: 10,
          borderRadius: 10, padding: '1px 5px',
          fontFamily: 'var(--font-mono)', lineHeight: '14px',
        }}>{badge}</span>
      )}
    </NavLink>
  )
}

function GroupLabel({ label }) {
  return (
    <div style={{
      fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--text-3)',
      textTransform: 'uppercase', letterSpacing: '0.08em',
      padding: '4px 10px 3px', opacity: 0.7,
    }}>{label}</div>
  )
}

// ── Collapsible Monitor section ────────────────────────────────────────────
function MonitorSection({ domainKey, label, Icon, accentColor, isActive, onClick, unreviewedDiffs }) {
  return (
    <div style={{ marginBottom: 2 }}>
      <button onClick={onClick} style={{
        display: 'flex', alignItems: 'center', gap: 7,
        width: '100%', padding: '5px 10px',
        background: isActive ? 'var(--bg-3)' : 'transparent',
        border: 'none',
        borderLeft: isActive ? `2px solid ${accentColor}` : '2px solid transparent',
        borderRadius: 'var(--radius)', cursor: 'pointer',
        color: isActive ? 'var(--text)' : 'var(--text-3)',
        fontSize: 12, fontWeight: isActive ? 500 : 400,
        textAlign: 'left', marginBottom: 1, transition: 'all 0.12s',
      }}>
        <Icon size={13} style={{ flexShrink: 0, color: isActive ? accentColor : 'inherit' }} />
        <span style={{ flex: 1 }}>{label}</span>
        <span style={{
          fontSize: 9, fontFamily: 'var(--font-mono)', padding: '1px 5px',
          borderRadius: 3,
          background: isActive ? accentColor + '22' : 'var(--bg-3)',
          color: isActive ? accentColor : 'var(--text-3)',
          border: `1px solid ${isActive ? accentColor + '44' : 'transparent'}`,
          transition: 'all 0.12s',
        }}>{domainKey.toUpperCase()}</span>
        {isActive
          ? <ChevronDown  size={11} style={{ flexShrink: 0, opacity: 0.5 }} />
          : <ChevronRight size={11} style={{ flexShrink: 0, opacity: 0.4 }} />}
      </button>

      {isActive && (
        <div style={{ paddingLeft: 6 }}>
          {MONITOR_ITEMS.map(({ to, icon, label: lbl }) => (
            <NavItem key={to} to={to} icon={icon} label={lbl}
              badge={lbl === 'Changes' ? unreviewedDiffs : 0} />
          ))}
        </div>
      )}
    </div>
  )
}

// ── Domain toggle ──────────────────────────────────────────────────────────
function DomainToggle({ domain, setDomain }) {
  const AI_COLOR      = 'var(--accent)'
  const PRIVACY_COLOR = '#7c9ef7'
  return (
    <div style={{ display: 'flex', gap: 3, padding: '6px 0 2px' }}>
      {[
        { key: 'ai',      label: 'AI Reg',  color: AI_COLOR      },
        { key: 'privacy', label: 'Privacy', color: PRIVACY_COLOR },
      ].map(({ key, label, color }) => (
        <button key={key} onClick={() => setDomain(key)} style={{
          flex: 1, padding: '3px 0', fontSize: 10,
          fontFamily: 'var(--font-mono)', fontWeight: domain === key ? 600 : 400,
          background: domain === key ? color + '18' : 'transparent',
          border: `1px solid ${domain === key ? color + '55' : 'var(--border)'}`,
          borderRadius: 4,
          color: domain === key ? color : 'var(--text-3)',
          cursor: 'pointer', transition: 'all 0.12s', letterSpacing: '0.04em',
        }}>{label}</button>
      ))}
    </div>
  )
}

// ── App ────────────────────────────────────────────────────────────────────
function AppInner() {
  const [status,     setStatus]     = useState(null)
  const [jobRunning, setJobRunning] = useState(false)
  const { domain, setDomain }       = useDomain()
  const navigate                    = useNavigate()

  const AI_COLOR      = 'var(--accent)'
  const PRIVACY_COLOR = '#7c9ef7'
  const domainColor   = domain === 'privacy' ? PRIVACY_COLOR : AI_COLOR

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

  const stats           = status?.stats || {}
  const unreviewedDiffs = stats.unreviewed_diffs || 0

  const footerCount = domain === 'privacy'
    ? `${stats.privacy_documents ?? '—'} privacy docs`
    : `${stats.ai_documents ?? stats.total_documents ?? '—'} AI docs`

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>

      {/* Sidebar */}
      <aside style={{
        width: 214, background: 'var(--bg-2)',
        borderRight: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column', flexShrink: 0,
      }}>
        {/* Wordmark */}
        <div style={{ padding: '16px 14px 8px', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <div style={{
              fontFamily: 'var(--font-display)', fontSize: '1.35rem',
              fontWeight: 300, color: domainColor,
              letterSpacing: '-0.01em', transition: 'color 0.2s',
            }}>ARIS</div>
            <div style={{
              fontSize: 9, fontFamily: 'var(--font-mono)', color: domainColor,
              opacity: 0.75, background: domainColor + '14',
              padding: '1px 5px', borderRadius: 3,
              border: `1px solid ${domainColor}30`, transition: 'all 0.2s',
            }}>{domain === 'privacy' ? 'PRIVACY' : 'AI REG'}</div>
          </div>
          <div style={{ fontSize: 9, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginTop: 1 }}>
            Automated Regulatory Intelligence
          </div>
          <DomainToggle domain={domain} setDomain={setDomain} />
        </div>

        {/* Nav */}
        <nav style={{ flex: 1, padding: '4px 8px', overflowY: 'auto' }}>

          <div style={{ marginBottom: 10 }}>
            <GroupLabel label="Intelligence" />
            {INTELLIGENCE_ITEMS.map(({ to, icon, label }) => (
              <NavItem key={to} to={to} icon={icon} label={label} />
            ))}
          </div>

          <div style={{ marginBottom: 10 }}>
            <GroupLabel label="Monitor" />
            <MonitorSection
              domainKey="ai" label="AI Regulation" Icon={Bot}
              accentColor={AI_COLOR}
              isActive={domain === 'ai'}
              onClick={() => setDomain('ai')}
              unreviewedDiffs={unreviewedDiffs}
            />
            <MonitorSection
              domainKey="privacy" label="Data Privacy" Icon={Lock}
              accentColor={PRIVACY_COLOR}
              isActive={domain === 'privacy'}
              onClick={() => setDomain('privacy')}
              unreviewedDiffs={unreviewedDiffs}
            />
          </div>

          <div style={{ marginBottom: 10 }}>
            <GroupLabel label="Analyse" />
            {ANALYSE_ITEMS.map(({ to, icon, label }) => (
              <NavItem key={to} to={to} icon={icon} label={label} />
            ))}
          </div>

          <div style={{ marginBottom: 4 }}>
            <GroupLabel label="System" />
            {SYSTEM_ITEMS.map(({ to, icon, label }) => (
              <NavItem key={to} to={to} icon={icon} label={label} />
            ))}
          </div>

        </nav>

        {/* Footer */}
        <div style={{ borderTop: '1px solid var(--border)', padding: '8px 8px 6px', flexShrink: 0 }}>
          <NavItem to="/settings" icon={Settings} label="Settings" />
          <div style={{ padding: '6px 10px 2px', fontSize: 11, color: 'var(--text-3)' }}>
            {jobRunning ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: domainColor }}>
                <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} />
                <span>Agent running…</span>
              </div>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{
                  width: 6, height: 6, borderRadius: '50%',
                  background: status ? 'var(--green)' : 'var(--red-dim)', flexShrink: 0,
                }} />
                <span>{footerCount} · {stats.total_summaries ?? '—'} summarised</span>
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

      {/* Main */}
      <main style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
        <Routes>
          <Route path="/"            element={<Dashboard   status={status} domain={domain} />} />
          <Route path="/ask"         element={<AskAris     domain={domain} />} />
          <Route path="/concepts"    element={<ConceptMap  domain={domain} />} />
          <Route path="/briefs"      element={<Brief       domain={domain} />} />
          <Route path="/timeline"    element={<Timeline    domain={domain} />} />
          <Route path="/documents"   element={<Documents   domain={domain} />} />
          <Route path="/changes"     element={<Changes     domain={domain} />} />
          <Route path="/baselines"   element={<Baselines   domain={domain} />} />
          <Route path="/trends"      element={<Trends      domain={domain} />} />
          <Route path="/horizon"     element={<Horizon     domain={domain} />} />
          <Route path="/enforcement" element={<Enforcement domain={domain} />} />
          <Route path="/synthesis"   element={<Synthesis   domain={domain} />} />
          <Route path="/gap"         element={<GapAnalysis domain={domain} />} />
          <Route path="/watchlist"   element={<Watchlist   domain={domain} />} />
          <Route path="/pdf"         element={<PDFIngest />} />
          <Route path="/run"         element={<RunAgents   onJobStart={() => setJobRunning(true)} />} />
          <Route path="/graph"       element={<Graph       navigate={navigate} domain={domain} />} />
          <Route path="/learning"    element={<Learning />} />
          <Route path="/settings"    element={<SettingsView status={status} />} />
        </Routes>
      </main>

    </div>
  )
}

export default function App() {
  return (
    <DomainProvider>
      <AppInner />
    </DomainProvider>
  )
}
