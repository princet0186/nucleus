"""Turns a chat question into a map payload, entirely on-device.

This is the orchestration the cloud model cannot do:

    intent (local regex)
      -> origin (grid in the question, or supplied by the caller)
      -> facilities (offline R*Tree + encrypted operator pins)
      -> route (straight-line today; road routing behind the same seam)
      -> payload for the map sidebar

``needs_origin`` is a first-class outcome, not an error. "Where's the nearest
hospital" is a perfectly good question that the device cannot answer until it
knows where the operator is standing. The frontend prompts for a grid (or, once
live tracking lands, supplies a GPS fix) and asks again.

``render_offline_answer`` produces the prose when ``MAPS_AI_PROSE`` is off or
Gemini is unreachable. It is a template, so it is stiff — and it is the only
path that works with the radio off, which is the path that has to work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from backend.core.config import settings
from backend.maps import catalog, facilities as facility_search
from backend.maps.facilities import FacilityHit
from backend.maps.geo import (
    GridError,
    find_grid,
    format_position,
    parse_position,
    position_label,
)
from backend.maps.facility import resolve_kinds
from backend.maps.intent import MapIntent, detect
from backend.maps.routing import Route, get_provider

# An origin that is nowhere near the installed region means the operator typed
# the wrong grid, or the wrong region is installed. Either way, silently
# returning "no facilities within 25 km" hides the real problem.
_OUT_OF_BOUNDS_MARGIN_DEG = 1.0


@dataclass
class MapResolution:
    """Everything the map sidebar needs, and everything the prose layer needs."""

    intent: MapIntent
    region: Optional[str] = None
    origin: Optional[tuple[float, float]] = None
    # The operator's own grid string, echoed rather than re-derived. See
    # ``geo.format_position`` for why re-encoding would be a bug.
    origin_grid: str = ""
    hits: list[FacilityHit] = field(default_factory=list)
    route: Optional[Route] = None
    needs_origin: bool = False
    warning: str = ""

    @property
    def nearest(self) -> Optional[FacilityHit]:
        return self.hits[0] if self.hits else None

    @property
    def origin_label(self) -> str:
        """How the origin should be shown: the operator's grid, or a derived one."""
        if self.origin_grid:
            return self.origin_grid
        if self.origin:
            return format_position(*self.origin)
        return ""

    def to_payload(self) -> dict:
        """The JSON the frontend uses to open and populate the map sidebar."""
        origin_payload = None
        if self.origin:
            lat, lon = self.origin
            origin_payload = {"lat": lat, "lon": lon, "grid": self.origin_label}

        return {
            "open_map": True,
            "needs_origin": self.needs_origin,
            "region": self.region,
            "origin": origin_payload,
            "kinds": list(self.intent.kinds),
            "wants_route": self.intent.wants_route,
            "confidence": self.intent.confidence,
            "matched": self.intent.matched,
            "facilities": [hit.to_dict() for hit in self.hits],
            "route": self.route.to_dict() if self.route else None,
            "warning": self.warning,
        }


def _resolve_origin(
    origin: Optional[str | tuple[float, float]],
    intent: MapIntent,
) -> tuple[Optional[tuple[float, float]], str]:
    """(position, literal grid) — caller's origin wins over the one in the question."""
    if isinstance(origin, tuple):
        return origin, ""
    if isinstance(origin, str) and origin.strip():
        parsed = parse_position(origin)
        if parsed is None:
            raise GridError(f"Could not read a position from {origin!r}")
        return parsed, find_grid(origin) or ""
    return intent.origin, intent.origin_grid


def _out_of_region(region: Optional[str], lat: float, lon: float) -> bool:
    if not region:
        return False
    try:
        west, south, east, north = catalog.get_tiles(region).bounds
    except Exception:  # noqa: BLE001 — a broken region should not block a search
        return False
    margin = _OUT_OF_BOUNDS_MARGIN_DEG
    return not (
        south - margin <= lat <= north + margin and west - margin <= lon <= east + margin
    )


def resolve(
    query: str,
    context: str = "",
    origin: Optional[str | tuple[float, float]] = None,
    region: Optional[str] = None,
    radius_km: Optional[float] = None,
    limit: Optional[int] = None,
) -> Optional[MapResolution]:
    """Resolve a chat turn into a map payload, or None when it is not a map query.

    Detection is a local regex — no egress, no API key. This is the offline
    fast-path for explicit questions ("nearest hospital"). Semantic intent that
    the regex cannot see is handled by ``resolve_suggestion`` from Gemini's
    judgement instead.
    """
    intent = detect(query, context)
    if not intent.is_map_query:
        return None
    return _resolve_with_intent(intent, origin, region, radius_km, limit)


