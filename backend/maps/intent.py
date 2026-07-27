"""Local map-intent detection. Rules only, zero egress.

When an operator asks "what's the nearest evacuation centre", the chat needs to
open the map sidebar. Deciding that with the cloud model is not an option: the
question carries a position, and the egress sanitizer tokenizes every grid
before a prompt leaves. Gemini would receive "nearest evac to [GRID_1]" and
could not resolve it even if it wanted to. So detection happens here, on-device,
against the offline index — which is also why it works with the radio off.

The rule is a conjunction: a *proximity* cue AND a *facility* cue. Either alone
is a false positive waiting to happen.

    "where is the entry wound"              proximity, no facility  -> no map
    "treating a hospital-acquired infection"  facility, no proximity -> no map
    "where is the nearest hospital"          both                   -> map

Explicit cues ("show me on the map") open the map with no facility filter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from backend.maps.facility import (
    AIRFIELD, CASUALTY_COLLECTION_POINT, CLINIC, DOCTORS, EVAC_POINT, FIRE_STATION,
    FUEL, GROUPS, HELIPAD, HOSPITAL, OSM_KINDS, PHARMACY, POLICE, SHELTER,
    WATER_POINT, group_of, resolve_kinds,
)
from backend.maps.geo import find_grid, parse_position

# Wanting to know where something is, or how to get to it.
_PROXIMITY = re.compile(
    r"\b("
    r"nearest|closest|nearby|near\s?by|near\s+me|around\s+me|"
    r"how\s+far|how\s+close|distance\s+to|far\s+is|"
    r"where\s+is|where'?s|where\s+are|locate|find\s+me|"
    r"route\s+to|directions?|navigate|way\s+to|get\s+to|take\s+me|head\s+to|"
    r"evacuate\s+to|move\s+to|casevac\s+to|medevac\s+to"
    r")\b",
    re.IGNORECASE,
)

# Explicit: open the map regardless of whether a facility was named.
_EXPLICIT_MAP = re.compile(
    r"\b(on\s+the\s+map|open\s+the\s+map|show\s+(?:me\s+)?(?:the\s+)?map|map\s+of|show\s+on\s+map)\b",
    re.IGNORECASE,
)

# Asking for a path, not just a position.
_ROUTE = re.compile(
    r"\b(route|directions?|navigate|way\s+to|get\s+to|take\s+me|how\s+do\s+i\s+reach|head\s+to)\b",
    re.IGNORECASE,
)

# Facility cues -> concrete kinds, or the name of a whole group.
#
# Every cue that matches is collected, then specific kinds beat umbrella groups
# (see ``_facility_targets``): "nearest evacuation centre" trips both the
# evac_point cue and the broad "evacuation" cue, and the operator asked for the
# former. Multi-word cues are listed before their own substrings so the longer
# phrase is what gets reported in ``matched``.
_FACILITY_CUES: tuple[tuple[str, str], ...] = (
    (r"casualty\s+collection(?:\s+point)?|\bccp\b", CASUALTY_COLLECTION_POINT),
    (r"evacuation\s+(?:cent(?:re|er)|point|site|zone)|evac\s+(?:cent(?:re|er)|point|site|zone)", EVAC_POINT),
    (r"landing\s+(?:zone|site|point)|\bhlz\b|\blz\b|helipad|heliport|\bheli\b", HELIPAD),
    (r"airfield|airstrip|aerodrome|runway|airport", AIRFIELD),
    # "casualty collection" belongs to the CCP cue above; repeating it here made
    # one phrase claim two operator-only kinds and widen into two whole groups.
    (r"aid\s+station|field\s+hospital|role\s*[1-4]\b", "aid_station"),
    (r"hospital|trauma\s+cent(?:re|er)|emergency\s+room|\ber\b|casualty\s+department", HOSPITAL),
    (r"clinic|health\s+cent(?:re|er)|dispensary", CLINIC),
    (r"pharmac(?:y|ies)|chemist|drugstore", PHARMACY),
    (r"doctor'?s?\b|surgery\b|physician", DOCTORS),
    (r"fire\s+station|fire\s+brigade", FIRE_STATION),
    (r"police\s+(?:station|post)|\bpolice\b", POLICE),
    (r"shelter|refuge|bunker", SHELTER),
    (r"water\s+(?:point|source)|drinking\s+water|potable\s+water", WATER_POINT),
    (r"fuel|petrol|diesel|gas\s+station|refuel", FUEL),
    # Umbrella terms resolve to whole groups.
    (r"medical\s+(?:facility|facilities|help|care|support)|medical\b|treatment\s+facility", "medical"),
    (r"evacuation|evac\b|medevac|casevac", "evac"),
)

_FACILITY_PATTERNS: tuple[tuple[re.Pattern, str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), target) for pattern, target in _FACILITY_CUES
)


@dataclass
class MapIntent:
    """What the operator's question asks of the map."""

    is_map_query: bool
    kinds: tuple[str, ...] = ()
    wants_route: bool = False
    origin: Optional[tuple[float, float]] = None
    # The grid exactly as the operator wrote it, so it can be echoed back rather
    # than re-derived from lat/lon (which changes the string). "" when the
    # position came from coordinates.
    origin_grid: str = ""
    confidence: float = 0.0
    matched: list[str] = field(default_factory=list)

    @property
    def needs_origin(self) -> bool:
        return self.is_map_query and self.origin is None


