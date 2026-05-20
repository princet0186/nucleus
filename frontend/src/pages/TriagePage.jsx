import { useState } from 'react'

const TRIAGE_COLORS = {
  'T1-IMMEDIATE': { color: 'var(--t1-immediate)', bg: 'var(--t1-bg)', badge: 'badge-t1' },
  'T2-DELAYED':   { color: 'var(--t2-delayed)',   bg: 'var(--t2-bg)', badge: 'badge-t2' },
  'T3-MINIMAL':   { color: 'var(--t3-minimal)',    bg: 'var(--t3-bg)', badge: 'badge-t3' },
  'T4-EXPECTANT': { color: 'var(--t4-expectant)',  bg: 'var(--t4-bg)', badge: 'badge-t4' },
}

export default function TriagePage() {
  const [input, setInput] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleClassify = async () => {
    if (!input.trim() || input.trim().length < 5) return
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const res = await fetch('/nucleus/triage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ injury_description: input.trim() }),
      })
      if (!res.ok) throw new Error('Classification failed. Ensure Gemini API key is set.')
      const data = await res.json()
      setResult(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const triageStyle = result?.triage_result ? TRIAGE_COLORS[result.triage_result.triage_category] : null

  return (
    <div className="playground-layout fade-in" style={{ display: 'flex', height: '100%', padding: '1.5rem', gap: '1.5rem' }}>
      
      {
        // Left Pane - Input
      }
      <div className="playground-main" style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.4rem', marginBottom: '0.25rem' }}>Playground: Medical Triage</h1>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            Gemini 3.0 Pro Medical Reasoning with Zero-Knowledge Privacy Pipeline.
          </p>
        </div>

        <div className="card" style={{ display: 'flex', flexDirection: 'column', flex: 1, padding: '1rem', background: 'var(--bg-deep)' }}>
          <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>
            Injury Description
          </label>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Describe combat injuries here... (e.g., GSW to left chest, difficulty breathing, weak pulse)"
            style={{ flex: 1, resize: 'none', border: 'none', background: 'transparent', outline: 'none', fontSize: '1rem' }}
            onKeyDown={e => { if (e.key === 'Enter' && e.metaKey) handleClassify() }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '1rem', borderTop: '1px solid var(--border-default)' }}>
            <span className="mono" style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>{input.length} chars</span>
            <button 
              className="btn btn-primary" 
              onClick={handleClassify} 
              disabled={loading || input.trim().length < 5}
              style={{ padding: '0.5rem 1.5rem', borderRadius: 'var(--radius-full)' }}
            >
              {loading ? <div className="spinner" style={{ width: '16px', height: '16px', borderWidth: '2px' }} /> : 'Run Triage ⌘↵'}
            </button>
          </div>
        </div>

        {error && (
          <div style={{ padding: '1rem', background: 'rgba(242, 139, 130, 0.1)', color: 'var(--danger)', borderRadius: 'var(--radius-sm)', border: '1px solid rgba(242, 139, 130, 0.2)' }}>
            ⚠ {error}
          </div>
        )}
      </div>

      {
        // Right Pane - Results & Privacy Metadata
      }
      <div className="playground-sidebar" style={{ width: '360px', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <h3 style={{ fontSize: '0.9rem', textTransform: 'uppercase', color: 'var(--text-secondary)', letterSpacing: '0.05em' }}>
          Triage Result
        </h3>
        
        {result ? (
          <>
            {result.triage_result ? (
              <div className="card slide-up" style={{ padding: '1.25rem', borderColor: triageStyle?.color || 'var(--border-default)', boxShadow: `0 0 20px ${triageStyle?.bg || 'transparent'}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                  <span className={`badge ${triageStyle?.badge || ''}`} style={{ fontSize: '0.9rem', padding: '0.4rem 0.8rem' }}>
                    {result.triage_result.triage_category}
                  </span>
                </div>
                
                <p style={{ fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '1.5rem', lineHeight: 1.5 }}>
                  {result.triage_result.confidence_reasoning}
                </p>

                <div style={{ marginBottom: '1rem' }}>
                  <h4 style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Treatment Actions</h4>
                  <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                    {result.triage_result.treatment_protocol.immediate_actions.map((action, i) => (
                      <li key={i} style={{ fontSize: '0.85rem', display: 'flex', gap: '0.5rem' }}>
                        <span className="mono" style={{ color: 'var(--accent)' }}>{String(i + 1).padStart(2, '0')}</span>
                        {action}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : (
              <div className="card slide-up" style={{ padding: '1rem', color: 'var(--warning)' }}>
                ⚠ Could not parse structured triage data. See raw response.
              </div>
            )}

            <div className="card slide-up" style={{ padding: '1rem', background: 'var(--bg-deep)' }}>
              <h4 style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Privacy Proof</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Sanitization:</span>
                  <span style={{ color: result.privacy.sanitization_applied ? 'var(--success)' : 'var(--text-muted)' }}>
                    {result.privacy.sanitization_applied ? 'Applied' : 'None'}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Fields Redacted:</span>
                  <span className="mono">{result.privacy.fields_redacted?.length || 0}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>Privacy Cost (ε):</span>
                  <span className="mono">{result.privacy.epsilon_spent?.toFixed(2)}</span>
                </div>
                <div style={{ marginTop: '0.5rem', paddingTop: '0.5rem', borderTop: '1px solid var(--border-default)' }}>
                  <span style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '0.2rem' }}>ZKP Commitment</span>
                  <span className="mono" style={{ fontSize: '0.65rem', wordBreak: 'break-all', color: 'var(--accent)' }}>
                    {result.privacy.zkp_commitment || 'N/A'}
                  </span>
                </div>
              </div>
            </div>
          </>
        ) : (
          <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            <span style={{ fontSize: '2rem', display: 'block', marginBottom: '1rem', opacity: 0.5 }}>✚</span>
            Run triage to see results and privacy metadata.
          </div>
        )}
      </div>
    </div>
  )
}
