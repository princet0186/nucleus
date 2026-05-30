import { useState, useRef, useEffect } from 'react'
import './QueryPage.css'

export default function QueryPage() {
  const [query, setQuery] = useState('')
  const [context, setContext] = useState('')
  const [showContext, setShowContext] = useState(false)
  const [loading, setLoading] = useState(false)
  const [conversations, setConversations] = useState([])
  const scrollRef = useRef(null)

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [conversations])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!query.trim() || loading) return

    const userMessage = { role: 'user', content: query, timestamp: new Date().toISOString() }
    setConversations(prev => [...prev, userMessage])
    setQuery('')
    setLoading(true)

    try {
      const body = { query: query.trim() }
      if (context.trim()) body.context = context.trim()

      const response = await fetch('/nucleus/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!response.ok) {
        const err = await response.json()
        throw new Error(err.detail || 'Request failed')
      }

      const data = await response.json()
      const aiMessage = {
        role: 'ai',
        content: data.response,
        timestamp: data.timestamp,
        cached: data.cached,
        privacy: data.privacy,
        query_id: data.query_id,
      }
      setConversations(prev => [...prev, aiMessage])
    } catch (err) {
      setConversations(prev => [...prev, {
        role: 'error',
        content: err.message,
        timestamp: new Date().toISOString(),
      }])
    } finally {
      setLoading(false)
    }
  }

  const quickQueries = [
    "How to apply a chest seal for open pneumothorax?",
    "Tourniquet application steps under fire",
    "Signs of tension pneumothorax in the field",
    "TCCC phases overview",
    "Needle decompression procedure",
  ]

  return (
    <div className="query-page">
      {/* Conversation Area */}
      <div className="conversation-area" ref={scrollRef}>
        {conversations.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">✦</div>
            <h2>Nucleus Tactical Query</h2>
            <p>Ask any military, tactical, or medical question. Your input is sanitized through a privacy pipeline before reaching the AI.</p>
            <div className="quick-queries">
              {quickQueries.map((q, i) => (
                <button key={i} className="quick-btn" onClick={() => setQuery(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          conversations.map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              <div className="message-header">
                <span className="message-role">
                  {msg.role === 'user' ? '🔒 You' : msg.role === 'error' ? '⚠ Error' : '✦ Nucleus AI'}
                </span>
                {msg.cached && <span className="cache-badge">⚡ CACHED</span>}
                {msg.privacy?.response_scrubbed && <span className="scrub-badge">🛡 SCRUBBED</span>}
              </div>
              <div className="message-body">
                {msg.content.split('\n').map((line, j) => {
                  if (line.startsWith('⚠')) return <p key={j} className="critical-line">{line}</p>
                  if (line.startsWith('⚡')) return <p key={j} className="takeaway-line">{line}</p>
                  if (line.startsWith('- ') || line.startsWith('• ')) return <p key={j} className="bullet-line">{line}</p>
                  return <p key={j}>{line}</p>
                })}
              </div>
              {msg.privacy && (
                <div className="privacy-footer">
                  <div className="privacy-pills">
                    {msg.privacy.sanitization_applied && (
                      <span className="pill pill-green">✓ Input Sanitized</span>
                    )}
                    {msg.privacy.differential_privacy_noise && (
                      <span className="pill pill-blue">✓ DP Noise Added</span>
                    )}
                    {msg.privacy.zkp_verified && (
                      <span className="pill pill-purple">✓ ZKP Verified</span>
                    )}
                    {msg.privacy.response_scrubbed && (
                      <span className="pill pill-orange">✓ Response Scrubbed</span>
                    )}
                    {msg.cached && (
                      <span className="pill pill-cyan">✓ Zero API Exposure</span>
                    )}
                  </div>
                  <div className="privacy-details">
                    {msg.privacy.fields_generalized?.length > 0 && (
                      <span className="detail-item">Generalized: {msg.privacy.fields_generalized.join(', ')}</span>
                    )}
                    {msg.privacy.fields_redacted?.length > 0 && (
                      <span className="detail-item">Redacted: {msg.privacy.fields_redacted.join(', ')}</span>
                    )}
                    <span className="detail-item">ε spent: {msg.privacy.epsilon_spent?.toFixed(3)} | remaining: {msg.privacy.epsilon_remaining?.toFixed(1)}</span>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
        {loading && (
          <div className="message ai loading-msg">
            <div className="message-header">
              <span className="message-role">✦ Nucleus AI</span>
            </div>
            <div className="message-body">
              <div className="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="input-area">
        {showContext && (
          <div className="context-bar">
            <textarea
              className="context-input"
              placeholder="Additional context (situation, environment, constraints)..."
              value={context}
              onChange={(e) => setContext(e.target.value)}
              rows={2}
            />
          </div>
        )}
        <form className="query-form" onSubmit={handleSubmit}>
          <button
            type="button"
            className={`context-toggle ${showContext ? 'active' : ''}`}
            onClick={() => setShowContext(!showContext)}
            title="Add context"
          >
            +
          </button>
          <input
            type="text"
            className="query-input"
            placeholder="Ask a tactical, medical, or operational question..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={loading}
          />
          <button type="submit" className="send-btn" disabled={loading || !query.trim()}>
            {loading ? '...' : '→'}
          </button>
        </form>
        <div className="input-footer">
          <span>🔒 Input generalized + DP noise → ZKP committed → Response scrubbed</span>
        </div>
      </div>
    </div>
  )
}
