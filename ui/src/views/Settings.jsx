import { useState, useEffect } from 'react'
import { CheckCircle2, XCircle, ExternalLink, AlertTriangle, Info,
  Bell, Clock, Send, Check, RefreshCw } from 'lucide-react'
import { Spinner } from '../components.jsx'
import { SectionHeader } from '../components.jsx'

// What you lose without each key — shown when key is not configured
const KEY_IMPACT = {
  anthropic: {
    loses: [
      'AI summarisation — documents fetched but never interpreted',
      'Plain-English summaries, urgency ratings, requirements lists',
      'Compliance checklists and change detection (diffs)',
      'Ask ARIS Q&A, Briefs, Synthesis, Gap Analysis',
    ],
    severity: 'critical',
  },
  regulations_gov: {
    loses: [
      'Federal rulemaking dockets (proposed rules, public comments)',
      'NPRM tracking — rules in progress before they finalise',
    ],
    severity: 'moderate',
  },
  congress_gov: {
    loses: [
      'US Congressional bill tracking (House and Senate)',
      'Committee hearing schedules and markup activity',
    ],
    severity: 'moderate',
  },
  legiscan: {
    loses: [
      'All US state legislature monitoring (all 5 enabled states)',
      'State bill introductions, amendments, passage events',
      'State-level AI regulation and privacy bill tracking',
    ],
    severity: 'high',
  },
  courtlistener: {
    loses: [
      'Federal court opinions and litigation tracking',
      'CourtListener enforcement actions in the Enforcement view',
    ],
    severity: 'low',
  },
}

// ── Timezone helpers ─────────────────────────────────────────────────────────
// The server stores jur_time as UTC HH:MM and computes next_run in UTC.
// We convert to/from local time so the user always sees and enters local time.

function localTimeToUtc(localHHMM) {
  // Convert "HH:MM" in local time → "HH:MM" in UTC
  const [hh, mm] = localHHMM.split(':').map(Number)
  const d = new Date()
  d.setHours(hh, mm, 0, 0)
  const uh = String(d.getUTCHours()).padStart(2, '0')
  const um = String(d.getUTCMinutes()).padStart(2, '0')
  return `${uh}:${um}`
}

function utcTimeToLocal(utcHHMM) {
  // Convert stored UTC "HH:MM" → "HH:MM" in local time for display/input
  if (!utcHHMM) return '08:00'
  const [hh, mm] = utcHHMM.split(':').map(Number)
  const d = new Date()
  d.setUTCHours(hh, mm, 0, 0)
  const lh = String(d.getHours()).padStart(2, '0')
  const lm = String(d.getMinutes()).padStart(2, '0')
  return `${lh}:${lm}`
}

function parseServerDt(isoStr) {
  // Server returns UTC datetimes without Z suffix — add it so the browser
  // correctly converts to local time when formatting
  if (!isoStr) return null
  return isoStr.endsWith('Z') ? isoStr : isoStr + 'Z'
}

