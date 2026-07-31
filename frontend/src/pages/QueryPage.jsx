import { useState, useRef, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import "./QueryPage.css";
import MapPanel from "../components/MapPanel";
import Logo from "../components/Logo";
import {
  listThreads,
  loadThread,
  saveThread,
  getCachedResponse,
  putCachedResponse,
  softWipe,
  hardWipe,
} from "../lib/chatStore";
import { indexMessage, retrieveContext } from "../lib/contextIndex";
import { recordExchange } from "../lib/privacyLog";

// The operator's position is remembered across reloads so manual testing (and a
// real patrol) does not retype a grid on every question. It never leaves the
// device: it is sent to the local backend, which resolves the map on-device and
// tokenizes the grid before any prompt reaches the cloud.
const ORIGIN_KEY = "nucleus.origin";

// The bottom dock selects the mode via ?mode=. Triage and Mass Casualty open
// as sectioned forms — each heading is a prompt for a detail that would
// otherwise slip the operator's mind — then the conversation continues as
// free-text follow-ups.
const MODES = {
  general: {
    name: "General Query",
    followUp: "Ask a tactical, medical, or operational question…",
    form: null,
  },
  triage: {
    name: "Triage",
    followUp: "Ask a follow-up — clarify findings, request next steps…",
    form: {
      intro: "Fill in what you know — every field sharpens the triage. Skip what you can't see.",
      fields: [
        { key: "mechanism", label: "Mechanism of injury", hint: "How were they hurt — blast, gunshot, vehicle, fall…" },
        { key: "injuries", label: "Injuries seen", hint: "Wounds, bleeding, burns, deformity — head to toe" },
        { key: "vitals", label: "Vital signs", hint: "Pulse, breathing, consciousness (AVPU), skin colour" },
        { key: "treatment", label: "Treatment given", hint: "Tourniquet, airway, dressings, drugs already administered" },
        { key: "demographics", label: "Age / sex", hint: "Approximate age and sex, if known" },
      ],
    },
  },
  mascal: {
    name: "Mass Casualty",
    followUp: "Ask a follow-up — update counts, request a revised plan…",
    form: {
      intro: "Paint the full picture — the plan is only as good as what you report.",
      fields: [
        { key: "incident", label: "What happened", hint: "IED, collapse, ambush, crash — when and where" },
        { key: "count", label: "Casualty count", hint: "How many casualties, roughly, and how they're distributed" },
        { key: "worst", label: "Worst injuries", hint: "The most severe presentations you can see" },
        { key: "hazards", label: "Active hazards", hint: "Fire, secondary devices, unstable structures, contamination" },
        { key: "resources", label: "Resources on hand", hint: "Personnel, medical supplies, vehicles, comms" },
      ],
    },
  },
};

export default function QueryPage() {
  const [searchParams] = useSearchParams();
  const modeDef = MODES[searchParams.get("mode")] || MODES.general;
  const mode = modeDef.name;

  const [query, setQuery] = useState("");
  const [formValues, setFormValues] = useState({});
  const [formOpen, setFormOpen] = useState(true);
  const [loading, setLoading] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [threadId, setThreadId] = useState(null);
  const [threads, setThreads] = useState([]);
  const [origin, setOrigin] = useState(() => localStorage.getItem(ORIGIN_KEY) || "");
  const [mapPayload, setMapPayload] = useState(null);
  const [mapOpen, setMapOpen] = useState(false);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    localStorage.setItem(ORIGIN_KEY, origin);
  }, [origin]);

  // The app-wide VaultGate guarantees the key is in memory before this page
  // mounts, so past threads can be listed straight away. The page opens on the
  // Recents view: resume a thread, or just start typing for a new one.
  useEffect(() => {
    let active = true;
    listThreads().then((t) => {
      if (active) setThreads(t);
    });
    return () => {
      active = false;
    };
  }, []);

  // Persist the active thread whenever it changes.
  useEffect(() => {
    if (threadId && conversations.length) saveThread(threadId, conversations);
  }, [conversations, threadId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [conversations]);

  // Switching sections resets the form draft; the form starts open only while
  // the chat is empty — once a conversation is running, follow-ups are text.
  useEffect(() => {
    setFormValues({});
    setFormOpen(conversations.length === 0);
    if (inputRef.current) inputRef.current.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, threadId]);

  // Grow the free-text composer with its content.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 150)}px`;
  }, [query]);

  const autoGrow = (e) => {
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
  };

  const ensureThreadId = () => {
    if (threadId) return threadId;
    const id = crypto.randomUUID();
    setThreadId(id);
    return id;
  };

  const handleResume = async (id) => {
    const messages = await loadThread(id);
    setThreadId(id);
    setConversations(messages);
    setFormOpen(false);
  };

  const handleNewChat = async () => {
    setThreadId(null);
    setConversations([]);
    setQuery("");
    setFormValues({});
    setFormOpen(true);
    setMapOpen(false);
    setMapPayload(null);
    setThreads(await listThreads());
  };

  // One pipeline for both composers: free text and the sectioned form.
  const submitContent = async (content) => {
    const submittedQuery = content.trim();
    if (!submittedQuery || loading) return;
    const tid = ensureThreadId();

    const userMessage = {
      role: "user",
      content: submittedQuery,
      mode: mode,
      timestamp: new Date().toISOString(),
    };
    setConversations((prev) => [...prev, userMessage]);
    indexMessage({
      id: `${userMessage.timestamp}-user`,
      threadId: tid,
      role: "user",
      content: submittedQuery,
    });

    // Serve identical (mode + query) from the on-device cache — no API call.
    // Map answers are never cached (see below), so a cache hit can never be a
    // stale facility list from a different position.
    const cached = await getCachedResponse(mode, submittedQuery);
    if (cached) {
      setConversations((prev) => [...prev, { ...cached, cached: true }]);
      if (cached.map) {
        setMapPayload(cached.map);
        setMapOpen(true);
      }
      return;
    }

    setLoading(true);

    try {
      let endpoint = "/nucleus/query";
      let body = {};

      // The operator's position rides along on every mode. It stays on-device —
      // the backend only uses it if the model decides a map would help, and it
      // is tokenized before any prompt reaches the cloud.
      const originValue = origin.trim() || null;
      if (mode === "General Query") {
        endpoint = "/nucleus/query";
        body = { query: submittedQuery, origin: originValue };
      } else if (mode === "Triage") {
        endpoint = "/nucleus/triage";
        body = {
          injury_description: submittedQuery,
          patient_demographics: null,
          origin: originValue,
        };
      } else if (mode === "Mass Casualty") {
        endpoint = "/nucleus/mascal";
        body = { query: submittedQuery, origin: originValue };
      }

      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "Request failed");
      }

      const data = await response.json();
      let aiResponseContent = "";
      let triageData = null;

      if (mode === "Triage" && data.triage_result) {
        triageData = data.triage_result;
        aiResponseContent = `**Triage Category:** ${triageData.triage_category}\n\n**Reasoning:** ${triageData.confidence_reasoning}`;
        if (triageData.treatment_protocol) {
          const tp = triageData.treatment_protocol;
          if (tp.priority) aiResponseContent += `\n\n**Priority:** ${tp.priority}`;
          if (tp.immediate_actions?.length > 0) {
            aiResponseContent += `\n\n**Immediate Actions:**\n${tp.immediate_actions.map((a) => `- ${a}`).join("\n")}`;
          }
          if (tp.evacuation) aiResponseContent += `\n\n**Evacuation:** ${tp.evacuation}`;
        }
        if (triageData.recommended_drugs?.length > 0) {
          aiResponseContent += `\n\n**Recommended Drugs:** ${triageData.recommended_drugs.join(", ")}`;
        }
        if (triageData.warnings?.length > 0) {
          aiResponseContent += `\n\n**⚠ Warnings:**\n${triageData.warnings.map((w) => `- ${w}`).join("\n")}`;
        }
      } else {
        aiResponseContent = data.response || data.raw_response || "No response received.";
      }

      const aiMessage = {
        role: "ai",
        content: aiResponseContent,
        timestamp: data.timestamp,
        cached: false,
        privacy: data.privacy,
        sanitization: data.sanitization,
        query_id: data.query_id,
        map: data.map || null,
      };
      setConversations((prev) => [...prev, aiMessage]);

      // Feed the privacy dashboard: what was typed vs. what actually egressed.
      recordExchange({ mode, original: submittedQuery, data });

      // The backend answered with a map: open the sidebar on it.
      if (data.map) {
        setMapPayload(data.map);
        setMapOpen(true);
      }

      // Cache so an identical (mode + query) is served locally next time —
      // EXCEPT map answers. The cache key is (mode, query) and carries no
      // origin, so a cached "nearest hospital" would be replayed verbatim after
      // the operator has moved, pointing them at a facility near where they
      // used to be. Recomputing a local lookup is free; being wrong is not.
      if (!data.map) putCachedResponse(mode, submittedQuery, aiMessage);
      indexMessage({
        id: `${aiMessage.timestamp}-ai`,
        threadId: tid,
        role: "ai",
        content: aiResponseContent,
      });
    } catch (err) {
      setConversations((prev) => [
        ...prev,
        { role: "error", content: err.message, timestamp: new Date().toISOString() },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!query.trim()) return;
    setQuery("");
    submitContent(query);
  };

  // The sectioned form folds into one labelled report — headings included, so
  // the model (and the transcript) keeps the structure.
  const handleFormSubmit = (e) => {
    e.preventDefault();
    const lines = modeDef.form.fields
      .map((f) => ({ label: f.label, value: (formValues[f.key] || "").trim() }))
      .filter((x) => x.value)
      .map((x) => `${x.label}: ${x.value}`);
    if (!lines.length) return;
    setFormValues({});
    setFormOpen(false);
    submitContent(lines.join("\n"));
  };

  const handleSoftWipe = async () => {
    await softWipe();
    setThreadId(null);
    setConversations([]);
    setQuery("");
    setThreads([]);
    setFormOpen(true);
  };

  const handleHardWipe = async () => {
    const confirmed = window.confirm(
      "HARD WIPE (crypto-erase): destroys the encryption key. " +
        "All stored data becomes permanently unrecoverable. Continue?"
    );
    if (!confirmed) return;
    await hardWipe();
    window.location.reload();
  };

  // The chat is the source of truth: retrieve the most evacuation-relevant
  // slice from the local encrypted index and let the backend turn it into a
  // consensus-voted 9-line (offline template if the cloud is unreachable).
  const handleGenerateMedevac = async () => {
    if (loading) return;
    setConversations((prev) => [
      ...prev,
      {
        role: "user",
        content: "Generate Medical Evacuation — retrieving relevant context from this chat...",
        mode: "MEDEVAC",
        timestamp: new Date().toISOString(),
      },
    ]);
    setLoading(true);

    try {
      const context = threadId ? await retrieveContext(threadId) : "";
      if (!context) {
        throw new Error(
          "No chat context to build a MEDEVAC from. Describe the casualty situation first."
        );
      }
      const response = await fetch("/nucleus/medevac/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ context, origin: origin.trim() || null }),
      });
      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || "MEDEVAC generation failed");
      }
      const data = await response.json();
      recordExchange({ mode: "MEDEVAC", original: context, data });

      const sourceLabel =
        data.source === "gemini_consensus"
          ? `AI consensus — ${data.consensus.samples} samples, ${Math.round(data.consensus.agreement * 100)}% agreement`
          : "Offline template (no cloud reachable)";
      let content = `**9-Line MEDEVAC** · ${sourceLabel}\n\n\`\`\`\n${data.radio_format}\n\`\`\``;
      if (data.narrative) content += `\n\n**Narrative:** ${data.narrative}`;
      const disputed = data.consensus?.disputed_fields ?? [];
      if (disputed.length > 0) {
        content += `\n\n**⚠ VERIFY MANUALLY:** samples disagreed on ${disputed.join(", ")}`;
      }

      setConversations((prev) => [
        ...prev,
        {
          role: "ai",
          content,
          timestamp: data.generated_at,
          sanitization: data.sanitization,
          map: data.map || null,
        },
      ]);
      // The casualty and nearest evac facilities came back with the 9-line.
      if (data.map) {
        setMapPayload(data.map);
        setMapOpen(true);
      }
    } catch (err) {
      setConversations((prev) => [
        ...prev,
        { role: "error", content: err.message, timestamp: new Date().toISOString() },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const activeTitle = conversations.find((m) => m.role === "user")?.content || "";

  const formatWhen = (iso) => {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  };

  // Format AI response content with basic markdown-like rendering
  const renderFormattedContent = (text) => {
    if (!text) return null;
    const lines = text.split("\n");
    const elements = [];
    let inCodeBlock = false;
    let codeLines = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      if (line.startsWith("```")) {
        if (inCodeBlock) {
          elements.push(
            <pre key={`code-${i}`} className="code-block">
              <code>{codeLines.join("\n")}</code>
            </pre>
          );
          codeLines = [];
          inCodeBlock = false;
        } else {
          inCodeBlock = true;
        }
        continue;
      }

      if (inCodeBlock) {
        codeLines.push(line);
        continue;
      }

      if (line.trim() === "") {
        elements.push(<div key={`space-${i}`} className="line-spacer" />);
        continue;
      }

      // Bold: **text**
      const parts = [];
      const boldRegex = /\*\*(.*?)\*\*/g;
      let lastIndex = 0;
      let match;
      while ((match = boldRegex.exec(line)) !== null) {
        if (match.index > lastIndex) {
          parts.push(<span key={`t-${i}-${lastIndex}`}>{line.slice(lastIndex, match.index)}</span>);
        }
        parts.push(<strong key={`b-${i}-${match.index}`}>{match[1]}</strong>);
        lastIndex = match.index + match[0].length;
      }
      if (lastIndex < line.length) {
        parts.push(<span key={`t-${i}-${lastIndex}`}>{line.slice(lastIndex)}</span>);
      }
      if (parts.length === 0) parts.push(line);

      // Bullets
      if (line.startsWith("- ") || line.startsWith("• ")) {
        elements.push(
          <div key={`li-${i}`} className="fmt-bullet">
            <span className="bullet-dot">›</span>
            <span>{parts.length > 0 ? parts.map((p, idx) => {
              if (typeof p === 'string') {
                const cleaned = p.replace(/^[-•]\s*/, '');
                return <span key={idx}>{cleaned}</span>;
              }
              return p;
            }) : line.replace(/^[-•]\s*/, '')}</span>
          </div>
        );
      } else if (line.startsWith("# ")) {
        elements.push(<h3 key={`h-${i}`} className="fmt-heading">{line.slice(2)}</h3>);
      } else if (line.startsWith("## ")) {
        elements.push(<h4 key={`h-${i}`} className="fmt-subheading">{line.slice(3)}</h4>);
      } else {
        elements.push(<p key={`p-${i}`} className="fmt-para">{parts}</p>);
      }
    }

    if (inCodeBlock && codeLines.length > 0) {
      elements.push(
        <pre key="code-end" className="code-block">
          <code>{codeLines.join("\n")}</code>
        </pre>
      );
    }

    return elements;
  };

  const renderPrivacyPanel = (privacy) => {
    if (!privacy) return null;
    const mechanism = privacy.dp_mechanism;
    return (
      <div className="privacy-panel">
        <div className="privacy-panel-header">
          <span className="privacy-panel-title">Privacy Metadata</span>
          {mechanism && (
            <span className={`dp-badge ${mechanism === 'prompt_pate' ? 'pate' : 'local'}`}>
              {mechanism === 'prompt_pate' ? 'PromptPATE' : 'Local DP'}
            </span>
          )}
        </div>
        <div className="privacy-grid">
          {privacy.sanitization_applied && (
            <div className="privacy-chip green">✓ Sanitized</div>
          )}
          {privacy.pate_aggregation && (
            <div className="privacy-chip blue">✓ PATE Ensemble</div>
          )}
          {privacy.response_scrubbed && (
            <div className="privacy-chip orange">✓ Scrubbed</div>
          )}
          {privacy.zkp_verified && (
            <div className="privacy-chip purple">✓ ZKP</div>
          )}
        </div>
        <div className="privacy-details">
          {privacy.pate_aggregation && (
            <>
              <div className="privacy-detail-row">
                <span className="detail-label">PATE Consensus</span>
                <span className="detail-value">{(privacy.pate_consensus * 100).toFixed(0)}%</span>
              </div>
              <div className="privacy-detail-row">
                <span className="detail-label">Teachers Voted</span>
                <span className="detail-value">{privacy.pate_teachers_voted}/8</span>
              </div>
            </>
          )}
          <div className="privacy-detail-row">
            <span className="detail-label">ε Spent</span>
            <span className="detail-value mono">{privacy.epsilon_spent?.toFixed(4)}</span>
          </div>
          <div className="privacy-detail-row">
            <span className="detail-label">ε Remaining</span>
            <span className="detail-value mono">{privacy.epsilon_remaining?.toFixed(2)}</span>
          </div>
          {privacy.fields_redacted?.length > 0 && (
            <div className="privacy-detail-row">
              <span className="detail-label">Redacted</span>
              <span className="detail-value">{privacy.fields_redacted.join(", ")}</span>
            </div>
          )}
          {privacy.fields_generalized?.length > 0 && (
            <div className="privacy-detail-row">
              <span className="detail-label">Generalized</span>
              <span className="detail-value">{privacy.fields_generalized.join(", ")}</span>
            </div>
          )}
        </div>
      </div>
    );
  };

  // Proof-of-redaction: shows which identifier classes were tokenized before
  // egress and the exact text that crossed the wire.
  const renderSanitizationPanel = (s) => (
    <div className="sanitize-panel">
      <div className="sanitize-header">
        <span className="sanitize-title">🛡 Egress Sanitized</span>
        {s.fields_redacted.map((f) => (
          <span key={f} className="sanitize-chip">{f}</span>
        ))}
      </div>
      <details className="sanitize-preview">
        <summary>What actually left this device</summary>
        <pre>{s.egress_preview}</pre>
      </details>
    </div>
  );

  const getModeBadgeClass = (m) => {
    if (m === "Triage") return "mode-badge triage";
    if (m === "Mass Casualty") return "mode-badge mascal";
    if (m === "MEDEVAC") return "mode-badge medevac";
    return "mode-badge general";
  };

  const showOnMap = (payload) => {
    setMapPayload(payload);
    setMapOpen(true);
  };

  const showForm = modeDef.form && formOpen;
  const subject = mode === "Triage" ? "casualty" : "incident";
  const landingHint = modeDef.form
    ? `Report the ${subject} below  then keep asking in the same chat.`
    : "Ask about tactics, field medicine, or operations.";

  return (
    <div className="query-page-layout">
      <div className="query-main-content">
        {/* Active thread strip — title of the running chat + escape hatch */}
        {conversations.length > 0 && (
          <div className="thread-bar">
            <span className="thread-title">{activeTitle}</span>
            <button className="new-chat-btn" onClick={handleNewChat}>
              ＋ New chat
            </button>
          </div>
        )}

        {/* Conversation area — scrolls; composer stays pinned below it */}
        <div className="conversation-area" ref={scrollRef}>
          {conversations.length === 0 && (
            <div className="landing">
              <div className="empty-state">
                <Logo className="empty-logo" />
                <p>{landingHint}</p>
              </div>

              {threads.length > 0 && (
                <div className="recents">
                  <div className="recents-header">
                    <span className="recents-title">Recent chats</span>
                  </div>
                  {threads.map((t) => (
                    <button key={t.id} className="recent-item" onClick={() => handleResume(t.id)}>
                      <span className="recent-glyph">✎</span>
                      <span className="recent-title">{t.title}</span>
                      <span className="recent-meta">
                        {formatWhen(t.updatedAt)} · {t.count} msgs
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          {conversations.map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              <div className="message-header">
                <span className="message-role">
                  {msg.role === "user" ? "You" : msg.role === "error" ? "Error" : "Nucleus"}
                </span>
                {msg.mode && <span className={getModeBadgeClass(msg.mode)}>{msg.mode}</span>}
                {msg.cached && <span className="cache-badge">⚡ CACHED</span>}
              </div>
              <div className="message-body">
                {msg.role === "ai" ? (
                  renderFormattedContent(msg.content)
                ) : (
                  <p className="user-text">{msg.content}</p>
                )}
              </div>
              {msg.map && (
                <button className="map-reopen-btn" onClick={() => showOnMap(msg.map)}>
                  ◎ Show on map
                  {msg.map.facilities?.length > 0 && (
                    <span className="map-reopen-count">{msg.map.facilities.length}</span>
                  )}
                </button>
              )}
              {/* A map answer with no `sanitization` never touched the network. */}
              {msg.map && !msg.sanitization && (
                <div className="offline-badge">
                  🔒 Resolved on-device — nothing transmitted
                </div>
              )}
              {msg.sanitization?.applied && renderSanitizationPanel(msg.sanitization)}
              {msg.privacy && renderPrivacyPanel(msg.privacy)}
            </div>
          ))}
          {loading && (
            <div className="message ai loading-msg">
              <div className="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
          )}
        </div>

        {/* Composer pinned above the dock: sectioned form or free-text chat */}
        <div className="composer">
          {showForm ? (
            <form onSubmit={handleFormSubmit} className="section-form">
              <div className="section-form-intro">{modeDef.form.intro}</div>
              {modeDef.form.fields.map((f) => (
                <label key={f.key} className="section-field">
                  <span className="section-field-label">{f.label}</span>
                  <textarea
                    rows={1}
                    className="section-field-input"
                    placeholder={f.hint}
                    value={formValues[f.key] || ""}
                    onChange={(e) =>
                      setFormValues((prev) => ({ ...prev, [f.key]: e.target.value }))
                    }
                    onInput={autoGrow}
                    disabled={loading}
                  />
                </label>
              ))}
              <div className="section-form-actions">
                {conversations.length > 0 && (
                  <button type="button" className="composer-switch" onClick={() => setFormOpen(false)}>
                    ← Back to chat
                  </button>
                )}
                <button
                  type="submit"
                  className="section-form-submit"
                  disabled={
                    loading ||
                    !modeDef.form.fields.some((f) => (formValues[f.key] || "").trim())
                  }
                >
                  {mode === "Triage" ? "Run Triage" : "Build Response Plan"}
                </button>
              </div>
            </form>
          ) : (
            <>
              <form onSubmit={handleSubmit} className="search-form">
                <textarea
                  ref={inputRef}
                  rows={1}
                  placeholder={modeDef.followUp}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      handleSubmit(e);
                    }
                  }}
                  disabled={loading}
                  className="main-search-input"
                />
                <button type="submit" className="search-submit-btn" disabled={loading || !query.trim()}>
                  {loading ? "..." : "→"}
                </button>
              </form>
              {modeDef.form && (
                <button type="button" className="composer-switch" onClick={() => setFormOpen(true)}>
                  ▤ Report another {subject} with the form
                </button>
              )}
            </>
          )}
        </div>
      </div>

      <div className="query-right-sidebar">
        <label className="origin-field">
          <span className="origin-label">Your position</span>
          <input
            className="origin-input"
            placeholder="42S WD 1234 5678"
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
            spellCheck={false}
          />
          <span className="origin-hint">
            MGRS grid or <code>lat, lon</code>. Used to answer “nearest…” questions locally.
          </span>
        </label>

        <button className="sidebar-action-btn primary" onClick={handleGenerateMedevac}>
          Generate Medical Evacuation
        </button>
        <button
          className={`sidebar-action-btn ${mapOpen ? "active" : ""}`}
          onClick={() => setMapOpen((open) => !open)}
        >
          {mapOpen ? "Hide Map" : "Open Map"}
        </button>
        <button className="sidebar-action-btn danger" onClick={handleSoftWipe}>
          Soft Wipe (Clear Data)
        </button>
        <button className="sidebar-action-btn danger" onClick={handleHardWipe}>
          Hard Wipe (Crypto-Erase)
        </button>
      </div>

      {mapOpen && <MapPanel payload={mapPayload} onClose={() => setMapOpen(false)} />}
    </div>
  );
}
