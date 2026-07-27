"""Request/response models for the offline maps API.

Kept separate from ``schemas.py`` so the map surface can grow (routing, live
tracking) without turning the core query schema into a junk drawer.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator

from backend.models.common import SanitizationMetadata


# -- shared ---------------------------------------------------------------


class MapOrigin(BaseModel):
    lat: float
    lon: float
    grid: str = Field(description="MGRS grid, or decimal degrees when outside MGRS coverage")


class MapFacility(BaseModel):
    id: str
    name: str
    kind: str
    label: str
    lat: float
    lon: float
    grid: str
    distance_km: float
    bearing_deg: float
    compass: str
    source: str = Field(description="'osm' (surveyed) or 'operator' (unverified pin)")
    verified: bool
    note: str = ""
    created_at: Optional[str] = None
    tags: dict = Field(default_factory=dict)


class MapRoute(BaseModel):
    distance_km: float
    bearing_deg: float
    compass: str
    provider: str
    profile: str
    is_straight_line: bool
    duration_min: Optional[float] = Field(
        default=None,
        description="None for straight-line routes. No ETA is invented from crow-flight distance.",
    )
    geometry: list[list[float]] = Field(
        default_factory=list, description="GeoJSON order: [[lon, lat], ...]"
    )


class MapPayload(BaseModel):
    """What the chat hands the map sidebar when a question needs a map."""

    open_map: bool = True
    needs_origin: bool = False
    region: Optional[str] = None
    origin: Optional[MapOrigin] = None
    kinds: list[str] = Field(default_factory=list)
    wants_route: bool = False
    confidence: float = 0.0
    matched: list[str] = Field(default_factory=list)
    facilities: list[MapFacility] = Field(default_factory=list)
    route: Optional[MapRoute] = None
    warning: str = ""


# -- position input -------------------------------------------------------


class _PositionMixin(BaseModel):
    """Accepts either an MGRS grid or a lat/lon pair, and insists on exactly one."""

    grid: Optional[str] = Field(default=None, examples=["42S WD 1234 5678"])
    lat: Optional[float] = Field(default=None, ge=-90, le=90)
    lon: Optional[float] = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _one_position(self):
        has_grid = bool(self.grid and self.grid.strip())
        has_coords = self.lat is not None and self.lon is not None

        if has_grid and has_coords:
            raise ValueError("Provide either 'grid' or 'lat'/'lon', not both.")
        if not has_grid and not has_coords:
            if self.lat is not None or self.lon is not None:
                raise ValueError("Both 'lat' and 'lon' are required together.")
            raise ValueError("A position is required: send 'grid', or 'lat' and 'lon'.")
        return self


# -- endpoints ------------------------------------------------------------


class FacilitySearchRequest(_PositionMixin):
    kinds: list[str] = Field(
        default_factory=list,
        description="Groups ('medical', 'evac', 'support') and/or kinds ('hospital'). Empty = all.",
        examples=[["medical"]],
    )
    radius_km: Optional[float] = Field(default=None, gt=0)
    limit: Optional[int] = Field(default=None, gt=0, le=200)
    region: Optional[str] = None
    include_operator: bool = True


class FacilitySearchResponse(BaseModel):
    origin: MapOrigin
    region: Optional[str] = None
    count: int
    facilities: list[MapFacility] = Field(default_factory=list)


class MapResolveRequest(BaseModel):
    """Ask the map layer to interpret a chat question. Mirrors /nucleus/query."""

    query: str = Field(min_length=3, examples=["Where is the nearest evacuation centre?"])
    context: Optional[str] = None
    origin: Optional[str] = Field(
        default=None,
        description="MGRS grid or 'lat,lon'. Omit when the question already carries one.",
        examples=["42S WD 1234 5678"],
    )
    region: Optional[str] = None
    radius_km: Optional[float] = Field(default=None, gt=0)
    limit: Optional[int] = Field(default=None, gt=0, le=200)


class MapResolveResponse(BaseModel):
    is_map_query: bool
    answer: str = ""
    key_points: list[str] = Field(default_factory=list)
    source: str = Field(default="", description="'gemini_prose' or 'offline_template'")
    map: Optional[MapPayload] = None
    sanitization: Optional[SanitizationMetadata] = Field(
        default=None,
        description="Absent on the offline template path, which sends nothing at all.",
    )


class UserPoiCreate(_PositionMixin):
    name: str = Field(min_length=1, max_length=120, examples=["Evac point Alpha"])
    kind: str = Field(examples=["evac_point"])
    note: str = Field(default="", max_length=500)


class UserPoiResponse(BaseModel):
    id: str
    name: str
    kind: str
    label: str
    lat: float
    lon: float
    grid: str
    note: str = ""
    created_at: Optional[str] = None
    verified: bool = False
    source: str = "operator"


class UserPoiListResponse(BaseModel):
    count: int
    limit: int
    kinds: list[dict] = Field(description="Kinds an operator is permitted to create")
    pois: list[UserPoiResponse] = Field(default_factory=list)
