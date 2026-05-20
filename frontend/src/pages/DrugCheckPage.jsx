import { useState } from 'react'

export default function DrugCheckPage() {
  const [administerInput, setAdministerInput] = useState('')
  const [givenInput, setGivenInput] = useState('')
  const [contextInput, setContextInput] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleCheck = async () => {
    if (!administerInput.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const payload = {
        drugs_to_administer: administerInput.split(',').map(s => s.trim()).filter(Boolean),
        drugs_already_given: givenInput.split(',').map(s => s.trim()).filter(Boolean),
        patient_context: contextInput.trim() || undefined,
      }

      const res = await fetch('/nucleus/drug-check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error('Drug check failed. Ensure Gemini API key is set.')
      const data = await res.json()
      setResult(data)
    } catch (e) {
      setError(e.message)
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
          <h1 style={{ fontSize: '1.4rem', marginBottom: '0.25rem' }}>Playground: Drug Formulary</h1>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            Gemini 3.0 Pro Pharmacological Analysis with DP Privacy Pipeline.
          </p>
        </div>

        <div className="card" style={{ display: 'flex', flexDirection: 'column', flex: 1, padding: '1.5rem', gap: '1.5rem', background: 'var(--bg-deep)' }}>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Drugs to Administer (comma separated)
            </label>
            <input
              type="text"
              className="input"
              value={administerInput}
              onChange={e => setAdministerInput(e.target.value)}
              placeholder="e.g., Ketamine, Morphine"
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Drugs Already Given (comma separated)
            </label>
            <input
              type="text"
              className="input"
              value={givenInput}
              onChange={e => setGivenInput(e.target.value)}
              placeholder="e.g., TXA"
            />
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', flex: 1 }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
              Patient Context (Optional)
            </label>
            <textarea
              className="input"
              value={contextInput}
              onChange={e => setContextInput(e.target.value)}
              placeholder="e.g., Patient is in hemorrhagic shock..."
              style={{ flex: 1, resize: 'none' }}
              onKeyDown={e => { if (e.key === 'Enter' && e.metaKey) handleCheck() }}
            />
          </div>

          <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: '1rem', borderTop: '1px solid var(--border-default)' }}>
            <button 
              className="btn btn-primary" 
              onClick={handleCheck} 
              disabled={loading || !administerInput.trim()}
              style={{ padding: '0.5rem 1.5rem', borderRadius: 'var(--radius-full)' }}
            >
              {loading ? <div className="spinner" style={{ width: '16px', height: '16px', borderWidth: '2px' }} /> : 'Analyze Interactions ⌘↵'}
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
          Analysis Result
        </h3>
        
        {result ? (
          <>
            {result.drug_analysis ? (
              <div className="card slide-up" style={{ padding: '1.25rem', borderColor: result.drug_analysis.safe_to_administer ? 'var(--success)' : 'var(--danger)', boxShadow: `0 0 20px ${result.drug_analysis.safe_to_administer ? 'rgba(129, 201, 149, 0.1)' : 'rgba(242, 139, 130, 0.1)'}` }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
                  <div className={`status-dot ${result.drug_analysis.safe_to_administer ? 'online' : 'offline'}`} />
                  <span style={{ fontSize: '0.9rem', fontWeight: 600, color: result.drug_analysis.safe_to_administer ? 'var(--success)' : 'var(--danger)' }}>
                    {result.drug_analysis.safe_to_administer ? 'SAFE TO ADMINISTER' : 'CONTRAINDICATED'}
                  </span>
                </div>
                
                <p style={{ fontSize: '0.9rem', color: 'var(--text-primary)', marginBottom: '1.5rem', lineHeight: 1.5 }}>
                  {result.drug_analysis.overall_recommendation}
                </p>

                {result.drug_analysis.interactions?.length > 0 && (
                  <div style={{ marginBottom: '1rem' }}>
                    <h4 style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>Interactions Detected</h4>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                      {result.drug_analysis.interactions.map((inter, i) => (
                        <div key={i} style={{ padding: '0.75rem', background: 'var(--bg-deep)', borderRadius: 'var(--radius-sm)', borderLeft: `3px solid ${inter.severity === 'HIGH' ? 'var(--danger)' : 'var(--warning)'}` }}>
                          <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.25rem', color: 'var(--text-primary)' }}>{inter.drug_pair}</div>
                          <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{inter.warning}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="card slide-up" style={{ padding: '1rem', color: 'var(--warning)' }}>
                ⚠ Could not parse structured drug data. See raw response.
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
              </div>
            </div>
          </>
        ) : (
          <div className="card" style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
            <span style={{ fontSize: '2rem', display: 'block', marginBottom: '1rem', opacity: 0.5 }}>⚕</span>
            Analyze interactions to see results.
          </div>
        )}
      </div>
    </div>
  )
}