export default function SettingsView({ status }) {
  const [expandedKey,      setExpandedKey]      = useState(null)
  const [schedule,         setSchedule]         = useState(null)
  const [schedSaving,      setSchedSaving]       = useState(false)
  const [schedSaved,       setSchedSaved]        = useState(false)
  const [schedEnabled,     setSchedEnabled]      = useState(false)
  const [schedInterval,    setSchedInterval]     = useState(24)
  const [schedDomain,      setSchedDomain]       = useState('both')
  const [schedLookback,    setSchedLookback]     = useState(7)
  // Jurisdiction track
  const [jurEnabled,       setJurEnabled]        = useState(false)
  const [jurDays,          setJurDays]           = useState([0,1,2,3,4])
  const [jurTime,          setJurTime]           = useState('08:00')
  const [jurDomain,        setJurDomain]         = useState('both')
  const [jurLookback,      setJurLookback]       = useState(7)
  // Enforcement track
  const [enfEnabled,       setEnfEnabled]        = useState(false)
  const [enfInterval,      setEnfInterval]       = useState(6)
  const [enfLookback,      setEnfLookback]       = useState(2)
  const [notifConfig,      setNotifConfig]       = useState(null)
  const [testSending,      setTestSending]       = useState(false)
  const [testResult,       setTestResult]        = useState(null)
  const keys  = status?.api_keys || {}
  const stats = status?.stats    || {}

  // Load schedule and notification config on mount
  useEffect(() => {
    fetch('/api/schedule').then(r => r.json()).then(cfg => {
      setSchedule(cfg)
      setSchedEnabled(cfg.enabled || false)
      setSchedInterval(cfg.interval_hours || 24)
      setSchedDomain(cfg.domain || 'both')
      setSchedLookback(cfg.lookback_days || 7)
      // Jurisdiction track
      setJurEnabled(cfg.jur_enabled || false)
      setJurDays(cfg.jur_days ? cfg.jur_days.split(',').map(Number) : [0,1,2,3,4])
      setJurTime(utcTimeToLocal(cfg.jur_time || '08:00'))  // display in local time
      setJurDomain(cfg.jur_domain || 'both')
      setJurLookback(cfg.jur_lookback || 7)
      // Enforcement track
      setEnfEnabled(cfg.enf_enabled || false)
      setEnfInterval(cfg.enf_interval_hours || 6)
      setEnfLookback(cfg.enf_lookback || 2)
    }).catch(() => {})
    fetch('/api/notifications/config').then(r => r.json()).then(cfg => {
      setNotifConfig(cfg)
    }).catch(() => {})
  }, [])

  const saveSchedule = async () => {
    setSchedSaving(true)
    setSchedSaved(false)
    try {
      const res = await fetch('/api/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          enabled: schedEnabled, interval_hours: schedInterval,
          domain: schedDomain, lookback_days: schedLookback,
          // Jurisdiction track
          jur_enabled: jurEnabled, jur_days: jurDays.join(','),
          jur_time: localTimeToUtc(jurTime), jur_domain: jurDomain, jur_lookback: jurLookback,  // store as UTC
          // Enforcement track
          enf_enabled: enfEnabled, enf_interval_hours: enfInterval,
          enf_lookback: enfLookback,
        }),
      })
      const updated = await res.json()
      setSchedule(updated)
      setSchedSaved(true)
      setTimeout(() => setSchedSaved(false), 3000)
    } catch {}
    setSchedSaving(false)
  }

  const triggerNow = async () => {
    await fetch('/api/schedule/trigger', { method: 'POST' })
    window.location.href = '/run'
  }

  const sendTest = async () => {
    setTestSending(true)
    setTestResult(null)
    try {
      const res = await fetch('/api/notifications/test', { method: 'POST' })
      const data = await res.json()
      setTestResult(data)
    } catch (e) {
      setTestResult({ error: e.message })
    }
    setTestSending(false)
  }

  const apiKeyDefs = [
    {
      key:      'anthropic',
      label:    'Anthropic API Key',
      url:      'https://console.anthropic.com/settings/keys',
      required: true,
      note:     'Powers all AI analysis — summarisation, diffs, Q&A, briefs, gap analysis',
    },
    {
      key:      'legiscan',
      label:    'LegiScan API Key',
      url:      'https://legiscan.com/legiscan',
      required: false,
      note:     'US state legislature monitoring — all 5 enabled states require this',
    },
    {
      key:      'regulations_gov',
      label:    'Regulations.gov API Key',
      url:      'https://open.gsa.gov/api/regulationsgov/',
      required: false,
      note:     'Federal rulemaking dockets, NPRMs, and public comment data',
    },
    {
      key:      'congress_gov',
      label:    'Congress.gov API Key',
      url:      'https://api.congress.gov/sign-up/',
      required: false,
      note:     'US Congressional bills, committee hearings, markup schedules',
    },
    {
      key:      'courtlistener',
      label:    'CourtListener API Key',
      url:      'https://www.courtlistener.com/sign-in/',
      required: false,
      note:     'Federal court opinions and litigation data',
    },
  ]

  const missingRequired  = apiKeyDefs.filter(d => d.required  && !keys[d.key])
  const missingOptional  = apiKeyDefs.filter(d => !d.required && !keys[d.key])
  const configuredCount  = apiKeyDefs.filter(d => keys[d.key]).length

  return (
    <div style={{ padding: '28px 32px', maxWidth: 760 }}>
      <SectionHeader title="Settings" subtitle="System configuration and API key status" />

      {/* Status summary */}
      {missingRequired.length > 0 && (
        <div style={{
          marginBottom: 24, padding: '12px 16px',
          background: 'rgba(224,82,82,0.08)', border: '1px solid rgba(224,82,82,0.3)',
          borderRadius: 'var(--radius)', display: 'flex', alignItems: 'flex-start', gap: 10,
        }}>
          <AlertTriangle size={15} style={{ color: 'var(--red)', flexShrink: 0, marginTop: 1 }} />
          <div style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.5 }}>
            <strong style={{ color: 'var(--red)' }}>Anthropic API key not configured.</strong>{' '}
            ARIS can fetch documents but cannot summarise, diff, or answer questions without it.
            Set <code style={{ background: 'var(--bg-4)', padding: '1px 4px', borderRadius: 3 }}>ANTHROPIC_API_KEY</code> in{' '}
            <code style={{ background: 'var(--bg-4)', padding: '1px 4px', borderRadius: 3 }}>config/keys.env</code> and restart the server.
          </div>
        </div>
      )}

      {missingRequired.length === 0 && missingOptional.length > 0 && (
        <div style={{
          marginBottom: 24, padding: '10px 14px',
          background: 'var(--bg-3)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius)', display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <Info size={14} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
          <div style={{ fontSize: 13, color: 'var(--text-3)' }}>
            {configuredCount}/{apiKeyDefs.length} keys configured.{' '}
            {missingOptional.length} optional {missingOptional.length === 1 ? 'key' : 'keys'} not set —
            click any unconfigured key to see what you're missing.
          </div>
        </div>
      )}

      {/* API Keys */}
      <div style={{ marginBottom: 32 }}>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)',
          textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 14,
        }}>API Keys</div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {apiKeyDefs.map(def => {
            const configured = !!keys[def.key]
            const impact     = KEY_IMPACT[def.key]
            const isExpanded = expandedKey === def.key
            const sevColor   = !configured
              ? (def.required ? 'var(--red)' : impact?.severity === 'high' ? 'var(--orange)' : impact?.severity === 'moderate' ? 'var(--yellow)' : 'var(--text-3)')
              : 'var(--green)'

            return (
              <div key={def.key}>
                <div
                  onClick={() => !configured && setExpandedKey(isExpanded ? null : def.key)}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: 12,
                    padding: '13px 15px',
                    background: 'var(--bg-2)',
                    border: `1px solid ${configured ? 'var(--green-dim)' : def.required ? 'rgba(224,82,82,0.4)' : 'var(--border)'}`,
                    borderRadius: isExpanded ? 'var(--radius) var(--radius) 0 0' : 'var(--radius)',
                    cursor: configured ? 'default' : 'pointer',
                    transition: 'border-color 0.15s',
                  }}
                >
                  {configured
                    ? <CheckCircle2 size={16} style={{ color: 'var(--green)', flexShrink: 0, marginTop: 1 }} />
                    : <XCircle     size={16} style={{ color: sevColor, flexShrink: 0, marginTop: 1 }} />
                  }

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 13, fontWeight: 500 }}>{def.label}</span>
                      {def.required && (
                        <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--red)', background: 'rgba(224,82,82,0.12)', padding: '1px 6px', borderRadius: 3 }}>
                          REQUIRED
                        </span>
                      )}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{def.note}</div>

                    {!configured && (
                      <a href={def.url} target="_blank" rel="noreferrer"
                        onClick={e => e.stopPropagation()}
                        style={{ fontSize: 12, color: 'var(--accent)', marginTop: 6, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        Get free key <ExternalLink size={11} />
                      </a>
                    )}
                  </div>

                  <div style={{
                    fontSize: 11, fontFamily: 'var(--font-mono)', flexShrink: 0,
                    padding: '3px 8px', borderRadius: 4,
                    background: configured ? 'var(--green-dim)' : 'var(--bg-4)',
                    color: configured ? 'var(--green)' : 'var(--text-3)',
                  }}>
                    {configured ? 'CONFIGURED' : 'NOT SET'}
                  </div>
                </div>

                {/* Impact panel — shown when unconfigured and expanded */}
                {!configured && isExpanded && impact && (
                  <div style={{
                    padding: '12px 15px',
                    background: 'var(--bg-3)',
                    border: `1px solid ${def.required ? 'rgba(224,82,82,0.4)' : 'var(--border)'}`,
                    borderTop: 'none',
                    borderRadius: '0 0 var(--radius) var(--radius)',
                  }}>
                    <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: sevColor, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
                      Without this key you lose:
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                      {impact.loses.map((loss, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, fontSize: 12, color: 'var(--text-2)', lineHeight: 1.4 }}>
                          <span style={{ color: sevColor, flexShrink: 0, marginTop: 1 }}>✕</span>
                          {loss}
                        </div>
                      ))}
                    </div>
                    <div style={{ marginTop: 12, padding: '8px 10px', background: 'var(--bg-2)', borderRadius: 'var(--radius)', fontSize: 12, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
                      Set <span style={{ color: 'var(--accent)' }}>{def.key.toUpperCase()}_KEY</span> in{' '}
                      <span style={{ color: 'var(--text-2)' }}>config/keys.env</span> and restart the server
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>

        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
          All keys are set in{' '}
          <code style={{ background: 'var(--bg-4)', padding: '1px 5px', borderRadius: 3 }}>config/keys.env</code>{' '}
          — never committed to version control. Restart the server after changes.
        </div>
      </div>

      {/* Enabled Jurisdictions */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
          Enabled Jurisdictions
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
              US States
              {!keys.legiscan && <span style={{ fontSize: 10, color: 'var(--orange)', fontFamily: 'var(--font-mono)' }}>LegiScan key required</span>}
            </div>
            {(status?.enabled_states || []).map(s => (
              <div key={s} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, marginBottom: 4 }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: keys.legiscan ? 'var(--green)' : 'var(--orange)' }} />
                <span style={{ color: keys.legiscan ? 'var(--text-2)' : 'var(--text-3)' }}>{s}</span>
                {!keys.legiscan && <span style={{ fontSize: 10, color: 'var(--text-3)' }}>inactive</span>}
              </div>
            ))}
          </div>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 8 }}>International</div>
            {(status?.enabled_international || []).map(j => (
              <div key={j} style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, marginBottom: 4 }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--green)' }} />
                {j}
              </div>
            ))}
          </div>
        </div>
        <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
          To add or remove jurisdictions, edit{' '}
          <code style={{ background: 'var(--bg-4)', padding: '1px 5px', borderRadius: 3 }}>config/jurisdictions.py</code>.
        </div>
      </div>

      {/* Database stats — split by domain */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
          Database
        </div>
        <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
          {[
            ['Total documents',        stats.total_documents,     null],
            ['AI regulation docs',     stats.ai_documents,        'var(--accent)'],
            ['Data privacy docs',      stats.privacy_documents,   '#7c9ef7'],
            ['Summarised',             stats.total_summaries,     null],
            ['Pending summarisation',  stats.pending_summaries,   stats.pending_summaries > 0 ? 'var(--yellow)' : null],
            ['Total changes detected', stats.total_diffs,         null],
            ['Unreviewed changes',     stats.unreviewed_diffs,    stats.unreviewed_diffs > 0 ? 'var(--orange)' : null],
            ['Critical changes',       stats.critical_diffs,      stats.critical_diffs > 0 ? 'var(--red)' : null],
            ['Enforcement actions',    stats.enforcement_actions, null],
          ].map(([label, val, color]) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 14px', borderBottom: '1px solid var(--border)', fontSize: 13 }}>
              <span style={{ color: 'var(--text-2)' }}>{label}</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: color || 'var(--text)' }}>{val ?? '—'}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Scheduled Monitoring */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Clock size={12} /> Scheduled Monitoring
        </div>

        {/* ── Jurisdiction Track ─────────────────────────────────────────── */}
        <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '16px 18px', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: jurEnabled ? 16 : 0 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, fontWeight: 500 }}>
              <input type="checkbox" checked={jurEnabled} onChange={e => setJurEnabled(e.target.checked)}
                style={{ width: 'auto', accentColor: 'var(--accent)' }} />
              <span style={{ color: jurEnabled ? 'var(--text)' : 'var(--text-3)' }}>Jurisdiction monitoring</span>
            </label>
            <span style={{ fontSize: 11, color: 'var(--text-3)', marginLeft: 4 }}>
              — runs states, international &amp; federal on specific days
            </span>
            {schedule?.jur_last_run && (
              <span style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginLeft: 'auto' }}>
                Last: {new Date(parseServerDt(schedule.jur_last_run)).toLocaleString()}
              </span>
            )}
          </div>

          {jurEnabled && (<>
            {/* Day-of-week selector */}
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 7 }}>Run on</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {[['Mon',0],['Tue',1],['Wed',2],['Thu',3],['Fri',4],['Sat',5],['Sun',6]].map(([label, val]) => {
                  const active = jurDays.includes(val)
                  return (
                    <button key={val} onClick={() => setJurDays(prev =>
                        active ? prev.filter(d => d !== val) : [...prev, val].sort()
                      )} style={{
                        padding: '5px 12px', fontSize: 12, fontWeight: 500,
                        borderRadius: 'var(--radius)', cursor: 'pointer',
                        border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
                        background: active ? 'var(--accent-dim)' : 'var(--bg-3)',
                        color: active ? 'var(--accent)' : 'var(--text-3)',
                        transition: 'all 0.1s',
                      }}>
                      {label}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Time + domain + lookback row */}
            <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr 1fr', gap: 12, marginBottom: 10 }}>
              <div>
                <label style={{ fontSize: 11, color: 'var(--text-3)', display: 'block', marginBottom: 5 }}>Run at (server time)</label>
                <input type="time" value={jurTime} onChange={e => setJurTime(e.target.value)}
                  style={{ width: '100%', background: 'var(--bg-3)', border: '1px solid var(--border)',
                    borderRadius: 'var(--radius)', padding: '6px 8px', color: 'var(--text)',
                    fontSize: 13, colorScheme: 'dark' }} />
              </div>
              <div>
                <label style={{ fontSize: 11, color: 'var(--text-3)', display: 'block', marginBottom: 5 }}>Domain</label>
                <select value={jurDomain} onChange={e => setJurDomain(e.target.value)} style={{ width: '100%' }}>
                  <option value="both">Both (AI + Privacy)</option>
                  <option value="ai">AI Regulation only</option>
                  <option value="privacy">Data Privacy only</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: 11, color: 'var(--text-3)', display: 'block', marginBottom: 5 }}>Lookback</label>
                <select value={jurLookback} onChange={e => setJurLookback(Number(e.target.value))} style={{ width: '100%' }}>
                  <option value={1}>1 day</option>
                  <option value={3}>3 days</option>
                  <option value={7}>7 days</option>
                  <option value={14}>14 days</option>
                </select>
              </div>
            </div>

            {schedule?.jur_next_run && (
              <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
                Next run: {new Date(parseServerDt(schedule.jur_next_run)).toLocaleString()}
              </div>
            )}
          </>)}
        </div>

        {/* ── Enforcement Track ──────────────────────────────────────────── */}
        <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '16px 18px', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: enfEnabled ? 16 : 0 }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13, fontWeight: 500 }}>
              <input type="checkbox" checked={enfEnabled} onChange={e => setEnfEnabled(e.target.checked)}
                style={{ width: 'auto', accentColor: 'var(--accent)' }} />
              <span style={{ color: enfEnabled ? 'var(--text)' : 'var(--text-3)' }}>Enforcement monitoring</span>
            </label>
            <span style={{ fontSize: 11, color: 'var(--text-3)', marginLeft: 4 }}>
              — checks enforcement feeds every N hours throughout the day
            </span>
            {schedule?.enf_last_run && (
              <span style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', marginLeft: 'auto' }}>
                Last: {new Date(parseServerDt(schedule.enf_last_run)).toLocaleString()}
              </span>
            )}
          </div>

          {enfEnabled && (<>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 10 }}>
              <div>
                <label style={{ fontSize: 11, color: 'var(--text-3)', display: 'block', marginBottom: 5 }}>Check every</label>
                <select value={enfInterval} onChange={e => setEnfInterval(Number(e.target.value))} style={{ width: '100%' }}>
                  <option value={1}>1 hour</option>
                  <option value={2}>2 hours</option>
                  <option value={4}>4 hours</option>
                  <option value={6}>6 hours</option>
                  <option value={8}>8 hours</option>
                  <option value={12}>12 hours</option>
                  <option value={24}>24 hours</option>
                </select>
              </div>
              <div>
                <label style={{ fontSize: 11, color: 'var(--text-3)', display: 'block', marginBottom: 5 }}>Lookback window</label>
                <select value={enfLookback} onChange={e => setEnfLookback(Number(e.target.value))} style={{ width: '100%' }}>
                  <option value={1}>1 day</option>
                  <option value={2}>2 days</option>
                  <option value={3}>3 days</option>
                  <option value={7}>7 days</option>
                </select>
              </div>
            </div>

            {schedule?.enf_next_run && (
              <div style={{ fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)' }}>
                Next run: {new Date(parseServerDt(schedule.enf_next_run)).toLocaleString()}
              </div>
            )}
          </>)}
        </div>

        {/* ── Save / Run now ─────────────────────────────────────────────── */}
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn-primary btn-sm" onClick={saveSchedule} disabled={schedSaving}>
            {schedSaving ? <><Spinner size={11} /> Saving…</> : schedSaved ? <><Check size={11} /> Saved</> : 'Save schedule'}
          </button>
          <button className="btn-secondary btn-sm" onClick={triggerNow}
            title="Trigger the full pipeline immediately (all enabled sources)">
            <RefreshCw size={11} /> Run now
          </button>
        </div>
      </div>

            {/* Notifications */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Bell size={12} /> Notifications
        </div>
        <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)', padding: '16px 18px' }}>
          {notifConfig ? (
            <>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                <div style={{ padding: '10px 12px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', display: 'flex', alignItems: 'center', gap: 8 }}>
                  {notifConfig.email_configured
                    ? <CheckCircle2 size={13} style={{ color: 'var(--green)', flexShrink: 0 }} />
                    : <XCircle size={13} style={{ color: 'var(--text-3)', flexShrink: 0 }} />}
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 500, color: notifConfig.email_configured ? 'var(--text)' : 'var(--text-3)' }}>Email</div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                      {notifConfig.email_configured ? notifConfig.recipient_email : 'Set NOTIFY_EMAIL in keys.env'}
                    </div>
                  </div>
                </div>
                <div style={{ padding: '10px 12px', background: 'var(--bg-3)', borderRadius: 'var(--radius)', display: 'flex', alignItems: 'center', gap: 8 }}>
                  {notifConfig.slack_configured
                    ? <CheckCircle2 size={13} style={{ color: 'var(--green)', flexShrink: 0 }} />
                    : <XCircle size={13} style={{ color: 'var(--text-3)', flexShrink: 0 }} />}
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 500, color: notifConfig.slack_configured ? 'var(--text)' : 'var(--text-3)' }}>Slack</div>
                    <div style={{ fontSize: 11, color: 'var(--text-3)' }}>
                      {notifConfig.slack_configured ? 'Webhook configured' : 'Set SLACK_WEBHOOK_URL in keys.env'}
                    </div>
                  </div>
                </div>
              </div>
              {(notifConfig.email_configured || notifConfig.slack_configured) ? (
                <>
                  <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 10 }}>Notify when:</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 16 }}>
                    {[
                      { key: 'notify_critical', label: 'Critical findings' },
                      { key: 'notify_high',     label: 'High-urgency docs' },
                      { key: 'notify_digest',   label: 'Daily digest' },
                    ].map(({ key, label }) => (
                      <div key={key} style={{ fontSize: 12, padding: '4px 10px', borderRadius: 20,
                        background: notifConfig[key] ? 'var(--accent-dim)' : 'var(--bg-4)',
                        border: `1px solid ${notifConfig[key] ? 'var(--accent)' : 'var(--border)'}`,
                        color: notifConfig[key] ? 'var(--accent)' : 'var(--text-3)' }}>
                        {label}
                      </div>
                    ))}
                    <div style={{ fontSize: 11, color: 'var(--text-3)', alignSelf: 'center', marginLeft: 4 }}>
                      Configure with NOTIFY_ON_* in keys.env
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <button className="btn-secondary btn-sm" onClick={sendTest} disabled={testSending}>
                      {testSending ? <><Spinner size={11} /> Sending…</> : <><Send size={11} /> Send test</>}
                    </button>
                    {testResult && (
                      <span style={{ fontSize: 12, color: testResult.any_sent ? 'var(--green)' : 'var(--red)' }}>
                        {testResult.any_sent ? '✓ Sent successfully' : testResult.error || 'No channels configured'}
                      </span>
                    )}
                  </div>
                </>
              ) : (
                <div style={{ fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
                  Add <code style={{ background: 'var(--bg-4)', padding: '1px 4px', borderRadius: 3 }}>NOTIFY_EMAIL</code> or{' '}
                  <code style={{ background: 'var(--bg-4)', padding: '1px 4px', borderRadius: 3 }}>SLACK_WEBHOOK_URL</code> to{' '}
                  <code style={{ background: 'var(--bg-4)', padding: '1px 4px', borderRadius: 3 }}>config/keys.env</code> to enable notifications.
                  See README for SMTP setup.
                </div>
              )}
            </>
          ) : (
            <div style={{ fontSize: 12, color: 'var(--text-3)' }}>Loading…</div>
          )}
        </div>
      </div>

      {/* CLI quick reference — updated with domain flag */}
      <div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
          CLI Quick Reference
        </div>
        <div style={{
          background: 'var(--bg)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius)',
          padding: '14px 16px',
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
          lineHeight: 2,
          color: 'var(--text-2)',
        }}>
          {[
            ['python main.py run --domain both',     'Full pipeline: fetch + summarize (AI + Privacy)'],
            ['python main.py run --domain ai',       'AI regulation only'],
            ['python main.py run --domain privacy',  'Data privacy only'],
            ['python main.py fetch --source EU',     'Fetch EU sources only'],
            ['python main.py summarize',             'Summarize pending docs'],
            ['python main.py changes',               'Show recent changes'],
            ['python main.py watch --interval 24',   'Run every 24h'],
          ].map(([cmd, desc]) => (
            <div key={cmd} style={{ display: 'flex', gap: 16 }}>
              <span style={{ color: 'var(--accent)', flexShrink: 0 }}>{cmd}</span>
              <span style={{ color: 'var(--text-3)' }}># {desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
