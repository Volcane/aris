import { useState, useEffect, useRef, useCallback } from 'react'
import { Network, ZoomIn, ZoomOut, Maximize2, RefreshCw } from 'lucide-react'
import { api } from '../api.js'
import { Spinner, EmptyState, Badge } from '../components.jsx'

const NODE_COLORS = {
  Critical: '#e05252',
  High:     '#e0834a',
  Medium:   '#d4a843',
  Low:      '#52a878',
  default:  '#607070',
}

const LINK_COLORS = {
  amends:       '#e0834a',
  clarifies:    '#5299d4',
  implements:   '#52a878',
  supersedes:   '#e05252',
  version_of:   '#a0b0af',
}

export default function Graph() {
  const [graphData,  setGraphData]  = useState({ nodes: [], edges: [] })
  const [loading,    setLoading]    = useState(true)
  const [selected,   setSelected]   = useState(null)
  const [jurisdiction, setJur]      = useState('')
  const containerRef = useRef(null)
  const [ForceGraph, setForceGraph] = useState(null)
  const fgRef = useRef(null)

  // Lazy load heavy graph library
  useEffect(() => {
    import('react-force-graph-2d').then(m => setForceGraph(() => m.default))
  }, [])

  const load = async () => {
    setLoading(true)
    try {
      const data = await api.graph(jurisdiction ? { jurisdiction } : {})
      setGraphData(data)
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [jurisdiction])

  const nodeColor  = n => NODE_COLORS[n.urgency] || NODE_COLORS.default
  const linkColor  = l => LINK_COLORS[l.type] || '#2a3030'

  const nodes = graphData.nodes.map(n => ({ ...n }))
  const links = graphData.edges.map(e => ({ source: e.source, target: e.target, ...e }))

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* ── Graph canvas ── */}
      <div style={{ flex: 1, position: 'relative', background: 'var(--bg)' }} ref={containerRef}>
        {/* Controls */}
        <div style={{
          position: 'absolute', top: 20, left: 20, zIndex: 10,
          display: 'flex', flexDirection: 'column', gap: 6,
        }}>
          <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.1rem', color: 'var(--accent)', marginBottom: 4 }}>
            Document Graph
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 8 }}>
            {nodes.length} nodes · {links.length} relationships
          </div>
          <select
            value={jurisdiction}
            onChange={e => setJur(e.target.value)}
            style={{ width: 140, fontSize: 12, padding: '5px 8px' }}
          >
            <option value="">All Jurisdictions</option>
            {['Federal','PA','EU','GB','CA','JP'].map(j => (
              <option key={j} value={j}>{j}</option>
            ))}
          </select>
          <button className="btn-secondary btn-sm" onClick={load} style={{ marginTop: 4 }}>
            <RefreshCw size={12} /> Refresh
          </button>
          <button className="btn-secondary btn-sm" onClick={() => fgRef.current?.zoomToFit(400)}>
            <Maximize2 size={12} /> Fit
          </button>
        </div>

        {/* Legend */}
        <div style={{
          position: 'absolute', bottom: 20, left: 20, zIndex: 10,
          background: 'rgba(13,15,15,0.85)', padding: '12px 14px',
          borderRadius: 'var(--radius)', border: '1px solid var(--border)',
          fontSize: 11, fontFamily: 'var(--font-mono)',
        }}>
          <div style={{ color: 'var(--text-3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Legend</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {Object.entries(NODE_COLORS).filter(([k]) => k !== 'default').map(([label, color]) => (
              <div key={label} className="flex items-center gap-2">
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: color }} />
                <span style={{ color: 'var(--text-2)' }}>{label}</span>
              </div>
            ))}
            <div style={{ marginTop: 4, borderTop: '1px solid var(--border)', paddingTop: 4 }}>
              {Object.entries(LINK_COLORS).map(([label, color]) => (
                <div key={label} className="flex items-center gap-2" style={{ marginTop: 3 }}>
                  <div style={{ width: 16, height: 2, background: color }} />
                  <span style={{ color: 'var(--text-2)' }}>{label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {loading || !ForceGraph ? (
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
            <Spinner size={24} />
          </div>
        ) : nodes.length === 0 ? (
          <EmptyState
            icon={Network}
            title="No document relationships yet"
            message="Run agents and link documents to populate the graph. Use 'python main.py link BASE ADDENDUM' or the Documents view to create relationships."
          />
        ) : (
          <ForceGraph
            ref={fgRef}
            graphData={{ nodes, links }}
            nodeId="id"
            nodeLabel={n => `${n.label}\n${n.jurisdiction} · ${n.doc_type}`}
            nodeColor={nodeColor}
            nodeRelSize={5}
            nodeVal={n => n.urgency === 'Critical' ? 3 : n.urgency === 'High' ? 2 : 1}
            linkColor={linkColor}
            linkWidth={1.5}
            linkDirectionalArrowLength={6}
            linkDirectionalArrowRelPos={1}
            linkLabel={l => l.label}
            onNodeClick={n => setSelected(n)}
            backgroundColor="transparent"
            width={containerRef.current?.clientWidth}
            height={containerRef.current?.clientHeight}
            nodeCanvasObject={(node, ctx, globalScale) => {
              const label  = (node.label || '').slice(0, 28)
              const color  = nodeColor(node)
              const radius = 5 * (node.urgency === 'Critical' ? 1.5 : node.urgency === 'High' ? 1.2 : 1)

              // Node circle
              ctx.beginPath()
              ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
              ctx.fillStyle = color
              ctx.fill()

              // Glow for high/critical
              if (node.urgency === 'Critical' || node.urgency === 'High') {
                ctx.beginPath()
                ctx.arc(node.x, node.y, radius + 3, 0, 2 * Math.PI)
                ctx.strokeStyle = color + '44'
                ctx.lineWidth = 2
                ctx.stroke()
              }

              // Label (only if zoomed in enough)
              if (globalScale >= 0.7) {
                ctx.fillStyle = '#e8edec'
                ctx.font = `${Math.max(9, 11 / globalScale)}px "DM Mono", monospace`
                ctx.textAlign = 'center'
                ctx.fillText(label, node.x, node.y + radius + 9)
              }
            }}
          />
        )}
      </div>

      {/* ── Node detail panel ── */}
      {selected && (
        <div style={{
          width: 320, flexShrink: 0,
          background: 'var(--bg-2)',
          borderLeft: '1px solid var(--border)',
          padding: 20, overflow: 'auto',
        }}>
          <div className="flex items-center justify-between" style={{ marginBottom: 16 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Selected Node</div>
            <button className="btn-icon" onClick={() => setSelected(null)}>✕</button>
          </div>

          <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.05rem', fontWeight: 300, marginBottom: 12, lineHeight: 1.4 }}>
            {selected.label}
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
            <Badge level={selected.jurisdiction}>{selected.jurisdiction}</Badge>
            <Badge level={selected.urgency}>{selected.urgency}</Badge>
            {selected.doc_type && <span className="badge badge-neutral">{selected.doc_type}</span>}
          </div>

          {selected.status && (
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 12 }}>
              Status: {selected.status}
            </div>
          )}

          {selected.url && (
            <a
              href={selected.url} target="_blank" rel="noreferrer"
              style={{ fontSize: 12, color: 'var(--accent)', display: 'block', marginBottom: 12 }}
            >
              View source →
            </a>
          )}

          {/* Connected nodes */}
          {links.filter(l => l.source === selected.id || l.target === selected.id).length > 0 && (
            <div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
                Connections
              </div>
              {links
                .filter(l => l.source === selected.id || l.target === selected.id)
                .map((l, i) => {
                  const other = l.source === selected.id ? l.target : l.source
                  const otherNode = nodes.find(n => n.id === other)
                  return (
                    <div key={i} style={{ fontSize: 12, padding: '6px 0', borderBottom: '1px solid var(--border)', cursor: 'pointer' }}
                      onClick={() => setSelected(otherNode || { id: other, label: other })}>
                      <span style={{ color: LINK_COLORS[l.type] || 'var(--text-3)', fontFamily: 'var(--font-mono)', fontSize: 10 }}>{l.type}</span>
                      <div style={{ color: 'var(--text-2)', marginTop: 2 }} className="truncate">{otherNode?.label || other}</div>
                    </div>
                  )
                })
              }
            </div>
          )}
        </div>
      )}
    </div>
  )
}
