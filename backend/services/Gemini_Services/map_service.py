"""Phrases an already-resolved offline map lookup, without leaking a position.

The lookup happened on-device (``backend.maps.resolver``). All Gemini does is
turn a fact sheet into a sentence. The fact sheet is *constructed with tokens* —
facility names are never written into the text and then substituted out, they
are simply never written at all. That removes the class of bug where replacing
"Base Hospital" also mangles "Base Hospital 12", and it means a leak would take
a code change rather than an unlucky substring.

Grids and coordinates are tokenized by the shared egress sanitizer, so the same
rules that protect every other endpoint protect this one. What crosses the wire
reads like:

    Operator question: nearest hospital to [GRID_1]
    1. [POI_1] - Hospital - GRID [GRID_2] - 4.2 km NE - source: OSM (surveyed)

Rehydration happens on-device after the round-trip. If Gemini is unreachable the
caller falls back to ``resolver.render_offline_answer``, which needs no network.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.maps.facilities import FacilityHit
from backend.maps.geo import position_label
from backend.maps.resolver import MapResolution
from backend.services.Gemini_Services.gemini_client import generate_structured
from backend.services.Gemini_Services.system_prompts import MAP_SYSTEM_PROMPT
from backend.services.privacy import rehydrate, sanitize


class MapAnswer(BaseModel):
    answer: str = Field(description="Concise field answer, nearest facility first")
    key_points: list[str] = Field(
        default_factory=list, description="Remaining facilities and caveats"
    )


# Any [LABEL_n] left after rehydration is a token with no mapping — the model
# invented it.
_RESIDUAL_TOKEN = re.compile(r"\[[A-Z][A-Z_]*_\d+\]")


class MapEgressError(RuntimeError):
    """A map prose attempt failed *after* the prompt was already transmitted.

    Carries the egress metadata so the caller can still tell the operator what
    crossed the wire. Reporting "nothing was sent" because the reply was
    discarded would be a false privacy claim, and this application exists to not
    make those.
    """

    def __init__(self, message: str, sanitization: dict) -> None:
        super().__init__(message)
        self.sanitization = sanitization


class HallucinatedFacilityError(MapEgressError):
    """The model emitted a token that maps to nothing.

    A fabricated [POI_4] is a fabricated facility. The text reads perfectly and
    points a casualty at a place the map never returned, so the answer is
    discarded whole and the caller falls back to the deterministic template.
    """


def _reject_residual_tokens(data: dict, sanitization: dict) -> None:
    body = " ".join([data.get("answer", ""), *(data.get("key_points") or [])])
    stray = sorted(set(_RESIDUAL_TOKEN.findall(body)))
    if stray:
        raise HallucinatedFacilityError(
            f"model emitted unmapped token(s) {stray}; discarding answer", sanitization
        )


def _facility_line(index: int, token: str, hit: FacilityHit) -> str:
    """One fact-sheet row.

    The operator's own note is deliberately NOT included. It is free text they
    wrote about their own operating area ("tarmac, marked with green smoke",
    "cache behind the treeline") — the single most sensitive string in the
    payload, and the reason operator pins are encrypted at rest at all. Sending
    it to a cloud model to make a sentence prettier would give away exactly what
    the encryption was protecting. The note is already in the map payload, so
    the medic reads it on-device; the model only learns that one exists.
    """
    facility = hit.facility
    # Flag the operator's own marks distinctly. They are deliberate — the operator
    # put them on the map — so a good answer should call them out ("a place you
    # marked"), not bury them among surveyed results.
    source = (
        "OSM (surveyed)"
        if facility.verified
        else "MARKED BY THE OPERATOR (their own annotation, UNVERIFIED)"
    )
    line = (
        f"{index}. {token} - {facility.label} - {position_label(hit.grid)} {hit.grid} - "
        f"{hit.distance_km:.1f} km {hit.compass} - source: {source}"
    )
    if facility.note:
        line += " - the operator attached a note (shown to them on-device)"
    return line


def _build_fact_sheet(query: str, resolution: MapResolution) -> tuple[str, dict[str, str]]:
    """Compose the prompt with POI tokens already in place.

    Returns (text, poi_mapping). Grids inside ``text`` are still real; the
    sanitizer tokenizes them on the next step, exactly as it does for every
    other endpoint.
    """
    poi_mapping: dict[str, str] = {}
    lines: list[str] = [f"Operator question: {query}", "", "Facilities resolved on-device:"]

    for index, hit in enumerate(resolution.hits, start=1):
        token = f"[POI_{index}]"
        poi_mapping[token] = hit.facility.name
        lines.append(_facility_line(index, token, hit))

    route = resolution.route
    if route:
        lines.append("")
        kind = "straight-line (no road network, NO travel time available)" if route.is_straight_line else route.provider
        lines.append(
            f"Route to nearest: {route.distance_km:.1f} km, "
            f"bearing {route.bearing_deg:.0f} ({route.compass}), {kind}."
        )

    if resolution.warning:
        lines.append("")
        lines.append(f"Caveat: {resolution.warning}")

    return "\n".join(lines), poi_mapping


def generate_map_answer(
    query: str,
    resolution: MapResolution,
    on_egress: Optional[Callable[[dict], None]] = None,
) -> dict:
    """Ask Gemini to phrase the resolved lookup. Raises on failure — callers fall back.

    Never called when the resolution has no facilities: there would be nothing to
    phrase, and asking a model to narrate an empty list invites it to fill one in.

    ``on_egress`` fires with the sanitization metadata immediately *before* the
    prompt is transmitted. A caller that abandons this call on a deadline has
    still emitted, and needs to be able to say so.

    Raises ``HallucinatedFacilityError`` if the model referenced a facility that
    was not on the fact sheet.
    """
    if not resolution.hits:
        raise ValueError("generate_map_answer requires at least one facility")

    text, poi_mapping = _build_fact_sheet(query, resolution)

    mapping: dict[str, str] = dict(poi_mapping)
    sanitization = {"applied": False, "fields_redacted": [], "egress_preview": ""}

    if settings.SANITIZE_EGRESS:
        clean = sanitize(text)
        text = clean.text
        mapping.update(clean.mapping)
        sanitization = {
            "applied": True,  # POI tokens are always applied, even with no grid match
            "fields_redacted": sorted({*clean.fields_redacted, "POI"}),
            "egress_preview": clean.text[:500],
        }
    else:
        sanitization["egress_preview"] = text[:500]

    # Past this line the prompt is on the wire. Every failure from here on must
    # still surface `sanitization`, so wrap them in MapEgressError — and tell the
    # caller now, in case it abandons us on a deadline and never sees a return.
    if on_egress:
        on_egress(sanitization)

    try:
        result = generate_structured(
            prompt=text,
            system_prompt=MAP_SYSTEM_PROMPT,
            primary_model=settings.GEMINI_GENERAL_MODEL,
            fallback_model=settings.GEMINI_GENERAL_FALLBACK,
            response_schema=MapAnswer,
            temperature=0.2,  # phrasing, not invention
            sanitize_egress=False,  # already tokenized above, including POI names
        )
    except Exception as exc:  # noqa: BLE001 — transport, quota, schema, refusal
        raise MapEgressError(str(exc), sanitization) from exc

    data = rehydrate(result.data, mapping)
    _reject_residual_tokens(data, sanitization)

    return {
        "answer": data.get("answer", ""),
        "key_points": data.get("key_points", []) or [],
        "sanitization": sanitization,
    }
