"""Offline maps API: vector tiles, facility search, operator pins.

Route order matters. Tiles live under a ``/tiles`` prefix and fonts under
``/fonts`` so that no path parameter can shadow ``/poi`` or ``/status``.

Nothing here reaches the network. The only endpoint that can emit is
``/maps/resolve``, and only to have Gemini phrase a result that was already
computed on-device from tokenized facts.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse

from backend.core.config import settings
from backend.maps import catalog, facilities as facility_search, resolver, style as style_builder
from backend.maps import user_poi
from backend.maps.geo import GridError, format_position, from_mgrs
from backend.maps.mbtiles import MBTilesError, is_gzipped, tile_etag
from backend.maps.poi_index import PoiIndexError
from backend.models.common import SanitizationMetadata
from backend.models.map_schemas import (
    FacilitySearchRequest,
    FacilitySearchResponse,
    MapResolveRequest,
    MapResolveResponse,
    UserPoiCreate,
    UserPoiListResponse,
    UserPoiResponse,
)

router = APIRouter(prefix="/maps", tags=["Offline Maps"])

# Tiles are immutable for a given region build: a changed map means a new file.
_TILE_CACHE_CONTROL = "public, max-age=604800, immutable"


def _base_url(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _position(payload) -> tuple[float, float]:
    """Resolve a _PositionMixin into (lat, lon), turning a bad grid into a 400."""
    if payload.grid:
        try:
            return from_mgrs(payload.grid)
        except GridError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return float(payload.lat), float(payload.lon)


def _require_region(region: Optional[str]) -> str:
    resolved = region or catalog.default_region()
    if not resolved:
        installed = catalog.region_names()
        detail = (
            f"No default region. Installed: {installed}. "
            "Set MAPS_DEFAULT_REGION or pass 'region'."
            if installed
            else "No map regions installed. See docs/maps.md to build one."
        )
        raise HTTPException(status_code=404, detail=detail)
    return resolved


# -- status ---------------------------------------------------------------


@router.get("/status")
async def maps_status():
    """What is installed and what the map layer can do right now."""
    return await asyncio.to_thread(catalog.status)


@router.get("/regions")
async def list_regions():
    return {"regions": catalog.region_names(), "default": catalog.default_region()}


# -- tiles ----------------------------------------------------------------


@router.get("/tiles/{region}/tilejson.json")
async def tilejson(region: str, request: Request):
    try:
        tiles = catalog.get_tiles(region)
    except MBTilesError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return style_builder.tilejson(region, tiles, _base_url(request))


@router.get("/tiles/{region}/style.json")
async def style_json(region: str, request: Request, theme: Optional[str] = None):
    """A complete MapLibre style. Self-contained: no CDN, no remote font, no sprite.

    ``theme`` selects the palette ("day" | "night"); an unknown or omitted value
    falls back to the configured default.
    """
    try:
        tiles = catalog.get_tiles(region)
    except MBTilesError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return style_builder.style(region, tiles, _base_url(request), theme=theme)


@router.get("/tiles/{region}/{z}/{x}/{y}.pbf")
async def vector_tile(region: str, z: int, x: int, y: int, request: Request):
    """One vector tile.

    A missing tile is 204, not 404: empty ocean and empty desert are legitimate
    answers, and MapLibre treats a 404 as an error worth retrying.
    """
    try:
        tiles = catalog.get_tiles(region)
    except MBTilesError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not tiles.is_vector:
        raise HTTPException(
            status_code=400,
            detail=f"Region '{region}' holds {tiles.format} tiles, not vector tiles.",
        )

    data = await asyncio.to_thread(tiles.tile, z, x, y)
    if data is None:
        return Response(status_code=204)

    etag = tile_etag(data)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": _TILE_CACHE_CONTROL})

    headers = {"ETag": etag, "Cache-Control": _TILE_CACHE_CONTROL}
    if is_gzipped(data):
        # Planetiler stores tiles gzipped. Hand the bytes straight through rather
        # than inflating them only for the browser to inflate them again.
        headers["Content-Encoding"] = "gzip"

    return Response(content=data, media_type="application/x-protobuf", headers=headers)


@router.get("/fonts/{fontstack}/{glyph_range}.pbf")
async def glyphs(fontstack: str, glyph_range: str):
    """Serve glyph PBFs from disk so labels never require a CDN."""
    fonts_dir = settings.FONTS_DIR
    path = (fonts_dir / fontstack / f"{glyph_range}.pbf").resolve()

    # A fontstack arrives from the style and could contain traversal.
    try:
        path.relative_to(fonts_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid font path") from exc

    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"No glyphs for {fontstack} {glyph_range}")

    return FileResponse(
        path,
        media_type="application/x-protobuf",
        headers={"Cache-Control": _TILE_CACHE_CONTROL},
    )


# -- facility search ------------------------------------------------------


@router.get("/position")
async def resolve_position(grid: Optional[str] = None, lat: Optional[float] = None, lon: Optional[float] = None):
    """Resolve a typed position (MGRS grid OR lat/lon) to {lat, lon, grid}.

    Lets the operator mark an exact coordinate by typing it, rather than only by
    clicking the map. Pure conversion; nothing is stored and nothing leaves the
    device.
    """
    if grid and grid.strip():
        try:
            plat, plon = from_mgrs(grid.strip())
        except GridError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif lat is not None and lon is not None:
        if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            raise HTTPException(status_code=400, detail="Position out of range.")
        plat, plon = float(lat), float(lon)
    else:
        raise HTTPException(status_code=400, detail="Provide 'grid', or 'lat' and 'lon'.")
    return {"lat": plat, "lon": plon, "grid": format_position(plat, plon)}


@router.get("/facilities")
async def list_facilities(region: Optional[str] = None, include_operator: bool = True):
    """Every facility in a region, for a map overview — no position, no ranking.

    Backs the map opening on its facilities before the operator types a grid.
    Returns plain facilities (no distance/bearing); those need an origin, which
    ``/search`` requires and this deliberately does not.
    """
    resolved = region or catalog.default_region()
    found = await asyncio.to_thread(
        facility_search.list_region, resolved, include_operator
    )
    return {
        "region": resolved,
        "count": len(found),
        "facilities": [
            {
                "id": f.id,
                "name": f.name,
                "kind": f.kind,
                "label": f.label,
                "lat": f.lat,
                "lon": f.lon,
                "grid": format_position(f.lat, f.lon),
                "source": f.source,
                "verified": f.verified,
                "note": f.note,
            }
            for f in found
        ],
    }


@router.post("/search", response_model=FacilitySearchResponse)
async def search_facilities(payload: FacilitySearchRequest):
    """Nearest facilities to a position, merged across OSM and operator pins."""
    lat, lon = _position(payload)

    try:
        hits = await asyncio.to_thread(
            facility_search.search,
            lat,
            lon,
            payload.kinds,
            payload.radius_km,
            payload.limit,
            payload.region,
            payload.include_operator,
        )
    except PoiIndexError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return FacilitySearchResponse(
        origin={"lat": lat, "lon": lon, "grid": format_position(lat, lon)},
        region=payload.region or catalog.default_region(),
        count=len(hits),
        facilities=[hit.to_dict() for hit in hits],
    )


# -- chat-driven resolution ----------------------------------------------


@router.post("/resolve", response_model=MapResolveResponse)
async def resolve_map_query(payload: MapResolveRequest):
    """Interpret a chat question. Returns is_map_query=False when it is not one.

    This is the same path ``/nucleus/query`` takes; it is exposed directly so the
    frontend can pre-flight a question, and so the behaviour is testable without
    an API key.
    """
    try:
        resolution = await asyncio.to_thread(
            resolver.resolve,
            payload.query,
            payload.context or "",
            payload.origin,
            payload.region,
            payload.radius_km,
            payload.limit,
        )
    except GridError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if resolution is None:
        return MapResolveResponse(is_map_query=False)

    composed = await compose_answer(payload.query, resolution)
    return MapResolveResponse(
        is_map_query=True,
        answer=composed.answer,
        key_points=composed.key_points,
        source=composed.source,
        map=resolution.to_payload(),
        sanitization=composed.sanitization,
    )


SOURCE_GEMINI = "gemini_prose"
SOURCE_TEMPLATE = "offline_template"


@dataclass
class ComposedAnswer:
    """Prose for a resolved lookup, plus proof of what (if anything) was sent."""

    answer: str
    source: str
    key_points: list[str] = field(default_factory=list)
    sanitization: Optional[SanitizationMetadata] = None


async def compose_answer(query: str, resolution: resolver.MapResolution) -> ComposedAnswer:
    """Gemini phrasing when it is available, the local template otherwise.

    Shared with ``/nucleus/query``.

    The offline template is not a degraded mode — it is the guarantee. Every
    failure here (no key, no signal, quota exhausted, model refusal, invented
    facility, or a link that simply stops answering) lands on a deterministic
    answer built from local data, because a medic asking where to take a casualty
    must get an answer with the radio off.

    That last case is why there is a deadline. A degraded link blackholes packets
    instead of refusing them, so waiting for an exception can mean waiting
    forever. ``MAPS_AI_TIMEOUT_S`` bounds the wait; the local answer, already
    computed, wins.

    ``sanitization`` stays None only when nothing was ever transmitted. If the
    prompt went out and the reply was rejected — or never arrived — the tokenized
    egress is still reported. Claiming otherwise would tell the operator's
    privacy panel that the radio stayed silent when it did not.
    """
    can_ask_ai = (
        settings.MAPS_AI_PROSE
        and bool(resolution.hits)
        and not resolution.needs_origin
    )

    egress: Optional[SanitizationMetadata] = None

    if can_ask_ai:
        # Imported late: the maps layer must not drag the Gemini client (and its
        # key manager) into a device configured for zero egress.
        from backend.services.Gemini_Services.key_manager import key_manager
        from backend.services.Gemini_Services.map_service import (
            MapEgressError,
            generate_map_answer,
        )

        if key_manager.is_ready:
            # Captured before transmission, so a timeout can still report it.
            sent: dict = {}
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(generate_map_answer, query, resolution, sent.update),
                    timeout=settings.MAPS_AI_TIMEOUT_S,
                )
                return ComposedAnswer(
                    answer=result["answer"],
                    key_points=result["key_points"],
                    source=SOURCE_GEMINI,
                    sanitization=SanitizationMetadata(**result["sanitization"]),
                )
            except asyncio.TimeoutError:
                if sent:
                    egress = SanitizationMetadata(**sent)
                print(
                    f"[MAPS] AI prose timed out after {settings.MAPS_AI_TIMEOUT_S}s; "
                    "using offline template"
                )
            except MapEgressError as exc:
                # The prompt was transmitted; only the answer is being discarded.
                egress = SanitizationMetadata(**exc.sanitization)
                print(f"[MAPS] AI prose rejected ({str(exc)[:120]}); using offline template")
            except Exception as exc:  # noqa: BLE001 — failed before egress
                print(f"[MAPS] AI prose unavailable ({str(exc)[:120]}); using offline template")

    answer, key_points = resolver.render_offline_answer(resolution)
    return ComposedAnswer(
        answer=answer, key_points=key_points, source=SOURCE_TEMPLATE, sanitization=egress
    )


async def compose_chat_answer(query: str, resolution: resolver.MapResolution) -> ComposedAnswer:
    """``compose_answer`` with key_points folded into the answer body.

    ``/nucleus/query`` returns a single ``response`` string, so the bullets have
    to be rendered into it rather than travelling as a separate field.
    """
    composed = await compose_answer(query, resolution)
    if composed.key_points:
        composed.answer += "\n\n" + "\n".join(f"- {point}" for point in composed.key_points)
    return composed


# -- operator POIs --------------------------------------------------------


def _poi_response(facility) -> UserPoiResponse:
    return UserPoiResponse(
        id=facility.id,
        name=facility.name,
        kind=facility.kind,
        label=facility.label,
        lat=facility.lat,
        lon=facility.lon,
        grid=format_position(facility.lat, facility.lon),
        note=facility.note,
        created_at=facility.created_at,
    )


@router.get("/poi", response_model=UserPoiListResponse)
async def list_operator_pois():
    pois = await asyncio.to_thread(user_poi.list_all)
    return UserPoiListResponse(
        count=len(pois),
        limit=settings.MAPS_USER_POI_LIMIT,
        kinds=user_poi.operator_kind_choices(),
        pois=[_poi_response(poi) for poi in pois],
    )


@router.post("/poi", response_model=UserPoiResponse, status_code=201)
async def create_operator_poi(payload: UserPoiCreate):
    """Record a place the operator found. Encrypted at rest; destroyed by secure wipe."""
    lat, lon = _position(payload)
    try:
        facility = await asyncio.to_thread(
            user_poi.add, payload.name, payload.kind, lat, lon, payload.note
        )
    except user_poi.UserPoiError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _poi_response(facility)


@router.delete("/poi/{poi_id}", status_code=204)
async def delete_operator_poi(poi_id: str):
    removed = await asyncio.to_thread(user_poi.delete, poi_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"No operator POI {poi_id}")
    return Response(status_code=204)


@router.post("/poi/wipe")
async def wipe_operator_pois():
    """Delete every operator pin, leaving the rest of the application intact."""
    removed = await asyncio.to_thread(user_poi.wipe)
    return JSONResponse({"wiped": removed})
