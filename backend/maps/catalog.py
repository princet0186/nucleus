"""Discovers installed map regions and holds their open handles.

A region is a stem in ``settings.TILES_DIR``:

    data/tiles/kashmir.mbtiles        vector tiles          (required)
    data/tiles/kashmir.poi.sqlite     facility index        (optional)

Both are public OpenStreetMap derivatives — static, read-only, and deliberately
outside the secure-wipe blast radius. Wiping them would cost the operator their
map without denying an adversary anything they could not download themselves.
Operator-added places are the sensitive half and live in nucleus.db instead.

Handles are opened once and cached: MBTiles readers are thread-safe by way of
per-thread connections, so a module-level cache is safe under the FastAPI pool.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional

from backend.core.config import settings
from backend.maps.mbtiles import MBTiles, MBTilesError
from backend.maps.poi_index import PoiIndex, PoiIndexError

_lock = threading.Lock()
_tiles: dict[str, MBTiles] = {}
_pois: dict[str, Optional[PoiIndex]] = {}

POI_SUFFIX = ".poi.sqlite"


def _tiles_dir() -> Path:
    return Path(settings.TILES_DIR)


def region_names() -> list[str]:
    """Every installed region, sorted.

    A region needs *either* half to be useful, so both count:

        tiles only        a basemap you can look at
        POI index only    "nearest hospital" with no basemap under it

    The second is a real deployment, not a broken one — a facility index is a
    few megabytes where tiles are gigabytes, and a medic who needs a grid and a
    bearing does not need to see the terrain to act on them.
    """
    directory = _tiles_dir()
    if not directory.is_dir():
        return []

    names = {path.stem for path in directory.glob("*.mbtiles")}
    # Path.stem on "delhi.poi.sqlite" yields "delhi.poi"; strip the full suffix.
    names.update(
        path.name[: -len(POI_SUFFIX)] for path in directory.glob(f"*{POI_SUFFIX}")
    )
    return sorted(names)


def has_tiles(region: str) -> bool:
    return (_tiles_dir() / f"{region}.mbtiles").is_file()


def default_region() -> Optional[str]:
    """The configured region, or the only installed one, or None if ambiguous."""
    configured = settings.MAPS_DEFAULT_REGION.strip()
    if configured:
        return configured
    names = region_names()
    return names[0] if len(names) == 1 else None


def get_tiles(region: str) -> MBTiles:
    """Open (and cache) a region's tiles. Raises MBTilesError if not installed."""
    with _lock:
        cached = _tiles.get(region)
        if cached is not None:
            return cached

        # Reject traversal: a region name is a bare stem, never a path.
        if "/" in region or "\\" in region or region in ("", ".", ".."):
            raise MBTilesError(f"Invalid region name: {region!r}")

        path = _tiles_dir() / f"{region}.mbtiles"
        reader = MBTiles(path)
        _tiles[region] = reader
        return reader


def get_poi_index(region: str) -> Optional[PoiIndex]:
    """Open (and cache) a region's facility index, or None when unavailable.

    "Unavailable" covers three cases, all treated the same: the index was never
    built, the file is present but half-written (a build still in progress leaves
    a schema-less shell), or it is corrupt. A missing or broken facility index
    must never break the basemap — search just falls back to operator pins — so
    the error is swallowed here rather than propagated up through ``status``.

    A broken index is NOT cached, so it is retried on the next call: an in-
    progress build will start working the moment it finishes.
    """
    with _lock:
        if region in _pois:
            return _pois[region]

        path = _tiles_dir() / f"{region}{POI_SUFFIX}"
        if not path.is_file():
            _pois[region] = None
            return None
        try:
            index = PoiIndex(path)
        except PoiIndexError as exc:
            print(f"[MAPS] facility index for '{region}' unavailable ({exc}); ignoring")
            return None  # not cached — retry next call in case a build is finishing

        _pois[region] = index
        return index


def _tile_meta(entry: dict, name: str) -> None:
    """Fold a region's tile metadata into its status entry."""
    try:
        tiles = get_tiles(name)
    except MBTilesError as exc:
        entry["has_tiles"] = False
        entry["error"] = str(exc)
        return
    entry.update(
        format=tiles.format,
        minzoom=tiles.minzoom,
        maxzoom=tiles.maxzoom,
        bounds=tiles.bounds,
        center=tiles.center,
        vector_layers=[layer.get("id") for layer in tiles.vector_layers],
    )


def _poi_meta(entry: dict, name: str) -> None:
    """Fold a region's facility-index metadata into its status entry.

    For a basemap-less region, the facilities' own extent stands in for tile
    bounds so the map can open on them instead of the whole globe.
    """
    index = get_poi_index(name)
    entry["poi_index"] = {"present": index is not None}
    if index is None:
        return
    entry["poi_index"]["facilities"] = index.count()
    if entry["has_tiles"]:
        return
    box = index.bounds()
    center = index.center()
    if box is not None:
        entry["bounds"] = [box[2], box[0], box[3], box[1]]  # W,S,E,N
    if center is not None:
        entry["center"] = [center[1], center[0]]  # lon, lat


def _region_entry(name: str) -> dict:
    entry: dict = {"region": name, "has_tiles": has_tiles(name)}
    if entry["has_tiles"]:
        _tile_meta(entry, name)
    _poi_meta(entry, name)
    return entry


def status() -> dict:
    """What the map subsystem can actually do right now — surfaced at /maps/status."""
    regions = [_region_entry(name) for name in region_names()]

    return {
        "tiles_dir": str(_tiles_dir()),
        "default_region": default_region(),
        "fonts_installed": Path(settings.FONTS_DIR).is_dir(),
        "routing_provider": settings.MAPS_ROUTING_PROVIDER,
        "ai_prose": settings.MAPS_AI_PROSE,
        "regions": regions,
    }


def reset_cache() -> None:
    """Drop cached handles. For tests and for reload after installing a region."""
    with _lock:
        _tiles.clear()
        _pois.clear()
