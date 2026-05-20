import { useState } from 'react'

const TRIAGE_OPTIONS = [
  { value: 'T1-IMMEDIATE', label: 'T1 — Immediate', color: 'var(--t1-immediate)' },
  { value: 'T2-DELAYED',   label: 'T2 — Delayed',   color: 'var(--t2-delayed)' },
  { value: 'T3-MINIMAL',   label: 'T3 — Minimal',   color: 'var(--t3-minimal)' },
  { value: 'T4-EXPECTANT', label: 'T4 — Expectant', color: 'var(--t4-expectant)' },
]

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
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)

  const update = (key, value) => setForm(prev => ({ ...prev, [key]: value }))

  const handleGenerate = async () => {
    setLoading(true)
    setResult(null)
    try {
      const res = await fetch('/nucleus/medevac', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await res.json()
      setResult(data)
    } catch {
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="playground-layout fade-in" style={{ display: 'flex', height: '100%', padding: '1.5rem', gap: '1.5rem' }}>
      
      {
        // Left Pane - Input
      }
      <div className="playground-main" style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.4rem', marginBottom: '0.25rem' }}>MEDEVAC Builder</h1>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            Auto-generate a deterministic NATO-standard evacuation request. Offline capable.
          </p>
        </div>

        <div className="card" style={{ display: 'flex', flexDirection: 'column', flex: 1, padding: '1.5rem', background: 'var(--bg-deep)', gap: '1rem', overflowY: 'auto' }}>
          
          {
            // Triage Selection
          }
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Triage Category</label>
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
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Grid Coordinate (MGRS)</label>
              <input className="input mono" value={form.grid_coordinate} onChange={e => update('grid_coordinate', e.target.value)} placeholder="43S NA 12345 67890" />
            </div>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Call Sign</label>
              <input className="input mono" value={form.call_sign} onChange={e => update('call_sign', e.target.value)} />
            </div>
          </div>

          <div style={{ display: 'flex', gap: '1rem' }}>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Number of Patients</label>
              <input className="input mono" type="number" min="1" value={form.num_patients} onChange={e => update('num_patients', parseInt(e.target.value) || 1)} />
            </div>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Patient Type</label>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <button className="btn btn-ghost" style={{ flex: 1, borderColor: form.is_litter ? 'var(--accent)' : 'var(--border-default)', color: form.is_litter ? 'var(--accent)' : 'var(--text-secondary)' }} onClick={() => update('is_litter', true)}>Litter</button>
                <button className="btn btn-ghost" style={{ flex: 1, borderColor: !form.is_litter ? 'var(--accent)' : 'var(--border-default)', color: !form.is_litter ? 'var(--accent)' : 'var(--text-secondary)' }} onClick={() => update('is_litter', false)}>Ambulatory</button>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '1rem' }}>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Pickup Security</label>
              <select className="input" value={form.security} onChange={e => update('security', e.target.value)}>
                <option value="N">No enemy troops</option>
                <option value="P">Possibly enemy</option>
                <option value="E">Enemy in area</option>
                <option value="X">Armed escort required</option>
              </select>
            </div>
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Site Marking</label>
              <select className="input" value={form.marking} onChange={e => update('marking', e.target.value)}>
                <option value="A">Panels</option>
                <option value="B">Pyrotechnic signal</option>
                <option value="C">Smoke signal</option>
                <option value="D">None</option>
              </select>
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: '1rem', borderTop: '1px solid var(--border-default)', marginTop: 'auto' }}>
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
      </div>

      {
        // Right Pane - Results
      }
      <div className="playground-sidebar" style={{ width: '420px', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <h3 style={{ fontSize: '0.9rem', textTransform: 'uppercase', color: 'var(--text-secondary)', letterSpacing: '0.05em' }}>
          Generated Output
        </h3>
        
        {result ? (
          <div className="card slide-up" style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem', flex: 1, background: 'var(--bg-deep)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span className="mono" style={{ fontSize: '0.7rem', color: 'var(--accent)' }}>{result.request_id}</span>
              <button 
                className="btn btn-ghost" 
                style={{ fontSize: '0.75rem', padding: '0.2rem 0.6rem' }}
                onClick={() => navigator.clipboard?.writeText(result.radio_format)}
              >
                Copy Format
              </button>
            </div>

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
          </div>
        ) : (
          <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            <span style={{ fontSize: '2rem', display: 'block', marginBottom: '1rem', opacity: 0.5 }}>⬡</span>
            Generate request to see radio format.
          </div>
        )}
      </div>
    </div>
  )
}
