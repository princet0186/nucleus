// Turns one API exchange into a privacy-log entry.
//
// The backend already attaches per-request proof metadata (`privacy` from the
// DP pipeline, `sanitization` from the egress tokenizer); this normalizes it
// into what the dashboard needs: what the user typed, what actually crossed
// the wire, which mechanisms ran, and what it cost in ε.

import { logPrivacyEvent } from "./chatStore";

export function recordExchange({ mode, original, data }) {
  const s = data?.sanitization;
  const p = data?.privacy;

  const mechanisms = [];
  if (p?.dp_mechanism === "prompt_pate") mechanisms.push("PromptPATE");
  else if (p?.dp_mechanism) mechanisms.push("Local DP");
  if (p?.pate_aggregation) mechanisms.push("PATE Ensemble");
  if (s?.applied || p?.sanitization_applied) mechanisms.push("PII Sanitization");
  if (p?.response_scrubbed) mechanisms.push("Response Scrubbing");
  if (p?.zkp_verified) mechanisms.push("ZKP Attestation");

  const ts = new Date().toISOString();
  logPrivacyEvent({
    id: `${ts}-${Math.random().toString(36).slice(2, 8)}`,
    ts,
    mode,
    original,
    // No sanitization block means the request never reached the cloud —
    // resolved on-device (map lookups, offline templates).
    egress: s?.egress_preview ?? null,
    offline: !s && !p,
    mechanisms,
    fieldsRedacted: [
      ...new Set([...(s?.fields_redacted || []), ...(p?.fields_redacted || [])]),
    ],
    fieldsGeneralized: p?.fields_generalized || [],
    epsilonSpent: p?.epsilon_spent ?? 0,
    epsilonRemaining: p?.epsilon_remaining ?? null,
  });
}
