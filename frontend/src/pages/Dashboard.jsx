import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

export default function Dashboard() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    fetch('/health')
      .then(r => r.json())
      .then(data => { setStatus(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const modules = [
    {
      id: 'triage',
      title: 'MASCAL Triage',
      description: 'AI-powered NATO T1–T4 casualty classification with TCCC treatment protocols.',
      icon: '✛',
      path: '/triage',
    },
    {
      id: 'drugs',
      title: 'Drug Formulary',
      description: 'Battlefield medication interaction checker against TCCC drug guidelines.',
      icon: '⚕',
      path: '/drugs',
    },
    {
      id: 'medevac',
      title: '9-Line MEDEVAC',
      description: 'Auto-generated NATO-standard evacuation requests from triage data.',
      icon: '⬡',
      path: '/medevac',
    }
  ]

  if (loading) {
    return (
      <div className="page-wrapper" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
        <div className="spinner" />
      </div>
    )
  }

  return (
    <div className="page-wrapper fade-in" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '80vh', textAlign: 'center' }}>
      <div style={{ marginBottom: '4rem', maxWidth: '800px' }}>
        <h1 style={{ fontSize: '3rem', fontWeight: 400, marginBottom: '1rem', background: 'linear-gradient(90deg, #e3e3e3, #8ab4f8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
          Nucleus AI (Gemini 3.0 Pro)
        </h1>
        <p style={{ fontSize: '1.1rem', color: 'var(--text-secondary)' }}>
          Define the next generation of professional tactical and medical field intelligence. Secure, encrypted, and offline-capable.
        </p>
      </div>

      <div className="grid grid-3" style={{ maxWidth: '1000px', width: '100%', textAlign: 'left' }}>
        {modules.map((mod, i) => (
          <div
            key={mod.id}
            className="card slide-up"
            style={{ animationDelay: `${i * 0.1}s`, cursor: 'pointer', position: 'relative', overflow: 'hidden' }}
            onClick={() => mod.path && navigate(mod.path)}
          >
            <div style={{ fontSize: '2rem', color: 'var(--accent)', marginBottom: '1rem' }}>
              {mod.icon}
            </div>
            <h3 style={{ marginBottom: '0.5rem', fontWeight: 500 }}>{mod.title}</h3>
            <p style={{ fontSize: '0.9rem', lineHeight: 1.5, color: 'var(--text-secondary)' }}>{mod.description}</p>
            
            {/* Subtle glow effect on hover */}
            <div className="card-glow" />
          </div>
        ))}
      </div>
    </div>
  )
}
