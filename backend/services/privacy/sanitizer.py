"""Rules-based PII sanitizer with reversible tokenization.

``sanitize`` turns identifying values into indexed tokens and returns the map
needed to reverse them; ``rehydrate`` applies that map to any response
structure. Clinical content ("GSW to thigh, difficulty breathing") passes
through untouched, so answer quality is unaffected.

Rule order matters: specific patterns (grid, frequency, labeled service
numbers) must consume their digits before the generic long-digit-run rule sees
the text.
"""

import re
from dataclasses import dataclass, field

_RANKS = (
    r"Sgt|SGT|Sergeant|Cpl|Corporal|Pvt|Private|PFC|Spc|Specialist|SSG|MSG"
    r"|1SG|CSM|Lt|LT|Lieutenant|Capt|CPT|Captain|Maj|MAJ|Major|LTC|Col|COL"
    r"|Colonel|Gen|General|Doc|Medic"
)
_UNIT_TYPES = (
    r"Battalion|Brigade|Regiment|Squadron|Company|Platoon|Division|Infantry"
    r"|Cavalry|Marines|Corps|Bn|Bde|Regt|Sqn|Coy|Plt|Div"
)

# Common airframe/weapon designators that look like callsigns (UH-60, AK-47).
# Redacting these would degrade clinical/tactical answers for no privacy gain.
_CALLSIGN_EXCLUSIONS = {"uh", "ch", "ah", "mi", "an", "su", "ak", "rpg", "sa", "mk", "covid"}

# MGRS grids, in both the forms operators actually type.
#
#   compact   42SWD12345678
#   spaced    42S WD 1234 5678      <- the common hand-written form
#
# The compact rule alone left the spaced form untokenized, so a real grid
# reached the cloud verbatim. The spaced alternative closes that: it demands a
# contiguous zone+band ("42S"), valid MGRS letters (no I or O), and an
# equal-length easting/northing pair. Those three together keep military date
# groups like "3 MAY 2024" and "12 JUL 25" from being read as positions —
# the zone and band must touch, and "3 M" does not.
_GRID_COMPACT = r"\b\d{1,2}[A-Za-z]{3}\s?\d{4,10}\b"
_GRID_EN = r"(?:\d{5}\s?\d{5}|\d{4}\s?\d{4}|\d{3}\s?\d{3}|\d{2}\s?\d{2}|\d\s?\d)"
_GRID_SPACED = rf"\b\d{{1,2}}[C-HJ-NP-X]\s?[A-HJ-NP-Z]{{2}}\s?{_GRID_EN}\b"

_RULES: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("PHONE", re.compile(r"\+\d{1,3}[\s-]?\d{3,5}[\s-]?\d{3,6}\b")),
    # Spaced first: it is the longer, better-specified read. Compact runs second
    # as the permissive fallback (lowercase grids, odd digit counts, I/O letters)
    # where over-matching is harmless because rehydration restores the original.
    ("GRID", re.compile(rf"{_GRID_SPACED}|{_GRID_COMPACT}")),
    ("COORD", re.compile(r"\b-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}\b")),
    ("FREQ", re.compile(r"\b\d{1,3}(?:\.\d{1,3})?\s?(?:MHz|kHz)\b", re.IGNORECASE)),
    (
        "SN",
        re.compile(
            r"\b(?:SN|service\s+(?:no\.?|number)|serial(?:\s+(?:no\.?|number))?)"
            r"\s*[:#]?\s*\d{4,}\b",
            re.IGNORECASE,
        ),
    ),
    ("UNIT", re.compile(rf"\b\d+(?:st|nd|rd|th)?[\s-]+(?:{_UNIT_TYPES})\b", re.IGNORECASE)),
    ("NAME", re.compile(rf"\b(?:{_RANKS})\.?\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b")),
    ("CALLSIGN", re.compile(r"\b([A-Za-z]{2,})-\d{1,3}\b")),
    ("ID_NUMBER", re.compile(r"\b\d{7,}\b")),
]


@dataclass
class SanitizedText:
    text: str
    mapping: dict[str, str] = field(default_factory=dict)
    fields_redacted: list[str] = field(default_factory=list)

    @property
    def applied(self) -> bool:
        return bool(self.mapping)


def sanitize(text: str) -> SanitizedText:
    """Replace identifying values with indexed tokens like ``[GRID-1]``.

    The same value always maps to the same token within one call, so the model
    can still reason about "the casualty at [GRID-1]" consistently.
    """
    mapping: dict[str, str] = {}
    value_to_token: dict[str, str] = {}
    counters: dict[str, int] = {}

    def replace_with(label: str):
        def _replace(match: re.Match) -> str:
            value = match.group(0)
            if label == "CALLSIGN" and match.group(1).lower() in _CALLSIGN_EXCLUSIONS:
                return value
            if value in value_to_token:
                return value_to_token[value]
            counters[label] = counters.get(label, 0) + 1
            # Underscore keeps tokens inert to later rules (CALLSIGN matches
            # "word-digits", so "[NAME-1]" would be re-tokenized; "[NAME_1]" can't).
            token = f"[{label}_{counters[label]}]"
            mapping[token] = value
            value_to_token[value] = token
            return token

        return _replace

    sanitized = text
    for label, pattern in _RULES:
        sanitized = pattern.sub(replace_with(label), sanitized)

    return SanitizedText(
        text=sanitized,
        mapping=mapping,
        fields_redacted=sorted(counters.keys()),
    )


def rehydrate(value, mapping: dict[str, str]):
    """Recursively restore original values into a response structure.

    Applied on-device after the cloud round-trip, so the operator sees real
    grids/callsigns while the cloud only ever saw tokens. Models occasionally
    echo a token without its brackets ("GRID_1"), so both spellings restore.
    """
    if not mapping:
        return value
    if isinstance(value, str):
        for token, original in mapping.items():
            value = value.replace(token, original)
            bare = token.strip("[]")
            value = re.sub(rf"\b{re.escape(bare)}\b", original, value)
        return value
    if isinstance(value, dict):
        return {k: rehydrate(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [rehydrate(item, mapping) for item in value]
    return value


_PATIENT_COUNT = re.compile(
    r"\b(\d{1,3})\s*(?:x\s*)?(?:casualt|patient|wounded|injured|pax)", re.IGNORECASE
)
_LITTER_HINT = re.compile(r"\b(?:litter|stretcher|non-?ambulatory|can'?t walk)\b", re.IGNORECASE)


def extract_facts(text: str) -> dict:
    """Pull 9-line-relevant facts straight from raw text with the same rules.

    Powers the offline MEDEVAC fallback: when Gemini is unreachable, the
    deterministic template is filled from whatever the chat already contains.
    """
    grid = _RULES[2][1].search(text)
    freq = _RULES[4][1].search(text)
    count = _PATIENT_COUNT.search(text)

    callsign = None
    for match in _RULES[8][1].finditer(text):
        if match.group(1).lower() not in _CALLSIGN_EXCLUSIONS:
            callsign = match.group(0)
            break

    return {
        "grid_coordinate": grid.group(0) if grid else "UNKNOWN",
        "call_sign": callsign or "NUCLEUS-01",
        "radio_freq": freq.group(0) if freq else "UNKNOWN",
        "num_patients": int(count.group(1)) if count else 1,
        "is_litter": bool(_LITTER_HINT.search(text)),
    }
