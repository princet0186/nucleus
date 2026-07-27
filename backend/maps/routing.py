"""Route computation behind a provider seam.

Today there is exactly one provider: straight line. It answers the question the
9-line MEDEVAC actually asks — *how far and on what bearing* — using nothing but
the geodesy already in ``geo.py``. No container, no graph build, no service.

When the live-tracking phase lands, a ``ValhallaProvider`` (road distance, ETA,
map-matched traces, re-route on deviation) drops in behind this same interface
and the API contract does not move. That is the entire point of the seam:
choosing a routing engine is a decision about live tracking, and live tracking
is not being built yet.

``duration_min`` is None for straight-line routes, deliberately. Dividing a
crow-flight distance by an assumed speed produces a number that looks like an
ETA and is not one. In a MEDEVAC that number gets read over a radio. A missing
ETA is a fact the operator can act on; a fabricated one is not.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional, Protocol

from backend.core.config import settings
from backend.maps.geo import compass_point, haversine_km, initial_bearing_deg

PROFILE_FOOT = "foot"
PROFILE_VEHICLE = "vehicle"
PROFILE_AIR = "air"
PROFILES = (PROFILE_FOOT, PROFILE_VEHICLE, PROFILE_AIR)


@dataclass
class Route:
    """A path from origin to destination.

    ``geometry`` is GeoJSON order — [[lon, lat], ...] — so it can be handed to
    MapLibre as a LineString source without transformation.
    """

    distance_km: float
    bearing_deg: float
    compass: str
    provider: str
    profile: str
    is_straight_line: bool
    duration_min: Optional[float] = None
    geometry: list[list[float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "distance_km": round(self.distance_km, 3),
            "bearing_deg": round(self.bearing_deg, 1),
            "compass": self.compass,
            "duration_min": self.duration_min,
            "provider": self.provider,
            "profile": self.profile,
            "is_straight_line": self.is_straight_line,
            "geometry": self.geometry,
        }


class RouteProvider(Protocol):
    name: str

    def route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        profile: str = PROFILE_VEHICLE,
    ) -> Route: ...


class StraightLineProvider:
    """Great-circle distance and true bearing. Zero dependencies, always available.

    Honest about what it is not: ``is_straight_line`` is True and there is no
    ETA. Real road distance is typically 1.2-1.4x this, and terrain can make it
    far worse, so the operator must treat it as a lower bound.
    """

    name = "straight_line"

    def route(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
        profile: str = PROFILE_VEHICLE,
    ) -> Route:
        distance = haversine_km(origin_lat, origin_lon, dest_lat, dest_lon)
        bearing = initial_bearing_deg(origin_lat, origin_lon, dest_lat, dest_lon)
        return Route(
            distance_km=distance,
            bearing_deg=bearing,
            compass=compass_point(bearing),
            provider=self.name,
            profile=profile,
            is_straight_line=True,
            duration_min=None,
            geometry=[[origin_lon, origin_lat], [dest_lon, dest_lat]],
        )


_PROVIDERS: dict[str, type] = {
    StraightLineProvider.name: StraightLineProvider,
    # "valhalla": ValhallaProvider,   <- live-tracking phase
    # "osrm":     OsrmProvider,
}

_lock = threading.Lock()
_provider: Optional[RouteProvider] = None


def get_provider() -> RouteProvider:
    """The configured provider. Falls back to straight-line rather than failing.

    A field device with a misconfigured routing engine must still be able to say
    "the hospital is 4.2 km northeast".
    """
    global _provider
    with _lock:
        if _provider is not None:
            return _provider

        name = settings.MAPS_ROUTING_PROVIDER.strip().lower()
        factory = _PROVIDERS.get(name)
        if factory is None:
            print(
                f"[MAPS] Unknown routing provider {name!r}; "
                f"using {StraightLineProvider.name}. "
                f"Available: {', '.join(sorted(_PROVIDERS))}"
            )
            factory = StraightLineProvider

        _provider = factory()
        return _provider


def reset_provider() -> None:
    """Drop the cached provider. For tests and for config reload."""
    global _provider
    with _lock:
        _provider = None
