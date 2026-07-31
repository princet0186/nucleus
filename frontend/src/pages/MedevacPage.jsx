import { useState, useEffect } from 'react'
import { recordExchange } from '../lib/privacyLog'

// Same key the Query page uses, so the operator's position follows them here.
const ORIGIN_KEY = 'nucleus.origin'

const TRIAGE_OPTIONS = [
  { value: 'T1-IMMEDIATE', label: 'T1 — Immediate', color: 'var(--t1-immediate)' },
  { value: 'T2-DELAYED',   label: 'T2 — Delayed',   color: 'var(--t2-delayed)' },
  { value: 'T3-MINIMAL',   label: 'T3 — Minimal',   color: 'var(--t3-minimal)' },
  { value: 'T4-EXPECTANT', label: 'T4 — Expectant', color: 'var(--t4-expectant)' },
]

const NOTES_PLACEHOLDER =
  `Anything the form can't hold: wounds and interventions, special equipment ` +
  `(hoist, ventilator), CBRN contamination, terrain, patient nationality… ` +
  `With notes, the AI drafts the 9-line from everything at once; without, ` +
  `the form builds a deterministic 9-line entirely on-device.`

export default function MedevacPage() {
  const [form, setForm] = useState({
    triage_category: 'T1-IMMEDIATE',
    grid_coordinate: '',
    call_sign: 'NUCLEUS-01',
    radio_freq: '37.00 MHz FM',
    num_patients: 1,
    is_litter: true,
    security: 'N',
    marking: 'C',
    nationality: 'A',
    cbrn: 'N',
  })
  const [notes, setNotes] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  // The grid doubles as the map origin the rest of the app remembers.
  useEffect(() => {
    if (form.grid_coordinate.trim()) {
      localStorage.setItem(ORIGIN_KEY, form.grid_coordinate.trim())
    }
  }, [form.grid_coordinate])

  const update = (key, value) => setForm(prev => ({ ...prev, [key]: value }))

  const SECURITY_LABELS = {
    N: 'No enemy troops', P: 'Possibly enemy', E: 'Enemy in area', X: 'Armed escort required',
  }
  const MARKING_LABELS = { A: 'Panels', B: 'Pyrotechnic signal', C: 'Smoke signal', D: 'None' }

  // With notes: form facts + prose go through the AI consensus pipeline.
  // Without: the form alone builds a deterministic 9-line, fully on-device.
  const handleGenerate = async () => {
    if (loading) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      let data
      if (notes.trim()) {
        const context = [
          `Triage category: ${form.triage_category}`,
          form.grid_coordinate.trim() && `Pickup grid: ${form.grid_coordinate.trim()}`,
          `Callsign: ${form.call_sign} on ${form.radio_freq}`,
          `Patients: ${form.num_patients}, ${form.is_litter ? 'litter' : 'ambulatory'}`,
          `Pickup site security: ${SECURITY_LABELS[form.security]}`,
          `Site marking: ${MARKING_LABELS[form.marking]}`,
          `Situation notes: ${notes.trim()}`,
        ].filter(Boolean).join('\n')

        const res = await fetch('/nucleus/medevac/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ context, origin: form.grid_coordinate.trim() || null }),
        })
        if (!res.ok) {
          const err = await res.json()
          throw new Error(err.detail || 'MEDEVAC generation failed')
        }
        data = await res.json()
        recordExchange({ mode: 'MEDEVAC', original: context, data })
      } else {
        const res = await fetch('/nucleus/medevac', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(form),
        })
        if (!res.ok) {
          const err = await res.json()
          throw new Error(err.detail || 'MEDEVAC generation failed')
        }
        data = await res.json()
        data.source = 'deterministic'
      }
      setResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const copyRadioFormat = () => {
    navigator.clipboard?.writeText(result.radio_format)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const disputed = result?.consensus?.disputed_fields ?? []
  let sourceLabel = null
  let sourceColor = 'var(--success)'
  if (result) {
    if (result.source === 'gemini_consensus') {
      sourceLabel = `AI consensus — ${result.consensus.samples} samples, ${Math.round(result.consensus.agreement * 100)}% agreement`
    } else if (result.source === 'offline_template') {
      sourceLabel = 'Offline template — no cloud reachable, verify every line'
      sourceColor = 'var(--warning)'
    } else {
      sourceLabel = 'Deterministic 9-line — built on-device from the form, nothing transmitted'
    }
  }

  const fieldLabelStyle = { fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }
  const fieldColStyle = { flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem' }

  return (
    <div className="builder-layout fade-in" style={{ display: 'flex', height: '100%', padding: '1.5rem', gap: '1.5rem' }}>

      {/* Left pane — structured facts + free-text situation notes */}
      <div className="builder-main" style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.4rem', marginBottom: '0.25rem' }}>MEDEVAC Builder</h1>
        </div>

        <div className="card" style={{ display: 'flex', flexDirection: 'column', flex: 1, padding: '1.5rem', background: 'var(--bg-deep)', gap: '1rem', overflowY: 'auto' }}>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <span style={fieldLabelStyle}>Triage Category</span>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {TRIAGE_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => update('triage_category', opt.value)}
                  style={{
                    padding: '0.5rem 1rem',
                    borderRadius: 'var(--radius-sm)',
                    border: `1px solid ${form.triage_category === opt.value ? opt.color : 'var(--border-default)'}`,
                    background: form.triage_category === opt.value ? `${opt.color}22` : 'transparent',
                    color: form.triage_category === opt.value ? opt.color : 'var(--text-secondary)',
                    cursor: 'pointer',
                    fontSize: '0.9rem',
                    transition: 'all 0.2s',
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', gap: '1rem' }}>
            <div style={fieldColStyle}>
              <span style={fieldLabelStyle}>Grid Coordinate (MGRS)</span>
              <input className="input mono" value={form.grid_coordinate} onChange={e => update('grid_coordinate', e.target.value)} placeholder="43S NA 12345 67890" />
            </div>
            <div style={fieldColStyle}>
              <span style={fieldLabelStyle}>Call Sign</span>
              <input className="input mono" value={form.call_sign} onChange={e => update('call_sign', e.target.value)} />
            </div>
            <div style={fieldColStyle}>
              <span style={fieldLabelStyle}>Frequency</span>
              <input className="input mono" value={form.radio_freq} onChange={e => update('radio_freq', e.target.value)} />
            </div>
          </div>

          <div style={{ display: 'flex', gap: '1rem' }}>
            <div style={fieldColStyle}>
              <span style={fieldLabelStyle}>Number of Patients</span>
              <input className="input mono" type="number" min="1" value={form.num_patients} onChange={e => update('num_patients', Number.parseInt(e.target.value, 10) || 1)} />
            </div>
            <div style={fieldColStyle}>
              <span style={fieldLabelStyle}>Patient Type</span>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button className="btn btn-ghost" style={{ flex: 1, borderColor: form.is_litter ? 'var(--accent)' : 'var(--border-default)', color: form.is_litter ? 'var(--accent)' : 'var(--text-secondary)' }} onClick={() => update('is_litter', true)}>Litter</button>
                <button className="btn btn-ghost" style={{ flex: 1, borderColor: !form.is_litter ? 'var(--accent)' : 'var(--border-default)', color: !form.is_litter ? 'var(--accent)' : 'var(--text-secondary)' }} onClick={() => update('is_litter', false)}>Ambulatory</button>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '1rem' }}>
            <div style={fieldColStyle}>
              <span style={fieldLabelStyle}>Pickup Security</span>
              <select className="input" value={form.security} onChange={e => update('security', e.target.value)}>
                <option value="N">No enemy troops</option>
                <option value="P">Possibly enemy</option>
                <option value="E">Enemy in area</option>
                <option value="X">Armed escort required</option>
              </select>
            </div>
            <div style={fieldColStyle}>
              <span style={fieldLabelStyle}>Site Marking</span>
              <select className="input" value={form.marking} onChange={e => update('marking', e.target.value)}>
                <option value="A">Panels</option>
                <option value="B">Pyrotechnic signal</option>
                <option value="C">Smoke signal</option>
                <option value="D">None</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', flex: 1, minHeight: '120px' }}>
            <label htmlFor="medevac-notes" style={fieldLabelStyle}>Situation Notes (optional)</label>
            <textarea
              id="medevac-notes"
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder={NOTES_PLACEHOLDER}
              style={{ flex: 1, resize: 'none', fontSize: '0.9rem', lineHeight: 1.55 }}
              onKeyDown={e => { if (e.key === 'Enter' && e.metaKey) handleGenerate() }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border-default)' }}>
            <button
              className="btn btn-primary"
              onClick={handleGenerate}
              disabled={loading}
              style={{ padding: '0.5rem 1.5rem', borderRadius: 'var(--radius-full)' }}
            >
              {loading ? <div className="spinner" style={{ width: '16px', height: '16px', borderWidth: '2px' }} /> : 'Generate 9-Line ⌘↵'}
            </button>
          </div>
        </div>

        {error && (
          <div style={{ padding: '1rem', background: 'rgba(242, 139, 130, 0.1)', color: 'var(--danger)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(242, 139, 130, 0.2)' }}>
            ⚠ {error}
          </div>
        )}
      </div>

      {/* Right pane — the 9-line, ready to read over the radio */}
      <div className="builder-sidebar" style={{ width: '420px', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <h3 style={{ fontSize: '0.9rem', textTransform: 'uppercase', color: 'var(--text-secondary)', letterSpacing: '0.05em' }}>
          9-Line Request
        </h3>

        {result ? (
          <div className="card slide-up" style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem', background: 'var(--bg-deep)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.5rem' }}>
              <span className="mono" style={{ fontSize: '0.7rem', color: 'var(--accent)' }}>{result.request_id}</span>
              <button
                className="btn btn-ghost"
                style={{ fontSize: '0.75rem', padding: '0.2rem 0.6rem' }}
                onClick={copyRadioFormat}
              >
                {copied ? '✓ Copied' : 'Copy for radio'}
              </button>
            </div>

            <span style={{ fontSize: '0.72rem', color: sourceColor }}>{sourceLabel}</span>

            <pre className="mono" style={{
              background: 'var(--bg-base)',
              padding: '1rem',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.85rem',
              color: 'var(--text-primary)',
              overflowX: 'auto',
              border: '1px solid var(--border-default)',
              lineHeight: 1.4
            }}>
              {result.radio_format}
            </pre>

            {result.narrative && (
              <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                {result.narrative}
              </p>
            )}

            {disputed.length > 0 && (
              <div style={{ padding: '0.6rem 0.8rem', fontSize: '0.78rem', background: 'rgba(253, 226, 147, 0.1)', color: 'var(--warning)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(253, 226, 147, 0.2)' }}>
                ⚠ Verify manually — samples disagreed on: {disputed.join(', ')}
              </div>
            )}
          </div>
        ) : (
          <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            <span style={{ fontSize: '2rem', display: 'block', marginBottom: '1rem', opacity: 0.5 }}>
              ⬢
            </span>
            <span>Generated Evacuation.</span>
          </div>
        )}
      </div>
    </div>
  )
}
