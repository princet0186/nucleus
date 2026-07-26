"""AI MEDEVAC generation with PATE-style consensus voting.

The 9-line is life-safety output, so a single sample is not trusted. We draw
``MEDEVAC_CONSENSUS_SAMPLES`` independent generations and vote field-by-field:
majority value wins; fields where every sample disagrees are reported as
disputed so the operator verifies them before transmitting.

The chat context is sanitized once here (not per-sample), all samples see the
same tokens, and the winning result is rehydrated once at the end — real
grids/callsigns only ever exist on-device.
"""

from collections import Counter

from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.services.Gemini_Services.gemini_client import generate_structured
from backend.services.Gemini_Services.system_prompts import MEDEVAC_SYSTEM_PROMPT
from backend.services.privacy import rehydrate, sanitize

NINE_LINE_FIELDS = [f"line_{i}" for i in range(1, 10)]


class MedevacNineLine(BaseModel):
    line_1: str = ""
    line_2: str = ""
    line_3: str = ""
    line_4: str = ""
    line_5: str = ""
    line_6: str = ""
    line_7: str = ""
    line_8: str = ""
    line_9: str = ""


class MedevacDraft(BaseModel):
    nine_line: MedevacNineLine = Field(default_factory=MedevacNineLine)
    precedence: str = ""
    narrative: str = ""


def generate_medevac_consensus(context: str) -> dict:
    """Generate a 9-line + narrative from chat context, consensus-voted.

    Returns the voted nine_line/precedence/narrative plus a ``consensus``
    report and the ``sanitization`` metadata for the UI privacy panel.
    """
    sanitization = {"applied": False, "fields_redacted": [], "egress_preview": ""}
    mapping: dict[str, str] = {}
    if settings.SANITIZE_EGRESS:
        clean = sanitize(context)
        context, mapping = clean.text, clean.mapping
        sanitization = {
            "applied": clean.applied,
            "fields_redacted": clean.fields_redacted,
            "egress_preview": clean.text[:500],
        }

    samples = []
    for _ in range(max(1, settings.MEDEVAC_CONSENSUS_SAMPLES)):
        result = generate_structured(
            prompt=f"Field context for MEDEVAC request:\n{context}",
            system_prompt=MEDEVAC_SYSTEM_PROMPT,
            primary_model=settings.GEMINI_PLANNING_MODEL,
            fallback_model=settings.GEMINI_PLANNING_FALLBACK,
            response_schema=MedevacDraft,
            temperature=0.4,
            sanitize_egress=False,
        )
        samples.append(result.data)

    voted, disputed = _vote(samples)
    voted = rehydrate(voted, mapping)

    total_fields = len(NINE_LINE_FIELDS) + 1
    return {
        **voted,
        "consensus": {
            "samples": len(samples),
            "disputed_fields": disputed,
            "agreement": round(1 - len(disputed) / total_fields, 2),
        },
        "sanitization": sanitization,
    }


def _vote(samples: list[dict]) -> tuple[dict, list[str]]:
    """Majority-vote each 9-line field and precedence across samples.

    A field is disputed when no value reaches a majority; the first sample's
    value is kept as the working draft but the field is flagged for manual
    verification.
    """
    majority = len(samples) // 2 + 1
    disputed: list[str] = []

    def elect(field_name: str, values: list[str]) -> str:
        normalized = [" ".join(v.lower().split()) for v in values]
        winner, count = Counter(normalized).most_common(1)[0]
        if count < majority:
            disputed.append(field_name)
            return values[0]
        return values[normalized.index(winner)]

    nine_line = {
        f: elect(f, [s.get("nine_line", {}).get(f, "") for s in samples])
        for f in NINE_LINE_FIELDS
    }
    precedence = elect("precedence", [s.get("precedence", "") for s in samples])
    narrative = max((s.get("narrative", "") for s in samples), key=len)

    return (
        {"nine_line": nine_line, "precedence": precedence, "narrative": narrative},
        disputed,
    )