def _facility_targets(text: str) -> tuple[list[str], list[str]]:
    """Facility cues present, as (targets, matched phrases).

    Specific kinds normally suppress umbrella groups: ask for a hospital and you
    should not also get every helipad in range, because the bare word
    "evacuation" happened to appear in the sentence.

    The exception is a kind OpenStreetMap cannot express. "Evacuation point",
    "casualty collection point" and "aid station" are operator-only kinds — no
    OSM tag produces them — so narrowing to them alone returns nothing but the
    operator's own pins, and returns *nothing at all* on a fresh device. A medic
    asking for the nearest evacuation point while standing 400 m from a surveyed
    helipad must not be told there is nothing nearby. When none of the requested
    kinds can exist in the map data, widen to their category so surveyed
    alternatives surface; the operator's pins rank inside it either way.
    """
    targets: list[str] = []
    matched: list[str] = []
    for pattern, target in _FACILITY_PATTERNS:
        found = pattern.search(text)
        if found:
            targets.append(target)
            matched.append(found.group(0).strip())

    specific = [target for target in targets if target not in GROUPS]
    if not specific:
        return targets, matched

    if any(kind in OSM_KINDS for kind in specific):
        return specific, matched

    widened = list(specific)
    widened.extend(group for kind in specific if (group := group_of(kind)))
    return widened, matched


def _find_origin(text: str, context: str) -> tuple[Optional[tuple[float, float]], str]:
    """Position and its literal grid string, preferring the question over history.

    The operator may be planning for a grid they are not standing on, so a
    position in the live question always beats one recovered from the chat log.
    """
    for source in (text, context):
        position = parse_position(source)
        if position is not None:
            return position, find_grid(source) or ""
    return None, ""


def detect(query: str, context: str = "") -> MapIntent:
    """Classify a chat turn. Never raises; an unparseable query is simply not a map query.

    ``context`` is searched for a position only. Facility and proximity cues must
    come from the live question, or every turn after "where's the nearest
    hospital" would keep re-opening the map.
    """
    text = query or ""
    if not text.strip():
        return MapIntent(is_map_query=False)

    proximity = _PROXIMITY.search(text)
    explicit = _EXPLICIT_MAP.search(text)
    targets, matched_facilities = _facility_targets(text)

    has_facility = bool(targets)
    if not (explicit or (proximity and has_facility)):
        return MapIntent(is_map_query=False)

    origin, origin_grid = _find_origin(text, context or "")

    matched: list[str] = list(matched_facilities)
    if proximity:
        matched.append(proximity.group(0).strip())
    if explicit:
        matched.append(explicit.group(0).strip())

    if proximity and has_facility:
        confidence = 0.95
    elif explicit and has_facility:
        confidence = 0.9
    else:  # explicit map cue, no facility named
        confidence = 0.6

    return MapIntent(
        is_map_query=True,
        kinds=resolve_kinds(targets),
        wants_route=bool(_ROUTE.search(text)),
        origin=origin,
        origin_grid=origin_grid,
        confidence=confidence,
        matched=matched,
    )
