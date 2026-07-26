import asyncio
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.api.routes.maps import compose_chat_answer
from backend.maps import resolver as map_resolver
from backend.maps.geo import GridError, parse_position
from backend.models.map_schemas import MapPayload
from backend.services.Gemini_Services.key_manager import key_manager
from backend.services.Gemini_Services import (
    general_service,
    triage_service,
    mascal_service,
    medevac_service,
)
from backend.services.medevac_generator import format_for_radio, generate_medevac_request
from backend.services.privacy import extract_facts
from backend.models.schemas import (
    NucleusQueryRequest,
    NucleusQueryResponse,
    TriageRequest,
    TriageResponse,
    TriageResult,
    TreatmentProtocol,
    MedevacRequest,
    MedevacResponse,
    MedevacGenerateRequest,
    MedevacAIResponse,
    SanitizationMetadata,
)

router = APIRouter(prefix="/nucleus", tags=["Nucleus AI"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_ai() -> None:
    if not key_manager.is_ready:
        raise HTTPException(
            status_code=503,
            detail="Nucleus AI not initialized. Add GEMINI_API_KEY (or GEMINI_API_KEY_1..) to .env",
        )


# Sensible default when Gemini asks for a map but names no facility categories —
# this is a combat-medical app, so bias to the things that keep people alive.
_ASSIST_DEFAULT_KINDS = ("medical", "evac")


def _map_from_assist(data: dict, origin: str | None) -> MapPayload | None:
    """Turn Gemini's map_assist decision into a map payload, resolved on-device.

    Gemini judged (from tokenized text) whether a map helps and which facilities
    to show. Here the device does the geo-resolution the cloud never can, using
    the operator's real position. Returns None when Gemini declined the map.

    A malformed origin is not fatal to the primary answer: the map still opens in
    ``needs_origin`` mode so the operator can supply a good grid, rather than
    500ing a triage result over a typo.
    """
    assist = data.get("map_assist") or {}
    if not assist.get("should_open"):
        return None

    kwargs = dict(
        facility_kinds=assist.get("facility_kinds") or [],
        wants_route=bool(assist.get("wants_route")),
        default_kinds=_ASSIST_DEFAULT_KINDS,
        reason=assist.get("reason", ""),
    )
    try:
        resolution = map_resolver.resolve_suggestion(origin=origin, **kwargs)
    except GridError:
        resolution = map_resolver.resolve_suggestion(origin=None, **kwargs)

    return MapPayload(**resolution.to_payload())


async def _try_map_query(request: NucleusQueryRequest) -> NucleusQueryResponse | None:
    """Answer from the offline map layer, or return None if this is not a map question.

    Detection is a local regex over the question — no egress, no API key, and no
    round-trip before we know whether a map is even involved.
    """
    try:
        resolution = await asyncio.to_thread(
            map_resolver.resolve, request.query, request.context or "", request.origin
        )
    except GridError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if resolution is None:
        return None

    composed = await compose_chat_answer(request.query, resolution)

    return NucleusQueryResponse(
        query_id=str(uuid.uuid4()),
        mode="map",
        response=composed.answer,
        timestamp=_now(),
        cached=False,
        map=resolution.to_payload(),
        # None on the offline template path: nothing crossed the boundary at all.
        sanitization=composed.sanitization,
    )


# ---------------------------------------------------------------------------
# General tactical query -> instant model, or the offline map layer
# ---------------------------------------------------------------------------
@router.post("/query", response_model=NucleusQueryResponse)
async def general_query(request: NucleusQueryRequest):
    """Answer a chat turn. Questions that need a map are answered from local data.

    The map branch runs *before* the API-key check on purpose. "Where is the
    nearest evacuation centre" is resolved from the offline OSM index and the
    operator's own pins; a device with no key, no signal, and the radio off must
    still answer it. Gemini is invited afterwards only to phrase the result, and
    only ever sees tokenized facts.
    """
    map_response = await _try_map_query(request)
    if map_response is not None:
        return map_response

    _require_ai()
    try:
        result = await asyncio.to_thread(
            general_service.generate_general, request.query, request.context
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Gemini error: {e}")

    response = result.data.get("answer", "")
    key_points = result.data.get("key_points") or []
    if key_points:
        response += "\n\n" + "\n".join(f"- {p}" for p in key_points)

    # Gemini decides, from the tokenized question, whether a map would help. The
    # actual facilities are resolved on-device from the operator's own position.
    map_payload = await asyncio.to_thread(_map_from_assist, result.data, request.origin)

    return NucleusQueryResponse(
        query_id=str(uuid.uuid4()),
        mode="general",
        response=response,
        timestamp=_now(),
        cached=False,
        map=map_payload,
        sanitization=SanitizationMetadata(**result.sanitization),
    )


# ---------------------------------------------------------------------------
# Individual TCCC triage -> planning model
# ---------------------------------------------------------------------------
@router.post("/triage", response_model=TriageResponse)
async def medical_triage(request: TriageRequest):
    _require_ai()
    try:
        result = await asyncio.to_thread(
            triage_service.generate_triage,
            request.injury_description,
            request.patient_demographics,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Gemini error: {e}")

    data = result.data
    protocol = data.get("treatment_protocol", {}) or {}
    triage_result = TriageResult(
        triage_category=data.get("triage_category", ""),
        confidence_reasoning=data.get("confidence_reasoning", ""),
        treatment_protocol=TreatmentProtocol(
            priority=protocol.get("priority", ""),
            immediate_actions=protocol.get("immediate_actions", []),
            evacuation=protocol.get("evacuation", ""),
        ),
        recommended_drugs=data.get("recommended_drugs", []),
        warnings=data.get("warnings", []),
    )

    # A T1 needing surgical care in 60 minutes is a map question the operator did
    # not think to ask. Gemini flags it; the device finds the nearest care.
    map_payload = await asyncio.to_thread(_map_from_assist, data, request.origin)

    return TriageResponse(
        query_id=str(uuid.uuid4()),
        mode="triage",
        triage_result=triage_result,
        timestamp=_now(),
        map=map_payload,
        sanitization=SanitizationMetadata(**result.sanitization),
    )


# ---------------------------------------------------------------------------
# Mass casualty -> planning model (prioritization guidance, no identity tracking)
# ---------------------------------------------------------------------------
@router.post("/mascal", response_model=NucleusQueryResponse)
async def mass_casualty(request: NucleusQueryRequest):
    _require_ai()
    try:
        result = await asyncio.to_thread(mascal_service.generate_mascal, request.query)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Gemini error: {e}")

    # A mass-casualty event is where staging hospitals, helipads and collection
    # points on a map matters most; Gemini decides, the device plots.
    map_payload = await asyncio.to_thread(_map_from_assist, result.data, request.origin)

    return NucleusQueryResponse(
        query_id=str(uuid.uuid4()),
        mode="mascal",
        response=_format_mascal(result.data),
        timestamp=_now(),
        cached=False,
        map=map_payload,
        sanitization=SanitizationMetadata(**result.sanitization),
    )


def _format_mascal(data: dict) -> str:
    parts = []
    if data.get("situation_summary"):
        parts.append(f"**Situation:** {data['situation_summary']}")

    priorities = data.get("triage_priorities") or []
    if priorities:
        rows = [
            f"- **{p.get('category', '?')}** ({p.get('estimated_count', 'unknown')}): {p.get('action', '')}"
            for p in priorities
        ]
        parts.append("**Triage Priorities:**\n" + "\n".join(rows))

    if data.get("immediate_actions"):
        parts.append(
            "**Immediate Actions:**\n"
            + "\n".join(f"- {a}" for a in data["immediate_actions"])
        )
    if data.get("resource_allocation"):
        parts.append(
            "**Resource Allocation:**\n"
            + "\n".join(f"- {r}" for r in data["resource_allocation"])
        )
    if data.get("evacuation_priority"):
        parts.append(f"**Evacuation Priority:** {data['evacuation_priority']}")

    return "\n\n".join(parts) if parts else "No guidance generated."


# ---------------------------------------------------------------------------
# MEDEVAC from chat context -> consensus-voted AI, offline template fallback
# ---------------------------------------------------------------------------
_TRIAGE_HINT = re.compile(r"\bT([1-4])\b")
_TRIAGE_BY_NUMBER = {
    "1": "T1-IMMEDIATE",
    "2": "T2-DELAYED",
    "3": "T3-MINIMAL",
    "4": "T4-EXPECTANT",
}


def _medevac_map(context: str, origin: str | None) -> MapPayload | None:
    """Plot the casualty and the nearest evacuation facilities.

    A MEDEVAC is inherently a map question — the 9-line names a pickup location
    and the operator has to get the patient somewhere. So this does not ask
    Gemini: it takes the casualty position (supplied by the operator, or lifted
    straight from the chat) and resolves the nearest helipads, evac points and
    surgical care locally. The position may be an MGRS grid OR decimal
    coordinates, so both are parsed. No position, no map — silently.
    """
    casualty_origin: str | tuple[float, float] | None = origin
    if not casualty_origin:
        casualty_origin = parse_position(context)  # grid or lat/lon from the chat
    if not casualty_origin:
        return None
    try:
        resolution = map_resolver.resolve_suggestion(
            facility_kinds=["evac", "medical"],
            wants_route=True,
            origin=casualty_origin,
            default_kinds=("evac", "medical"),
            reason="MEDEVAC destination",
        )
    except GridError:
        return None
    if resolution.needs_origin:
        return None
    return MapPayload(**resolution.to_payload())


@router.post("/medevac/generate", response_model=MedevacAIResponse)
async def generate_medevac_from_context(request: MedevacGenerateRequest):
    """Turn concentrated chat context into a 9-line + narrative.

    AI path: sanitized egress, PATE-style consensus voting, local rehydration.
    If Gemini is unreachable (no internet / keys exhausted), falls back to the
    deterministic offline template filled with facts extracted from the chat.

    Either way the casualty and nearest evac facilities are plotted on-device.
    """
    casualty_map = await asyncio.to_thread(_medevac_map, request.context, request.origin)
    try:
        voted = await asyncio.to_thread(
            medevac_service.generate_medevac_consensus, request.context
        )
        return MedevacAIResponse(
            request_id=f"MEDEVAC-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            generated_at=_now(),
            source="gemini_consensus",
            nine_line=voted["nine_line"],
            precedence=voted["precedence"],
            narrative=voted["narrative"],
            radio_format=format_for_radio(voted["nine_line"], voted["precedence"]),
            consensus=voted["consensus"],
            sanitization=voted["sanitization"],
            map=casualty_map,
        )
    except Exception as e:  # noqa: BLE001 — offline path must always produce a 9-line
        print(f"[MEDEVAC] AI path unavailable ({str(e)[:120]}); using offline template")
        return _offline_medevac(request.context, casualty_map)


def _offline_medevac(context: str, casualty_map: MapPayload | None = None) -> MedevacAIResponse:
    facts = extract_facts(context)
    hint = _TRIAGE_HINT.search(context)
    # Unknown severity is treated as T1: over-triage is the safe failure mode.
    triage_category = _TRIAGE_BY_NUMBER.get(hint.group(1)) if hint else "T1-IMMEDIATE"

    generated = generate_medevac_request(triage_category=triage_category, **facts)
    return MedevacAIResponse(
        request_id=generated["request_id"],
        generated_at=generated["generated_at"],
        source="offline_template",
        nine_line=generated["nine_line"],
        precedence=generated["precedence"],
        narrative="Offline template: fields extracted locally from chat. Verify before transmitting.",
        radio_format=generated["radio_format"],
        map=casualty_map,
    )


# ---------------------------------------------------------------------------
# Manual MEDEVAC form -> deterministic offline generator (kept alongside)
# ---------------------------------------------------------------------------
@router.post("/medevac", response_model=MedevacResponse)
async def generate_medevac(request: MedevacRequest):
    return generate_medevac_request(
        triage_category=request.triage_category,
        grid_coordinate=request.grid_coordinate,
        call_sign=request.call_sign,
        radio_freq=request.radio_freq,
        num_patients=request.num_patients,
        is_litter=request.is_litter,
        security=request.security,
        marking=request.marking,
        nationality=request.nationality,
        cbrn=request.cbrn,
    )
