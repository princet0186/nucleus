"""Facility taxonomy: the one place OSM tags, kinds, and query groups are defined.

Both the offline build tool (``tools/build_poi_index.py``) and the runtime query
path import from here, so an index can never be built with tags the search does
not understand.

``priority`` ranks a kind by medical capability. It breaks exact distance ties
and nothing more: results are ordered by distance, full stop. Trading "6 km
further" against "more capable" would mean inventing an exchange rate between
kilometres and clinical capability, then applying it silently to a life-safety
list. Instead the priority travels to the client, which can re-sort explicitly,
and the medic sees the true ordering and decides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# -- kinds ---------------------------------------------------------------

HOSPITAL = "hospital"
CLINIC = "clinic"
DOCTORS = "doctors"
PHARMACY = "pharmacy"
AID_STATION = "aid_station"
HELIPAD = "helipad"
AIRFIELD = "airfield"
EVAC_POINT = "evac_point"
CASUALTY_COLLECTION_POINT = "casualty_collection_point"
FIRE_STATION = "fire_station"
POLICE = "police"
SHELTER = "shelter"
WATER_POINT = "water_point"
FUEL = "fuel"

# Planning markers: the operator drops these anywhere to annotate the map for
# their own planning. Unlike the facility kinds above, they describe no real-
# world service — they are a note pinned to a place. All operator-only.
WAYPOINT = "waypoint"
OBJECTIVE = "objective"
HAZARD = "hazard"
RALLY_POINT = "rally_point"
OBSERVATION_POST = "observation_post"


@dataclass(frozen=True)
class KindSpec:
    label: str
    group: str
    priority: int  # higher = more capable / preferred at equal distance


KINDS: dict[str, KindSpec] = {
    HOSPITAL: KindSpec("Hospital", "medical", 100),
    CLINIC: KindSpec("Clinic", "medical", 80),
    AID_STATION: KindSpec("Aid station", "medical", 70),
    DOCTORS: KindSpec("Doctor's surgery", "medical", 60),
    PHARMACY: KindSpec("Pharmacy", "medical", 30),
    HELIPAD: KindSpec("Helipad / landing site", "evac", 100),
    EVAC_POINT: KindSpec("Evacuation point", "evac", 90),
    CASUALTY_COLLECTION_POINT: KindSpec("Casualty collection point", "evac", 85),
    AIRFIELD: KindSpec("Airfield", "evac", 70),
    FIRE_STATION: KindSpec("Fire station", "support", 60),
    POLICE: KindSpec("Police station", "support", 50),
    SHELTER: KindSpec("Shelter", "support", 45),
    WATER_POINT: KindSpec("Water point", "support", 30),
    FUEL: KindSpec("Fuel", "support", 20),
    # Planning markers. Priority is low: a note should never outrank a real
    # facility when ranking "nearest care" by distance ties.
    WAYPOINT: KindSpec("Waypoint", "planning", 15),
    OBJECTIVE: KindSpec("Objective", "planning", 15),
    HAZARD: KindSpec("Hazard", "planning", 15),
    RALLY_POINT: KindSpec("Rally point", "planning", 15),
    OBSERVATION_POST: KindSpec("Observation post", "planning", 15),
}

GROUPS: dict[str, tuple[str, ...]] = {
    "medical": (HOSPITAL, CLINIC, AID_STATION, DOCTORS, PHARMACY),
    "evac": (HELIPAD, EVAC_POINT, CASUALTY_COLLECTION_POINT, AIRFIELD),
    "support": (FIRE_STATION, POLICE, SHELTER, WATER_POINT, FUEL),
    "planning": (WAYPOINT, OBJECTIVE, HAZARD, RALLY_POINT, OBSERVATION_POST),
}

# Kinds an operator may create. OSM-only kinds are excluded: an operator marking
# a spot as "hospital" would launder an unverified pin into an authoritative one.
# The medical/evac markers an operator legitimately places, plus the free-form
# planning markers, which describe no service and can go anywhere.
OPERATOR_KINDS: frozenset[str] = frozenset(
    {
        EVAC_POINT, CASUALTY_COLLECTION_POINT, AID_STATION, HELIPAD, SHELTER, WATER_POINT,
        WAYPOINT, OBJECTIVE, HAZARD, RALLY_POINT, OBSERVATION_POST,
    }
)

# -- OSM tag mapping (build-time) ----------------------------------------

# (key, value) -> kind. First match wins, so order matters: healthcare=* is a
# weaker signal than amenity=* and must not override it.
OSM_TAG_MAP: tuple[tuple[str, str, str], ...] = (
    ("amenity", "hospital", HOSPITAL),
    ("amenity", "clinic", CLINIC),
    ("amenity", "doctors", DOCTORS),
    ("amenity", "pharmacy", PHARMACY),
    ("amenity", "fire_station", FIRE_STATION),
    ("amenity", "police", POLICE),
    ("amenity", "shelter", SHELTER),
    ("amenity", "drinking_water", WATER_POINT),
    ("amenity", "fuel", FUEL),
    # emergency=landing_site is the HEMS air-ambulance landing site tag. For a
    # MEDEVAC it is worth as much as a formal helipad, so it maps to one.
    ("emergency", "landing_site", HELIPAD),
    ("emergency", "shelter", SHELTER),
    ("aeroway", "helipad", HELIPAD),
    ("aeroway", "heliport", HELIPAD),
    ("aeroway", "aerodrome", AIRFIELD),
    ("aeroway", "airstrip", AIRFIELD),
    ("healthcare", "hospital", HOSPITAL),
    ("healthcare", "clinic", CLINIC),
    ("healthcare", "centre", CLINIC),
    ("healthcare", "doctor", DOCTORS),
    ("healthcare", "pharmacy", PHARMACY),
)

# Tags copied into the index when present — these are what a medic actually
# needs to decide, and they are small enough to carry per row.
USEFUL_TAGS: tuple[str, ...] = (
    "emergency",
    "phone",
    "operator",
    "healthcare:speciality",
    "capacity:beds",
    "surface",
    "opening_hours",
)


# Kinds an OSM extract can actually produce. Its complement — evac_point,
# casualty_collection_point, aid_station — exists only as operator pins, because
# OpenStreetMap has no tag for "the place my unit evacuates from". A search
# restricted to those kinds can only ever return the operator's own pins.
OSM_KINDS: frozenset[str] = frozenset(kind for _, _, kind in OSM_TAG_MAP)


def group_of(kind: str) -> Optional[str]:
    spec = KINDS.get(kind)
    return spec.group if spec else None


def kind_of(tags: dict) -> Optional[str]:
    """Classify an OSM element. Returns None when it is not a facility we index."""
    for key, value, kind in OSM_TAG_MAP:
        if tags.get(key) == value:
            return kind
    return None


def resolve_kinds(names: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """Expand a mix of group names and kind names into concrete kinds.

    ``["medical", "helipad"]`` -> every medical kind plus helipad. Unknown names
    are dropped rather than raising: an operator asking for "nearest bunker"
    should get a clean empty result, not a 400.
    """
    if not names:
        return ()
    resolved: list[str] = []
    for name in names:
        key = name.strip().lower()
        if key in GROUPS:
            resolved.extend(GROUPS[key])
        elif key in KINDS:
            resolved.append(key)
    return tuple(dict.fromkeys(resolved))


def label_of(kind: str) -> str:
    spec = KINDS.get(kind)
    return spec.label if spec else kind.replace("_", " ").capitalize()


def priority_of(kind: str) -> int:
    spec = KINDS.get(kind)
    return spec.priority if spec else 0


# -- record --------------------------------------------------------------

SOURCE_OSM = "osm"
SOURCE_OPERATOR = "operator"


@dataclass
class Facility:
    """A place, from OSM or from an operator.

    ``verified`` is the provenance flag a medic reads before betting a life on a
    pin. OSM facilities are surveyed; operator pins are one person's word.
    """

    id: str
    name: str
    kind: str
    lat: float
    lon: float
    source: str
    verified: bool
    tags: dict = field(default_factory=dict)
    note: str = ""
    created_at: Optional[str] = None

    @property
    def label(self) -> str:
        return label_of(self.kind)

    @property
    def priority(self) -> int:
        return priority_of(self.kind)
