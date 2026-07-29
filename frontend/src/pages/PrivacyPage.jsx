import { useEffect, useState } from "react";
import { listPrivacyEvents } from "../lib/chatStore";
import "./PrivacyPage.css";

// The privacy ledger: one row per exchange, straight from the encrypted
// on-device log. For every prompt it shows the operator's original text, the
// sanitized text that actually reached the cloud LLM, the mechanisms that
// stood between the two, and the differential-privacy cost.

const MECHANISM_HINTS = {
  PromptPATE: "8 teacher prompts vote; only the noisy consensus label leaves",
  "Local DP": "calibrated noise added on-device before egress",
  "PATE Ensemble": "answer aggregated across an ensemble, not one model call",
  "PII Sanitization": "names, grids, callsigns tokenized before egress",
  "Response Scrubbing": "identifiers stripped from the model's reply",
  "ZKP Attestation": "commitment proves sanitization ran, without revealing the input",
};

export default function PrivacyPage() {
  const [events, setEvents] = useState(null);

  useEffect(() => {
    let active = true;
    listPrivacyEvents().then((e) => {
      if (active) setEvents(e);
    });
    return () => {
      active = false;
    };
  }, []);

  if (events === null) {
    return (
      <div className="privacy-page">
        <div className="spinner" style={{ margin: "4rem auto" }} />
      </div>
    );
  }

  const cloud = events.filter((e) => !e.offline);
  const onDevice = events.filter((e) => e.offline);
  const spentTotal = events.reduce((sum, e) => sum + (e.epsilonSpent || 0), 0);
  const latestWithBudget = events.find((e) => e.epsilonRemaining != null);
  const remaining = latestWithBudget?.epsilonRemaining ?? null;
  const budgetFraction =
    remaining != null && remaining + spentTotal > 0
      ? remaining / (remaining + spentTotal)
      : null;
  const redactionCount = events.reduce((sum, e) => sum + (e.fieldsRedacted?.length || 0), 0);

  const formatTime = (iso) => {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="privacy-page fade-in">
      <div className="privacy-page-header">
        <h1>Privacy Dashboard</h1>
        
      </div>

      <div className="privacy-stats">
        <div className="stat-tile">
          <span className="stat-label">ε budget remaining</span>
          <span className="stat-value mono">
            {remaining != null ? remaining.toFixed(2) : "—"}
          </span>
          {budgetFraction != null && (
            <div className="budget-bar">
              <div
                className={`budget-bar-fill ${budgetFraction < 0.25 ? "low" : ""}`}
                style={{ width: `${Math.round(budgetFraction * 100)}%` }}
              />
            </div>
          )}
          <span className="stat-foot">
            ε ${spentTotal.toFixed(3)} spent across logged exchanges
          </span>
        </div>
        <div className="stat-tile">
          <span className="stat-label">Exchanges logged</span>
          <span className="stat-value mono">{events.length}</span>
          
        </div>
        <div className="stat-tile">
          <span className="stat-label">Identifiers protected</span>
          <span className="stat-value mono">{redactionCount}</span>
          
        </div>
      </div>

      {events.length === 0 ? (
        <div className="privacy-empty">
          Nothing logged yet
        </div>
      ) : (
        <div className="privacy-log">
          <div className="privacy-log-title">Egress log — newest first</div>
          {events.map((e) => (
            <div key={e.id} className="log-entry">
              <div className="log-entry-header">
                <span className="log-mode">{e.mode}</span>
                <span className="log-time">{formatTime(e.ts)}</span>
                {e.epsilonSpent > 0 && (
                  <span className="log-epsilon mono">ε +{e.epsilonSpent.toFixed(4)}</span>
                )}
              </div>

              {e.mechanisms?.length > 0 && (
                <div className="log-mechanisms">
                  {e.mechanisms.map((m) => (
                    <span key={m} className="mechanism-chip" title={MECHANISM_HINTS[m] || ""}>
                      {m}
                    </span>
                  ))}
                </div>
              )}

              <div className="log-compare">
                <div className="log-col">
                  <span className="log-col-title you">You typed</span>
                  <pre className="log-text">{e.original}</pre>
                </div>
                <div className="log-arrow">→</div>
                <div className="log-col">
                  <span className="log-col-title cloud">
                    {e.offline ? "Never left the device" : "Reached the cloud"}
                  </span>
                  {e.offline ? (
                    <div className="log-offline">
                      🔒 Resolved on-device — no request was transmitted
                    </div>
                  ) : (
                    <pre className="log-text egress">
                      {e.egress || "(sanitized preview not reported for this exchange)"}
                    </pre>
                  )}
                </div>
              </div>

              {(e.fieldsRedacted?.length > 0 || e.fieldsGeneralized?.length > 0) && (
                <div className="log-fields">
                  {e.fieldsRedacted?.map((f) => (
                    <span key={`r-${f}`} className="field-tag redacted">⌫ {f}</span>
                  ))}
                  {e.fieldsGeneralized?.map((f) => (
                    <span key={`g-${f}`} className="field-tag generalized">≈ {f}</span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
