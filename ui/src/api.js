const BASE = '/api'

async function req(path, opts = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

export const api = {
  // Status
  status:         ()          => req('/status'),

  // Documents
  documents:      (params)    => req('/documents?' + new URLSearchParams(params)),
  document:       (id)        => req(`/documents/${encodeURIComponent(id)}`),
  docHistory:     (id)        => req(`/documents/${encodeURIComponent(id)}/history`),

  // Changes / diffs
  changes:        (params)    => req('/changes?' + new URLSearchParams(params)),
  reviewChange:   (id)        => req(`/changes/${id}/review`, { method: 'POST' }),
  manualDiff:     (a, b)      => req('/diff',   { method: 'POST', body: JSON.stringify({ doc_id_a: a, doc_id_b: b }) }),
  linkDocs:       (base, add, type, notes) =>
                                req('/link', { method: 'POST', body: JSON.stringify({ base_id: base, addendum_id: add, link_type: type, notes }) }),

  // Run agents
  runAgents:      (payload)   => req('/run',         { method: 'POST', body: JSON.stringify(payload) }),
  runStatus:      ()          => req('/run/status'),
  runLog:         (since)     => req(`/run/log?since=${since}`),

  // Checklist
  checklist:      (doc_id, company_context) =>
                                req('/checklist', { method: 'POST', body: JSON.stringify({ document_id: doc_id, company_context }) }),

  // Watchlist
  watchlist:      ()          => req('/watchlist'),
  addWatch:       (item)      => req('/watchlist',          { method: 'POST',   body: JSON.stringify(item) }),
  deleteWatch:    (name)      => req(`/watchlist/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  watchMatches:   (name)      => req(`/watchlist/${encodeURIComponent(name)}/matches`),

  // Graph
  graph:          (params)    => req('/graph?' + new URLSearchParams(params)),

  // Export
  exportJson:     (params)    => BASE + '/export/json?' + new URLSearchParams(params),
  exportMarkdown: (params)    => BASE + '/export/markdown?' + new URLSearchParams(params),
}
