"""Nucleus Gemini service layer.

Direct, privacy-unwired Gemini pipeline. Each field mode lives in its own file:
    general_service  -> fast instant model  (general tactical query)
    triage_service   -> planning model      (individual TCCC triage)
    mascal_service   -> planning model      (mass-casualty prioritization guidance)
    medevac_service  -> planning model      (9-line + narrative, optional AI path)

Shared plumbing:
    key_manager      -> rotates across many API keys to dodge rate limits
    gemini_client    -> strict-JSON structured generation with model fallback
    system_prompts   -> system prompts for every mode

NOTE: The differential-privacy / PATE / ZKP layer is intentionally NOT wired in
here yet. Once the raw pipeline returns clean responses, the DP layer will wrap
the input/output of these calls (sanitize-in, scrub-out).
"""
