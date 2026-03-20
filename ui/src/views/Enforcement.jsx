import { useState, useEffect, useCallback } from 'react'
import {
  Shield, RefreshCw, ExternalLink, AlertTriangle, Scale,
  FileText, Globe, Filter, ChevronDown, ChevronUp, Sparkles,
} from 'lucide-react'
import { Spinner, EmptyState, SectionHeader, Badge } from '../components.jsx'
import { useNavigate } from 'react-router-dom'

const enfApi = {
  list:  (p={}) => fetch(`/api/enforcement?${new URLSearchParams(p)}`).then(r=>r.json()),
  stats: ()     => fetch('/api/enforcement/stats').then(r=>r.json()),
  fetch: (days) => fetch(`/api/enforcement/fetch?days=${days}`,{method:'POST'}).then(r=>r.json()),
}

const SOURCE_META = {
  ftc:          { label:'FTC',          color:'#4f8fe0', agency:'Federal Trade Commission'        },
  sec:          { label:'SEC',          color:'#a06bd4', agency:'Securities & Exchange Commission' },
  cfpb:         { label:'CFPB',         color:'#52a878', agency:'Consumer Financial Protection Bureau'},
  eeoc:         { label:'EEOC',         color:'#d4a843', agency:'Equal Employment Opportunity Commission'},
  doj:          { label:'DOJ',          color:'#e0834a', agency:'Department of Justice'           },
  ico:          { label:'ICO',          color:'#4fd4c8', agency:"Information Commissioner's Office (UK)"},
  courtlistener:{ label:'Courts',       color:'#e05252', agency:'Federal Courts (CourtListener)'  },
}

const TYPE_META = {
  enforcement: { label:'Enforcement', icon:Shield,       color:'var(--red)'    },
  litigation:  { label:'Litigation',  icon:Scale,        color:'var(--orange)' },
  opinion:     { label:'Opinion',     icon:FileText,     color:'var(--accent)' },
  settlement:  { label:'Settlement',  icon:Shield,       color:'var(--green)'  },
  guidance:    { label:'Guidance',    icon:FileText,     color:'var(--text-3)' },
}

const OUTCOME_COLORS = {
  fine:        'var(--red)',
  settlement:  'var(--green)',
  injunction:  'var(--orange)',
  pending:     'var(--yellow)',
  opinion:     'var(--accent)',
  enforcement: 'var(--orange)',
  dismissed:   'var(--text-3)',
}

const JURISDICTIONS = ['','Federal','GB','EU']
const ACTION_TYPES  = ['','enforcement','litigation','opinion','settlement','guidance']
const SOURCES       = ['','ftc','sec','cfpb','eeoc','doj','ico','courtlistener']

// ── Action card ───────────────────────────────────────────────────────────────

function ActionCard({ action, onSelect, isSelected }) {
  const src    = SOURCE_META[action.source] || { label: action.source, color:'#607070' }
  const typeCfg = TYPE_META[action.action_type] || { label: action.action_type, icon: FileText, color:'var(--text-3)' }
  const TypeIcon = typeCfg.icon

  return (
    <div
      onClick={() => onSelect(action)}
      className="card card-hover"
      style={{
        padding:    '11px 14px',
        cursor:     'pointer',
        borderLeft: `3px solid ${src.color}`,
        background: isSelected ? 'var(--bg-3)' : 'var(--bg-2)',
        marginBottom: 6,
      }}
    >
      <div className="flex items-center gap-3">
        {/* Source badge */}
        <div style={{
          fontSize:     10, fontFamily:'var(--font-mono)', fontWeight:700,
          color:        src.color, minWidth:44, textAlign:'center',
          background:   `${src.color}18`,
          padding:      '2px 5px', borderRadius:3, flexShrink:0,
        }}>
          {src.label}
        </div>

        {/* Title */}
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize:12, fontWeight:500, lineHeight:1.4 }} className="truncate">
            {action.title}
          </div>
          <div style={{ fontSize:10, color:'var(--text-3)', fontFamily:'var(--font-mono)', marginTop:1 }}>
            {action.agency}
            {action.respondent && <span> · {action.respondent.slice(0,40)}</span>}
          </div>
        </div>

        {/* Type */}
        <div className="flex items-center gap-1" style={{
          fontSize:10, fontFamily:'var(--font-mono)', color:typeCfg.color, flexShrink:0,
        }}>
          <TypeIcon size={10} />
          {typeCfg.label}
        </div>

        {/* Penalty */}
        {action.penalty_amount && (
          <div style={{
            fontSize:10, fontFamily:'var(--font-mono)', color:'var(--red)',
            background:'rgba(224,82,82,0.08)', padding:'2px 6px', borderRadius:3, flexShrink:0,
          }}>
            {action.penalty_amount.slice(0,20)}
          </div>
        )}

        {/* Date */}
        <div style={{ fontSize:10, color:'var(--text-3)', fontFamily:'var(--font-mono)', flexShrink:0 }}>
          {action.published_date?.slice(0,10)}
        </div>
      </div>
    </div>
  )
}

