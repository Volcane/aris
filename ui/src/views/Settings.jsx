import { useState } from 'react'
import { CheckCircle2, XCircle, ExternalLink, Settings } from 'lucide-react'
import { SectionHeader } from '../components.jsx'

export default function SettingsView({ status }) {
  const keys    = status?.api_keys || {}
  const stats   = status?.stats    || {}

  const apiKeyDefs = [
    {
      key:      'anthropic',
      label:    'Anthropic API Key',
      url:      'https://console.anthropic.com/settings/keys',
      required: true,
      note:     'Required for all AI summarization, checklist generation, and diff analysis',
    },
    {
      key:      'regulations_gov',
      label:    'Regulations.gov API Key',
      url:      'https://open.gsa.gov/api/regulationsgov/',
      required: false,
      note:     'Enables Federal rulemaking dockets and public comment data',
    },
    {
      key:      'congress_gov',
      label:    'Congress.gov API Key',
      url:      'https://api.congress.gov/sign-up/',
      required: false,
      note:     'Enables US Congressional bill tracking',
    },
    {
      key:      'legiscan',
      label:    'LegiScan API Key',
      url:      'https://legiscan.com/legiscan',
      required: false,
      note:     'Required for all US state legislature monitoring',
    },
  ]

  return (
    <div style={{ padding: '28px 32px', maxWidth: 760 }}>
      <SectionHeader title="Settings" subtitle="System configuration and API key status" />

      {/* API Keys */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 16 }}>
          API Keys
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {apiKeyDefs.map(def => {
            const configured = !!keys[def.key]
            return (
              <div key={def.key} style={{
                display: 'flex', alignItems: 'flex-start', gap: 14,
                padding: '14px 16px',
                background: 'var(--bg-2)',
                border: `1px solid ${configured ? 'var(--green-dim)' : def.required ? 'var(--red-dim)' : 'var(--border)'}`,
                borderRadius: 'var(--radius)',
              }}>
                {configured
                  ? <CheckCircle2 size={18} style={{ color: 'var(--green)', flexShrink: 0, marginTop: 1 }} />
                  : <XCircle     size={18} style={{ color: def.required ? 'var(--red)' : 'var(--text-3)', flexShrink: 0, marginTop: 1 }} />
                }
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)' }}>
                    {def.label}
                    {def.required && <span style={{ fontSize: 11, color: 'var(--red)', marginLeft: 8, fontFamily: 'var(--font-mono)' }}>REQUIRED</span>}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{def.note}</div>
                  {!configured && (
                    <a href={def.url} target="_blank" rel="noreferrer"
                      style={{ fontSize: 12, color: 'var(--accent)', marginTop: 6, display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      Register for free key <ExternalLink size={11} />
                    </a>
                  )}
                </div>
                <div style={{
                  fontSize: 11, fontFamily: 'var(--font-mono)',
                  padding: '3px 8px', borderRadius: 4,
                  background: configured ? 'var(--green-dim)' : 'var(--bg-4)',
                  color: configured ? 'var(--green)' : 'var(--text-3)',
                }}>
                  {configured ? 'CONFIGURED' : 'NOT SET'}
                </div>
              </div>
            )
          })}
        </div>
        <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
          To configure keys, edit <code style={{ background: 'var(--bg-4)', padding: '1px 5px', borderRadius: 3 }}>config/keys.env</code> in the project root and restart the server.
        </div>
      </div>

      {/* Enabled Jurisdictions */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
          Enabled Jurisdictions
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 8 }}>US States</div>
            {(status?.enabled_states || []).map(s => (
              <div key={s} className="flex items-center gap-2" style={{ fontSize: 13, marginBottom: 4 }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--green)' }} />
                {s}
              </div>
            ))}
          </div>
          <div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 8 }}>International</div>
            {(status?.enabled_international || []).map(j => (
              <div key={j} className="flex items-center gap-2" style={{ fontSize: 13, marginBottom: 4 }}>
                <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--green)' }} />
                {j}
              </div>
            ))}
          </div>
        </div>
        <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
          To add or remove jurisdictions, edit <code style={{ background: 'var(--bg-4)', padding: '1px 5px', borderRadius: 3 }}>config/jurisdictions.py</code>.
        </div>
      </div>

      {/* Database stats */}
      <div style={{ marginBottom: 32 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
          Database
        </div>
        <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
          {[
            ['Total documents',        stats.total_documents],
            ['Summarised',             stats.total_summaries],
            ['Pending summarisation',  stats.pending_summaries],
            ['Federal documents',      stats.federal_documents],
            ['State documents',        stats.state_documents],
            ['Total diffs',            stats.total_diffs],
            ['Unreviewed diffs',       stats.unreviewed_diffs],
            ['Critical diffs',         stats.critical_diffs],
          ].map(([label, val]) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 14px', borderBottom: '1px solid var(--border)', fontSize: 13 }}>
              <span style={{ color: 'var(--text-2)' }}>{label}</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{val ?? '—'}</span>
            </div>
          ))}
        </div>
      </div>

      {/* CLI quick reference */}
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
            ['python main.py run',                  'Full pipeline: fetch + summarize'],
            ['python main.py fetch --source EU',    'Fetch EU only'],
            ['python main.py summarize',            'Summarize pending docs'],
            ['python main.py changes',              'Show recent changes'],
            ['python main.py diff DOC-A DOC-B',     'Compare two documents'],
            ['python main.py link BASE ADDENDUM',   'Link addendum to base'],
            ['python main.py watch --interval 24',  'Run every 24h'],
          ].map(([cmd, desc]) => (
            <div key={cmd} style={{ display: 'flex', gap: 16 }}>
              <span style={{ color: 'var(--accent)' }}>{cmd}</span>
              <span style={{ color: 'var(--text-3)' }}># {desc}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
