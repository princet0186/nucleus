"""Geodesy primitives and MGRS <-> WGS84 conversion.

Pure computation, no I/O and no network. Operators speak in MGRS grids, the
9-line MEDEVAC carries a grid, and the egress sanitizer already recognizes the
grid format — so grids are the native currency here and lat/lon is the internal
representation.

Distances use the haversine formula on a spherical earth (R = 6371.0088 km, the
mean radius). Worst-case error against the WGS84 ellipsoid is ~0.5%, i.e. ~20 m
over a 4 km evacuation leg. That is well inside GPS-denied positional
uncertainty and far inside the error of a straight-line-vs-road estimate, so
the extra cost of Vincenty/geodesic solving buys nothing at this scale.
"""

from __future__ import annotations

import math
import re
from typing import Optional

EARTH_RADIUS_KM = 6371.0088

# MGRS: zone (1-60), latitude band (C-X, no I/O), 100km square (2 letters, no
# I/O), then equal-length easting and northing (1-5 digits each = 10km..1m).
# Deliberately stricter than the sanitizer's GRID rule: that one over-matches on
# purpose (redacting a non-grid is harmless), while parsing a non-grid as a
# position would put a casualty in the wrong place.
#
# The digit alternatives run longest-first, and that ordering is load-bearing.
# Operators write "42S WD 1234 5678" (10 m). Try the 4-digit branch first and it
# matches "1234", finds a word boundary at the space, and silently returns a
# 10 km-precision grid — putting the casualty up to 7 km from where they are.
# Longest-first makes the full-precision read the only one that can win.
_EASTING_NORTHING = r"(?:\d{5}\s?\d{5}|\d{4}\s?\d{4}|\d{3}\s?\d{3}|\d{2}\s?\d{2}|\d\s?\d)"
MGRS_RE = re.compile(
    rf"\b(\d{{1,2}}\s?[C-HJ-NP-X]\s?[A-HJ-NP-Z]{{2}}\s?{_EASTING_NORTHING})\b",
    re.IGNORECASE,
)

# Decimal degrees, "lat, lon". Requires a decimal point on both so that a bare
# "12, 34" (patient counts, line numbers) is never read as a position.
LATLON_RE = re.compile(r"(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)")

_COMPASS_16 = (
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
)


class GridError(ValueError):
    """An MGRS string could not be parsed into a position."""


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial great-circle bearing from point 1 to point 2, degrees true (0-360)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def compass_point(bearing_deg: float) -> str:
    """16-point compass abbreviation for a true bearing."""
    return _COMPASS_16[int((bearing_deg % 360.0) / 22.5 + 0.5) % 16]


def bbox_around(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """Bounding box (min_lat, max_lat, min_lon, max_lon) enclosing a radius.

    Used to pre-filter the R*Tree before exact haversine ranking, so it must
    never under-cover. Longitude degrees shrink with latitude; near the poles
    cos(lat) collapses and the span explodes, so the box is clamped to the whole
    parallel rather than allowed to wrap the antimeridian.
    """
    lat_delta = math.degrees(radius_km / EARTH_RADIUS_KM)
    min_lat = max(-90.0, lat - lat_delta)
    max_lat = min(90.0, lat + lat_delta)

    # Widest longitude span occurs at the latitude nearest a pole.
    worst_lat = max(abs(min_lat), abs(max_lat))
    cos_lat = math.cos(math.radians(worst_lat))
    if cos_lat < 1e-9:
        return min_lat, max_lat, -180.0, 180.0

    lon_delta = math.degrees(radius_km / EARTH_RADIUS_KM / cos_lat)
    if lon_delta >= 180.0:
        return min_lat, max_lat, -180.0, 180.0
    return min_lat, max_lat, lon - lon_delta, lon + lon_delta


def normalize_grid(grid: str) -> str:
    """Uppercase, strip internal whitespace: '42S WD 1234 5678' -> '42SWD12345678'."""
    return re.sub(r"\s+", "", grid).upper()


def _mgrs_lib():
    try:
        import mgrs  # noqa: PLC0415 — optional at import time so tiles serve without it
    except ImportError as exc:  # pragma: no cover
        raise GridError(
            "MGRS support requires the 'mgrs' package (pip install mgrs)."
        ) from exc
    return mgrs.MGRS()


def from_mgrs(grid: str) -> tuple[float, float]:
    """MGRS grid -> (lat, lon). Raises GridError on anything unparseable."""
    normalized = normalize_grid(grid)
    if not MGRS_RE.fullmatch(normalized):
        raise GridError(f"Not a valid MGRS grid: {grid!r}")
    try:
        lat, lon = _mgrs_lib().toLatLon(normalized)
    except GridError:
        raise
    except Exception as exc:  # noqa: BLE001 — the C library raises bare RuntimeError
        raise GridError(f"Could not resolve MGRS grid {grid!r}: {exc}") from exc
    return float(lat), float(lon)


def to_mgrs(lat: float, lon: float, precision: int = 5) -> str:
    """(lat, lon) -> MGRS grid. precision 5 = 1 m, 4 = 10 m, 3 = 100 m."""
    try:
        grid = _mgrs_lib().toMGRS(lat, lon, MGRSPrecision=precision)
    except GridError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise GridError(f"Could not convert {lat},{lon} to MGRS: {exc}") from exc
    return grid.decode() if isinstance(grid, bytes) else str(grid)


def find_grid(text: str) -> Optional[str]:
    """The first parseable MGRS grid in ``text``, normalized. None if there is none."""
    if not text:
        return None
    for match in MGRS_RE.finditer(text):
        candidate = normalize_grid(match.group(1))
        try:
            from_mgrs(candidate)
        except GridError:
            continue
        return candidate
    return None


def parse_position(text: str) -> Optional[tuple[float, float]]:
    """Best-effort position from free text: an MGRS grid, else 'lat, lon'.

    Returns None when the text carries no position, which is the signal for the
    caller to ask the operator for one rather than guess.
    """
    if not text:
        return None

    grid = find_grid(text)
    if grid:
        return from_mgrs(grid)

    coord_match = LATLON_RE.search(text)
    if coord_match:
        lat, lon = float(coord_match.group(1)), float(coord_match.group(2))
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
            return lat, lon

    return None


def position_label(position: str) -> str:
    """"GRID" for an MGRS string, "POS" for anything else.

    ``format_position`` falls back to decimal degrees outside MGRS coverage (or
    when the ``mgrs`` package is missing). Captioning those digits "GRID" on a
    line a medic reads over a radio invites them to be copied into a 9-line as a
    grid reference. Name the thing you actually have.
    """
    return "GRID" if MGRS_RE.fullmatch(normalize_grid(position)) else "POS"


def format_position(lat: float, lon: float) -> str:
    """MGRS if convertible, else decimal degrees. Never raises — display only.

    Only for positions that are natively lat/lon (an OSM facility, a GPS fix).
    Never re-encode a grid the operator typed: converting their grid to lat/lon
    and back lands on the same ground to within a metre, but renders a different
    *string* — "42S WD 1234 5678" comes back as "42SWD1233956779". The operator
    then has to work out whether the system moved their casualty. Echo the grid
    they gave you; see ``resolver.MapResolution.origin_grid``.
    """
    try:
        return to_mgrs(lat, lon)
    except GridError:
        return f"{lat:.5f}, {lon:.5f}"
