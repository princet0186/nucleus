"""Shared strict-JSON generation helper with model routing + fallback.

Every mode-service calls ``generate_structured`` with:
  - its system prompt
  - a primary + fallback model (model routing lives in config.py)
  - a Pydantic ``response_schema`` so the model is forced into strict JSON

This is also the privacy choke point: every prompt is PII-sanitized here
before egress and the response is rehydrated after, so no endpoint can bypass
the boundary. Key rotation (rate-limit dodging) is handled by ``key_manager``.
"""

import json
from dataclasses import dataclass, field
from typing import Type

from google import genai
from pydantic import BaseModel

from backend.core.config import settings
from backend.services.Gemini_Services.key_manager import key_manager
from backend.services.privacy import rehydrate, sanitize

# Field devices need direct clinical/tactical answers — do not let the safety
# filters silently drop legitimate combat-medicine content.
_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]


_TOKEN_INSTRUCTION = (
    "\n\nSome values in the input are privacy tokens like [GRID_1] or [NAME_1]. "
    "Treat each token as the real value it stands for and copy it verbatim "
    "wherever that value belongs in your answer. Never invent replacements."
)


@dataclass
class GenerationResult:
    """Rehydrated response data plus what actually crossed the wire."""

    data: dict
    sanitization: dict = field(
        default_factory=lambda: {"applied": False, "fields_redacted": [], "egress_preview": ""}
    )


def generate_structured(
    prompt: str,
    system_prompt: str,
    primary_model: str,
    fallback_model: str,
    response_schema: Type[BaseModel],
    temperature: float = 0.3,
    sanitize_egress: bool | None = None,
) -> GenerationResult:
    """Sanitize, generate strict JSON with model fallback, rehydrate.

    Pipeline: PII -> tokens -> Gemini -> JSON -> tokens -> PII (locally).

    Model routing: try ``primary_model`` across every API key (rotating on
    rate-limit). If the primary is exhausted on ALL keys — e.g. gemini-2.5-pro
    has a hard 0 quota on the free tier — fall through to ``fallback_model``.

    ``sanitize_egress=False`` lets a caller that pre-sanitized its own prompt
    (the MEDEVAC consensus loop) skip double tokenization; the default follows
    ``settings.SANITIZE_EGRESS``.
    """
    should_sanitize = settings.SANITIZE_EGRESS if sanitize_egress is None else sanitize_egress

    mapping: dict[str, str] = {}
    sanitization = {"applied": False, "fields_redacted": [], "egress_preview": ""}
    if should_sanitize:
        result = sanitize(prompt)
        prompt, mapping = result.text, result.mapping
        sanitization = {
            "applied": result.applied,
            "fields_redacted": result.fields_redacted,
            "egress_preview": result.text[:500],
        }
        if result.applied:
            system_prompt = system_prompt + _TOKEN_INSTRUCTION

    if settings.EGRESS_DEBUG:
        print(f"[EGRESS -> GEMINI] {prompt}")

    config = {
        "system_instruction": system_prompt,
        "response_mime_type": "application/json",
        "response_schema": response_schema,
        "temperature": temperature,
        "safety_settings": _SAFETY_SETTINGS,
    }

    def _make_call(model: str):
        def _call(api_key: str) -> str:
            client = genai.Client(api_key=api_key)
            resp = client.models.generate_content(
                model=model, contents=prompt, config=config
            )
            if not resp.text:
                raise ValueError(f"{model} returned empty response")
            return resp.text

        return _call

    # Ordered, de-duplicated model chain.
    models = [m for m in dict.fromkeys([primary_model, fallback_model]) if m]

    last_error = None
    for model in models:
        try:
            raw = key_manager.execute_with_retry(_make_call(model))
            return GenerationResult(
                data=rehydrate(json.loads(raw), mapping),
                sanitization=sanitization,
            )
        except Exception as e:  # noqa: BLE001 — try the next model in the chain
            last_error = e
            print(f"[GEMINI] {model} unavailable ({str(e)[:120]}); trying next model")

    raise RuntimeError(f"All Gemini models/keys exhausted. Last error: {last_error}")