// ── Detail panel ──────────────────────────────────────────────────────────────

function DetailPanel({ action, onClose }) {
  const navigate = useNavigate()
  if (!action) return null

  const src     = SOURCE_META[action.source] || { label: action.source, color:'#607070', agency:'' }
  const typeCfg = TYPE_META[action.action_type] || { label: action.action_type, icon:FileText, color:'var(--text-3)' }
  const TypeIcon = typeCfg.icon

  return (
    <div style={{
      width:320, flexShrink:0, borderLeft:'1px solid var(--border)',
      overflow:'auto', padding:'20px 18px', background:'var(--bg)',
    }}>
      {/* Source + type header */}
      <div className="flex items-center gap-2" style={{ marginBottom:14 }}>
        <div style={{
          fontSize:11, fontFamily:'var(--font-mono)', fontWeight:700,
          color:src.color, background:`${src.color}18`,
          padding:'3px 8px', borderRadius:3,
        }}>
          {src.label}
        </div>
        <div className="flex items-center gap-1" style={{
          fontSize:11, fontFamily:'var(--font-mono)', color:typeCfg.color,
        }}>
          <TypeIcon size={11}/> {typeCfg.label}
        </div>
        <div style={{ marginLeft:'auto' }}>
          <button className="btn-icon" onClick={onClose}
            style={{ fontSize:13, color:'var(--text-3)' }}>✕</button>
        </div>
      </div>

      <div style={{ fontWeight:500, fontSize:13, lineHeight:1.4, marginBottom:8 }}>
        {action.title}
      </div>

      {/* Meta grid */}
      <div style={{ display:'grid', gridTemplateColumns:'auto 1fr', gap:'6px 12px',
                    fontSize:12, marginBottom:14 }}>
        {action.agency && <>
          <span style={{ color:'var(--text-3)' }}>Agency</span>
          <span style={{ color:'var(--text-2)' }}>{action.agency}</span>
        </>}
        {action.respondent && <>
          <span style={{ color:'var(--text-3)' }}>Respondent</span>
          <span style={{ color:'var(--text-2)' }}>{action.respondent}</span>
        </>}
        {action.jurisdiction && <>
          <span style={{ color:'var(--text-3)' }}>Jurisdiction</span>
          <span style={{ color:'var(--text-2)' }}>{action.jurisdiction}</span>
        </>}
        {action.published_date && <>
          <span style={{ color:'var(--text-3)' }}>Date</span>
          <span style={{ color:'var(--text-2)' }}>{action.published_date.slice(0,10)}</span>
        </>}
        {action.outcome && <>
          <span style={{ color:'var(--text-3)' }}>Outcome</span>
          <span style={{
            color: OUTCOME_COLORS[action.outcome] || 'var(--text-2)',
            fontFamily:'var(--font-mono)', fontSize:11,
          }}>{action.outcome}</span>
        </>}
        {action.penalty_amount && <>
          <span style={{ color:'var(--text-3)' }}>Penalty</span>
          <span style={{ color:'var(--red)', fontWeight:500 }}>{action.penalty_amount}</span>
        </>}
      </div>

      {/* Summary */}
      {action.summary && (
        <div style={{
          fontSize:12, color:'var(--text-2)', lineHeight:1.6,
          borderTop:'1px solid var(--border)', paddingTop:12, marginBottom:12,
        }}>
          {action.summary}
        </div>
      )}

      {/* Concepts */}
      {action.ai_concepts?.length > 0 && (
        <div style={{ marginBottom:12 }}>
          <div style={{ fontSize:10, fontFamily:'var(--font-mono)', color:'var(--text-3)',
                        textTransform:'uppercase', letterSpacing:'0.05em', marginBottom:5 }}>
            AI Concepts
          </div>
          <div style={{ display:'flex', flexWrap:'wrap', gap:4 }}>
            {action.ai_concepts.map(c => (
              <span key={c} style={{
                fontSize:10, fontFamily:'var(--font-mono)',
                background:'var(--bg-3)', border:'1px solid var(--border)',
                padding:'2px 7px', borderRadius:3,
                color:'var(--accent)',
              }}>
                {c.replace(/_/g,' ')}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Related regulations */}
      {action.related_regs?.length > 0 && (
        <div style={{ marginBottom:14 }}>
          <div style={{ fontSize:10, fontFamily:'var(--font-mono)', color:'var(--text-3)',
                        textTransform:'uppercase', letterSpacing:'0.05em', marginBottom:5 }}>
            Related Regulations
          </div>
          <div style={{ display:'flex', flexWrap:'wrap', gap:4 }}>
            {action.related_regs.map(r => (
              <span key={r} style={{
                fontSize:10, fontFamily:'var(--font-mono)',
                background:'var(--bg-3)', border:'1px solid var(--border)',
                padding:'2px 7px', borderRadius:3, color:'var(--text-2)',
              }}>
                {r}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
        {action.url && (
          <a href={action.url} target="_blank" rel="noreferrer"
             className="btn-secondary btn-sm" style={{ justifyContent:'center' }}>
            <ExternalLink size={11}/> View source
          </a>
        )}
        <button className="btn-ghost btn-sm" style={{ justifyContent:'center' }}
          onClick={()=>navigate('/ask')}>
          <Sparkles size={11} style={{ color:'var(--accent)' }}/>
          Ask ARIS about this case →
        </button>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Enforcement({ domain }) {
  const [items,       setItems]       = useState([])
  const [stats,       setStats]       = useState(null)
  const [loading,     setLoading]     = useState(true)
  const [fetching,    setFetching]    = useState(false)
  const [selected,    setSelected]    = useState(null)
  const [jurisdiction,setJur]         = useState('')
  const [source,      setSource]      = useState('')
  const [actionType,  setActionType]  = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params = { days:365, limit:200 }
      if (jurisdiction) params.jurisdiction = jurisdiction
      if (source)       params.source       = source
      if (actionType)   params.action_type  = actionType
      const [data, s] = await Promise.all([
        enfApi.list(params),
        enfApi.stats().catch(()=>null),
      ])
      setItems(data.items || [])
      setStats(s)
    } finally { setLoading(false) }
  }, [jurisdiction, source, actionType])

  useEffect(()=>{ load() },[load])

  const triggerFetch = async () => {
    setFetching(true)
    try {
      await enfApi.fetch(90)
      // Poll for new data after a short delay
      setTimeout(()=>{ load(); setFetching(false) }, 5000)
    } catch { setFetching(false) }
  }

  const isEmpty = !loading && items.length === 0

  // Source breakdown for sidebar
  const bySource = stats?.by_source || {}

  return (
    <div style={{ display:'flex', height:'100%', overflow:'hidden' }}>

      {/* ── Sidebar: source breakdown ── */}
      <div style={{
        width:220, flexShrink:0, borderRight:'1px solid var(--border)',
        overflow:'auto', padding:'20px 0', background:'var(--bg-2)',
      }}>
        <div style={{ fontSize:11, fontFamily:'var(--font-mono)', color:'var(--text-3)',
                      textTransform:'uppercase', letterSpacing:'0.06em',
                      padding:'0 16px 10px' }}>
          Sources
        </div>

        {/* All */}
        <div
          onClick={()=>setSource('')}
          style={{
            padding:'7px 16px', cursor:'pointer', fontSize:12,
            background: source==='' ? 'var(--bg-3)' : 'transparent',
            borderLeft: source==='' ? '3px solid var(--accent)' : '3px solid transparent',
          }}
        >
          <div className="flex items-center justify-between">
            <span style={{ fontWeight: source===''?500:400 }}>All Sources</span>
            <span style={{ fontSize:10, fontFamily:'var(--font-mono)',
                           color:'var(--text-3)' }}>{stats?.total||0}</span>
          </div>
        </div>

        {Object.entries(SOURCE_META).map(([key, meta]) => {
          const count = bySource[key] || 0
          return (
            <div key={key} onClick={()=>setSource(key)}
              style={{
                padding:'7px 16px', cursor:'pointer', fontSize:12,
                background: source===key ? 'var(--bg-3)' : 'transparent',
                borderLeft: source===key ? `3px solid ${meta.color}` : '3px solid transparent',
              }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span style={{
                    fontSize:10, fontFamily:'var(--font-mono)', fontWeight:700,
                    color: meta.color,
                  }}>{meta.label}</span>
                  <span style={{ color: source===key?'var(--text)':'var(--text-2)',
                                  fontWeight:source===key?500:400, fontSize:11 }}>
                    {meta.agency.split(' ').slice(0,3).join(' ')}
                  </span>
                </div>
                {count>0 && (
                  <span style={{ fontSize:10, fontFamily:'var(--font-mono)',
                                 color:'var(--text-3)' }}>{count}</span>
                )}
              </div>
            </div>
          )
        })}

        <div style={{ borderTop:'1px solid var(--border)', margin:'10px 0', padding:'10px 16px 0' }}>
          <div style={{ fontSize:11, fontFamily:'var(--font-mono)', color:'var(--text-3)',
                        textTransform:'uppercase', letterSpacing:'0.06em', marginBottom:8 }}>
            Setup
          </div>
          <div style={{ fontSize:11, color:'var(--text-3)', lineHeight:1.6 }}>
            Add <code style={{ background:'var(--bg-4)', padding:'1px 4px', borderRadius:2 }}>
            COURTLISTENER_KEY</code> to <code style={{ background:'var(--bg-4)', padding:'1px 4px', borderRadius:2 }}>
            keys.env</code> for higher court data rate limits.
            <a href="https://www.courtlistener.com/sign-in/" target="_blank" rel="noreferrer"
               style={{ color:'var(--accent)', display:'block', marginTop:4 }}>
              Free registration →
            </a>
          </div>
        </div>
      </div>

      {/* ── Main content ── */}
      <div style={{ flex:1, display:'flex', flexDirection:'column', overflow:'hidden' }}>

        {/* Header */}
        <div style={{ padding:'20px 24px 0', flexShrink:0 }}>
          <SectionHeader
            title="Enforcement & Litigation"
            subtitle={stats ? `${stats.total} AI-related actions tracked` : ''}
            action={
              <button className="btn-secondary btn-sm" onClick={triggerFetch}
                      disabled={fetching}>
                <RefreshCw size={12} style={{
                  animation: fetching?'spin 1s linear infinite':'none'
                }}/>
                {fetching ? 'Fetching…' : 'Fetch Latest'}
              </button>
            }
          />

          {/* Filters */}
          <div className="flex gap-3 items-center"
               style={{ paddingBottom:12, borderBottom:'1px solid var(--border)',
                        flexWrap:'wrap', marginTop:8 }}>
            <select value={jurisdiction} onChange={e=>setJur(e.target.value)}
                    style={{ width:130, fontSize:12 }}>
              {JURISDICTIONS.map(j=><option key={j} value={j}>{j||'All Jurisdictions'}</option>)}
            </select>
            <select value={actionType} onChange={e=>setActionType(e.target.value)}
                    style={{ width:130, fontSize:12 }}>
              {ACTION_TYPES.map(t=><option key={t} value={t}>{t||'All Types'}</option>)}
            </select>
            <div style={{ marginLeft:'auto', fontSize:11, color:'var(--text-3)',
                          fontFamily:'var(--font-mono)' }}>
              {items.length} results
            </div>
          </div>
        </div>

        {/* List */}
        <div style={{ flex:1, overflow:'auto', padding:'12px 24px' }}>
          {loading ? (
            <div style={{ display:'flex', justifyContent:'center', padding:40 }}>
              <Spinner/>
            </div>
          ) : isEmpty ? (
            <div style={{ padding:'40px 0' }}>
              <EmptyState
                icon={Shield}
                title="No enforcement actions yet"
                message='Click "Fetch Latest" to pull AI-related enforcement actions from FTC, SEC, CFPB, EEOC, DOJ, ICO, and CourtListener.'
              />
            </div>
          ) : (
            items.map(item => (
              <ActionCard
                key={item.id}
                action={item}
                onSelect={setSelected}
                isSelected={selected?.id === item.id}
              />
            ))
          )}
        </div>
      </div>

      {/* ── Detail panel ── */}
      {selected && (
        <DetailPanel action={selected} onClose={()=>setSelected(null)} />
      )}
    </div>
  )
}
