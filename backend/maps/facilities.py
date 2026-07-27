"""Unified facility search across the OSM index and operator-added pins.

Two stores with opposite properties are merged here:

    OSM index    public, surveyed, R*Tree-indexed, read-only, survives a wipe
    operator     private, unverified, encrypted, linear-scanned, wiped

Every result carries its provenance. A medic reading "Evac point (Alpha) —
operator-reported, unverified, 2h ago" is making a different decision than one
reading "District Hospital — OSM". Flattening that distinction to save a field
in the response would be the wrong kind of tidy.

Ordering is by distance. See ``facility.py`` for why capability does not
outrank proximity here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from backend.core.config import settings
from backend.maps import catalog, user_poi
from backend.maps.facility import Facility, resolve_kinds
from backend.maps.geo import compass_point, format_position, initial_bearing_deg

# Pulled from each store before merge. Generous enough that the merged, ranked
# result is stable, bounded enough that a query in a dense city stays cheap.
_CANDIDATE_LIMIT = 200


@dataclass
class FacilityHit:
    """A facility with its spatial relationship to the query origin."""

    facility: Facility
    distance_km: float
    bearing_deg: float
    compass: str
    grid: str

    def to_dict(self) -> dict:
        facility = self.facility
        return {
            "id": facility.id,
            "name": facility.name,
            "kind": facility.kind,
            "label": facility.label,
            "lat": facility.lat,
            "lon": facility.lon,
            "grid": self.grid,
            "distance_km": round(self.distance_km, 3),
            "bearing_deg": round(self.bearing_deg, 1),
            "compass": self.compass,
            "source": facility.source,
            "verified": facility.verified,
            "note": facility.note,
            "created_at": facility.created_at,
            "tags": facility.tags,
        }


def _to_hit(origin_lat: float, origin_lon: float, facility: Facility, distance_km: float) -> FacilityHit:
    bearing = initial_bearing_deg(origin_lat, origin_lon, facility.lat, facility.lon)
    return FacilityHit(
        facility=facility,
        distance_km=distance_km,
        bearing_deg=bearing,
        compass=compass_point(bearing),
        grid=format_position(facility.lat, facility.lon),
    )


def list_region(
    region: Optional[str] = None,
    include_operator: bool = True,
    limit: int = 5000,
) -> list[Facility]:
    """Every facility in a region, for a map overview — no origin, no ranking.

    Search needs a position; browsing does not. This backs the map opening on the
    region with its facilities already plotted, before the operator has typed a
    grid.
    """
    found: list[Facility] = []

    resolved_region = region or catalog.default_region()
    if resolved_region:
        index = catalog.get_poi_index(resolved_region)
        if index is not None:
            found.extend(index.all(limit=limit))

    if include_operator:
        found.extend(user_poi.list_all())

    return found


def search(
    lat: float,
    lon: float,
    kinds: Iterable[str] = (),
    radius_km: Optional[float] = None,
    limit: Optional[int] = None,
    region: Optional[str] = None,
    include_operator: bool = True,
    operator_all_kinds: bool = False,
) -> list[FacilityHit]:
    """Nearest facilities to a position, merged across both stores.

    ``kinds`` accepts group names ("medical", "evac", "support") and concrete
    kinds ("hospital", "helipad") interchangeably. Empty means every kind.

    ``operator_all_kinds`` surfaces the operator's OWN marks near the origin
    regardless of the kind filter. A place the operator deliberately marked — an
    emergency hospital they flagged as a plain note, say — is intentional context
    and should come up for "nearest hospital" even if its kind does not match.
    OSM facilities still honour the filter; only the operator's marks bypass it.
    Used by the chat/AI path so a map answer always reflects what the operator
    put on the map.

    A missing OSM index is not an error: the operator's own pins are still
    searchable, which is exactly the state of a freshly deployed device whose
    region has not been installed yet.
    """
    radius = min(
        radius_km if radius_km is not None else settings.MAPS_SEARCH_RADIUS_KM,
        settings.MAPS_MAX_SEARCH_RADIUS_KM,
    )
    max_results = limit if limit is not None else settings.MAPS_MAX_RESULTS
    wanted = resolve_kinds(list(kinds)) if kinds else ()

    found: list[tuple[Facility, float]] = []

    resolved_region = region or catalog.default_region()
    if resolved_region:
        index = catalog.get_poi_index(resolved_region)
        if index is not None:
            found.extend(index.within(lat, lon, radius, wanted, limit=_CANDIDATE_LIMIT))

    if include_operator:
        op_kinds = () if operator_all_kinds else wanted
        found.extend(user_poi.within(lat, lon, radius, op_kinds, limit=_CANDIDATE_LIMIT))

    # Distance first; capability only settles an exact tie; name makes it stable.
    found.sort(key=lambda pair: (pair[1], -pair[0].priority, pair[0].name))

    return [_to_hit(lat, lon, facility, distance) for facility, distance in found[:max_results]]