def resolve_suggestion(
    facility_kinds: list[str],
    wants_route: bool = False,
    origin: Optional[str | tuple[float, float]] = None,
    region: Optional[str] = None,
    radius_km: Optional[float] = None,
    limit: Optional[int] = None,
    default_kinds: tuple[str, ...] = (),
    reason: str = "",
) -> MapResolution:
    """Build a map from Gemini's map_assist decision plus the local origin.

    The counterpart to ``resolve``: the model has already judged (from tokenized
    text) that a map helps and which facilities to show. Here the device turns
    that into an actual resolution against the offline index, using a position
    that never left it. ``default_kinds`` is the medically-sensible fallback when
    the model asked for a map but named no categories.
    """
    kinds = resolve_kinds(facility_kinds) or default_kinds
    intent = MapIntent(
        is_map_query=True,
        kinds=tuple(kinds),
        wants_route=wants_route,
        confidence=1.0,
        matched=[reason] if reason else [],
    )
    return _resolve_with_intent(intent, origin, region, radius_km, limit)


def _resolve_with_intent(
    intent: MapIntent,
    origin: Optional[str | tuple[float, float]],
    region: Optional[str],
    radius_km: Optional[float],
    limit: Optional[int],
) -> MapResolution:
    """Shared tail of ``resolve``/``resolve_suggestion``: origin -> search -> route."""
    resolved_region = region or catalog.default_region()
    position, origin_grid = _resolve_origin(origin, intent)

    if position is None:
        return MapResolution(intent=intent, region=resolved_region, needs_origin=True)

    lat, lon = position
    shown = origin_grid or format_position(lat, lon)

    warning = ""
    if _out_of_region(resolved_region, lat, lon):
        warning = (
            f"Position {shown} lies outside the installed "
            f"'{resolved_region}' map. Results may be incomplete."
        )

    # operator_all_kinds: a map ANSWER always reflects what the operator marked.
    # A place they flagged (even a plain note) surfaces near the origin regardless
    # of the kind filter, so "nearest hospital" can return the emergency hospital
    # they pinned themselves.
    hits = facility_search.search(
        lat, lon, kinds=intent.kinds, radius_km=radius_km, limit=limit,
        region=resolved_region, operator_all_kinds=True,
    )

    route = None
    if hits:
        nearest = hits[0].facility
        route = get_provider().route(lat, lon, nearest.lat, nearest.lon)

    if not hits and not warning:
        radius = radius_km if radius_km is not None else settings.MAPS_SEARCH_RADIUS_KM
        warning = f"No matching facility within {radius:g} km."

    return MapResolution(
        intent=intent,
        region=resolved_region,
        origin=position,
        origin_grid=origin_grid,
        hits=hits,
        route=route,
        warning=warning,
    )


# -- deterministic prose (no egress) -------------------------------------


def _describe(hit: FacilityHit, route: Optional[Route] = None) -> str:
    provenance = "" if hit.facility.verified else " [operator-reported, unverified]"
    line = (
        f"{hit.facility.name} ({hit.facility.label}) — "
        f"{position_label(hit.grid)} {hit.grid}, {hit.distance_km:.1f} km {hit.compass}{provenance}"
    )
    if route and route.is_straight_line:
        line += " (straight-line)"
    return line


def render_offline_answer(resolution: MapResolution) -> tuple[str, list[str]]:
    """(answer, key_points) assembled locally. Never touches the network."""
    if resolution.needs_origin:
        return (
            "I need your position before I can find the nearest facility. "
            "Send an MGRS grid (for example 42S WD 1234 5678) or decimal coordinates.",
            [],
        )

    if not resolution.hits:
        return (
            resolution.warning or "No matching facility found in the installed map data.",
            [],
        )

    nearest = resolution.hits[0]
    answer = f"**Nearest: {_describe(nearest, resolution.route)}**"

    if resolution.route and resolution.route.is_straight_line:
        answer += (
            "\n\nDistance is straight-line. Expect road distance to run "
            "roughly 20-40% longer, and no ETA is offered because none can be "
            "computed without the road network."
        )
    if resolution.warning:
        answer += f"\n\n{resolution.warning}"
    if not nearest.facility.verified:
        answer += (
            "\n\nThis is an operator-reported pin, not surveyed map data. "
            "Confirm before committing a casualty to it."
        )

    others = [_describe(hit) for hit in resolution.hits[1:]]
    return answer, others
