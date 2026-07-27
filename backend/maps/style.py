"""TileJSON and self-contained MapLibre styles for the offline basemap.

The style is generated, not shipped as a static asset, because the tile URLs
must point at whatever host the backend is actually reachable on — a field
device has no stable origin.

It references nothing off-device: no CDN, no sprite sheet, no remote fonts. A
style that reaches out for a glyph is a style that emits when the operator
thought the map was offline.

Two themes ship, and adding more is a matter of dropping another palette into
``THEMES`` — every colour the renderer uses comes from the active palette, so a
theme is fully described by ~25 hex values:

    day    a light, familiar street-map look (the default)
    night  a dark, low-emission palette for night / EMCON use

Symbol (text) layers only appear when a glyph directory is installed, because
MapLibre cannot draw a label without a font PBF and an unlabelled map beats a
console full of 404s. See ``docs/maps.md`` for how to install glyphs.

Layer names follow the OpenMapTiles schema, which is what Planetiler emits.
"""

from __future__ import annotations

from pathlib import Path

from backend.core.config import settings
from backend.maps.mbtiles import MBTiles

SOURCE_ID = "nucleus"
FONT_STACK = ["Noto Sans Regular"]

# A theme is just a palette. Same keys in every theme; the layer builder reads
# them by name, so a new look never touches layer logic — only these values.
THEMES: dict[str, dict[str, str]] = {
    # Light street map. Roads are white with grey casing, motorways carry the
    # familiar amber, water is soft blue — legible at a glance, like a road atlas.
    "day": {
        "background": "#e9ebee",
        "water": "#a8d0f0",
        "wood": "#c6e2c1",
        "grass": "#d6e8cc",
        "park": "#c8e6be",
        "landuse": "#ececec",
        "building": "#e2e0dc",
        "building_outline": "#d2cfc8",
        "boundary": "#9b8fb0",
        "aeroway": "#d9dbe0",
        "road_casing": "#d4d6da",
        "motorway": "#f4b940",
        "motorway_casing": "#e39a1c",
        "trunk": "#f7cd6b",
        "primary": "#ffffff",
        "secondary": "#ffffff",
        "minor": "#ffffff",
        "path": "#b6a98f",
        "rail": "#c2c6cb",
        "poi": "#7a8087",
        "label": "#3b3f45",
        "label_halo": "#ffffff",
    },
    # Dark tactical / night. The original low-emission palette: dark enough for
    # night use, roads bright enough to read at a glance.
    "night": {
        "background": "#12161c",
        "water": "#16202e",
        "wood": "#161d18",
        "grass": "#171e1a",
        "park": "#15201a",
        "landuse": "#161a20",
        "building": "#1d222a",
        "building_outline": "#252b34",
        "boundary": "#4a5568",
        "aeroway": "#242a33",
        "road_casing": "#0d1014",
        "motorway": "#c8783c",
        "motorway_casing": "#7a4a24",
        "trunk": "#b08040",
        "primary": "#8a8f98",
        "secondary": "#71767e",
        "minor": "#4d525a",
        "path": "#3c414a",
        "rail": "#2b3038",
        "poi": "#8a9099",
        "label": "#c3c9d1",
        "label_halo": "#0d1014",
    },
}

DEFAULT_THEME = "day"


def resolve_theme(theme: str | None) -> str:
    """Pick a valid theme name, falling back to the configured default."""
    if theme and theme.lower() in THEMES:
        return theme.lower()
    configured = (settings.MAPS_STYLE_THEME or "").lower()
    return configured if configured in THEMES else DEFAULT_THEME


def tilejson(region: str, tiles: MBTiles, base_url: str) -> dict:
    """TileJSON 3.0.0 describing one installed region."""
    return {
        "tilejson": "3.0.0",
        "id": region,
        "name": tiles.name,
        "scheme": "xyz",
        "tiles": [f"{base_url}/maps/tiles/{region}/{{z}}/{{x}}/{{y}}.pbf"],
        "minzoom": tiles.minzoom,
        "maxzoom": tiles.maxzoom,
        "bounds": tiles.bounds,
        "center": tiles.center,
        "attribution": tiles.attribution,
        "vector_layers": tiles.vector_layers,
    }


def fonts_installed() -> bool:
    return Path(settings.FONTS_DIR).is_dir()


def _road_filter(*classes: str) -> list:
    return [
        "all",
        ["==", ["geometry-type"], "LineString"],
        ["in", ["get", "class"], ["literal", list(classes)]],
    ]


def _fill_layers(c: dict) -> list[dict]:
    """Area fills: land, water, parks, aeroways, buildings."""
    return [
        {"id": "background", "type": "background", "paint": {"background-color": c["background"]}},
        {
            "id": "landcover",
            "type": "fill",
            "source": SOURCE_ID,
            "source-layer": "landcover",
            "paint": {
                "fill-color": [
                    "match", ["get", "class"],
                    "wood", c["wood"],
                    "grass", c["grass"],
                    c["landuse"],
                ],
                "fill-opacity": 0.7,
            },
        },
        {
            "id": "landuse",
            "type": "fill",
            "source": SOURCE_ID,
            "source-layer": "landuse",
            "paint": {"fill-color": c["landuse"], "fill-opacity": 0.6},
        },
        {
            "id": "park",
            "type": "fill",
            "source": SOURCE_ID,
            "source-layer": "park",
            "paint": {"fill-color": c["park"], "fill-opacity": 0.6},
        },
        {
            "id": "water",
            "type": "fill",
            "source": SOURCE_ID,
            "source-layer": "water",
            "paint": {"fill-color": c["water"]},
        },
        {
            "id": "waterway",
            "type": "line",
            "source": SOURCE_ID,
            "source-layer": "waterway",
            "paint": {
                "line-color": c["water"],
                "line-width": ["interpolate", ["linear"], ["zoom"], 8, 0.5, 16, 2.5],
            },
        },
        # Aeroways matter for a MEDEVAC app: runways, aprons and helipads should
        # read on the basemap, not only as search pins.
        {
            "id": "aeroway-fill",
            "type": "fill",
            "source": SOURCE_ID,
            "source-layer": "aeroway",
            "filter": ["==", ["geometry-type"], "Polygon"],
            "paint": {"fill-color": c["aeroway"]},
        },
        {
            "id": "aeroway-line",
            "type": "line",
            "source": SOURCE_ID,
            "source-layer": "aeroway",
            "filter": ["==", ["geometry-type"], "LineString"],
            "paint": {
                "line-color": c["aeroway"],
                "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1, 15, 6],
            },
        },
        {
            "id": "building",
            "type": "fill",
            "source": SOURCE_ID,
            "source-layer": "building",
            "minzoom": 13,
            "paint": {
                "fill-color": c["building"],
                "fill-outline-color": c["building_outline"],
                "fill-opacity": 0.9,
            },
        },
    ]


def _road_layers(c: dict) -> list[dict]:
    """Road hierarchy: a shared casing under class-specific fills."""
    return [
        # One casing under everything gives roads a readable outline at any zoom.
        {
            "id": "road-casing",
            "type": "line",
            "source": SOURCE_ID,
            "source-layer": "transportation",
            "minzoom": 6,
            "layout": {"line-cap": "round", "line-join": "round"},
            "paint": {
                "line-color": c["road_casing"],
                "line-width": ["interpolate", ["exponential", 1.4], ["zoom"], 6, 1.4, 14, 7, 18, 26],
            },
        },
        {
            "id": "road-rail",
            "type": "line",
            "source": SOURCE_ID,
            "source-layer": "transportation",
            "minzoom": 9,
            "filter": _road_filter("rail"),
            "paint": {"line-color": c["rail"], "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.6, 16, 2.5]},
        },
        {
            "id": "road-path",
            "type": "line",
            "source": SOURCE_ID,
            "source-layer": "transportation",
            "minzoom": 13,
            "filter": _road_filter("path", "track"),
            "paint": {"line-color": c["path"], "line-width": 1.1, "line-dasharray": [2, 2]},
        },
        {
            "id": "road-minor",
            "type": "line",
            "source": SOURCE_ID,
            "source-layer": "transportation",
            "minzoom": 12,
            "filter": _road_filter("minor", "service"),
            "layout": {"line-cap": "round", "line-join": "round"},
            "paint": {
                "line-color": c["minor"],
                "line-width": ["interpolate", ["exponential", 1.4], ["zoom"], 12, 0.8, 18, 12],
            },
        },
        {
            "id": "road-secondary",
            "type": "line",
            "source": SOURCE_ID,
            "source-layer": "transportation",
            "minzoom": 8,
            "filter": _road_filter("secondary", "tertiary"),
            "layout": {"line-cap": "round", "line-join": "round"},
            "paint": {
                "line-color": c["secondary"],
                "line-width": ["interpolate", ["exponential", 1.4], ["zoom"], 8, 1.0, 18, 16],
            },
        },
        {
            "id": "road-primary",
            "type": "line",
            "source": SOURCE_ID,
            "source-layer": "transportation",
            "minzoom": 7,
            "filter": _road_filter("primary"),
            "layout": {"line-cap": "round", "line-join": "round"},
            "paint": {
                "line-color": c["primary"],
                "line-width": ["interpolate", ["exponential", 1.4], ["zoom"], 7, 1.2, 18, 18],
            },
        },
        {
            "id": "road-trunk",
            "type": "line",
            "source": SOURCE_ID,
            "source-layer": "transportation",
            "minzoom": 5,
            "filter": _road_filter("trunk"),
            "layout": {"line-cap": "round", "line-join": "round"},
            "paint": {
                "line-color": c["trunk"],
                "line-width": ["interpolate", ["exponential", 1.4], ["zoom"], 5, 1.0, 18, 20],
            },
        },
        # Motorways carry a coloured casing of their own so they pop like a real
        # road atlas.
        {
            "id": "road-motorway-casing",
            "type": "line",
            "source": SOURCE_ID,
            "source-layer": "transportation",
            "minzoom": 4,
            "filter": _road_filter("motorway"),
            "layout": {"line-cap": "round", "line-join": "round"},
            "paint": {
                "line-color": c["motorway_casing"],
                "line-width": ["interpolate", ["exponential", 1.4], ["zoom"], 4, 1.6, 18, 26],
            },
        },
        {
            "id": "road-motorway",
            "type": "line",
            "source": SOURCE_ID,
            "source-layer": "transportation",
            "minzoom": 4,
            "filter": _road_filter("motorway"),
            "layout": {"line-cap": "round", "line-join": "round"},
            "paint": {
                "line-color": c["motorway"],
                "line-width": ["interpolate", ["exponential", 1.4], ["zoom"], 4, 0.9, 18, 22],
            },
        },
        {
            "id": "boundary",
            "type": "line",
            "source": SOURCE_ID,
            "source-layer": "boundary",
            "filter": ["<=", ["get", "admin_level"], 4],
            "paint": {
                "line-color": c["boundary"],
                "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.6, 10, 1.8],
                "line-dasharray": [3, 2],
            },
        },
    ]


def _poi_layers(c: dict) -> list[dict]:
    """Subtle POI dots at high zoom — context, not clutter. No labels needed."""
    return [
        {
            "id": "poi-dot",
            "type": "circle",
            "source": SOURCE_ID,
            "source-layer": "poi",
            "minzoom": 15,
            "paint": {
                "circle-color": c["poi"],
                "circle-radius": ["interpolate", ["linear"], ["zoom"], 15, 1.5, 18, 3.5],
                "circle-opacity": 0.7,
            },
        },
    ]


def _label_layers(c: dict) -> list[dict]:
    """Text layers. Only emitted when glyphs are installed."""
    return [
        {
            "id": "road-label",
            "type": "symbol",
            "source": SOURCE_ID,
            "source-layer": "transportation_name",
            "minzoom": 12,
            "layout": {
                "symbol-placement": "line",
                "text-field": ["get", "name"],
                "text-font": FONT_STACK,
                "text-size": 11,
            },
            "paint": {
                "text-color": c["label"],
                "text-halo-color": c["label_halo"],
                "text-halo-width": 1.3,
            },
        },
        {
            "id": "place-label",
            "type": "symbol",
            "source": SOURCE_ID,
            "source-layer": "place",
            "layout": {
                "text-field": ["get", "name"],
                "text-font": FONT_STACK,
                "text-size": ["interpolate", ["linear"], ["zoom"], 4, 10, 10, 15, 14, 19],
                "text-max-width": 8,
            },
            "paint": {
                "text-color": c["label"],
                "text-halo-color": c["label_halo"],
                "text-halo-width": 1.5,
            },
        },
    ]


def style(region: str, tiles: MBTiles, base_url: str, theme: str | None = None) -> dict:
    """A complete MapLibre GL style for one region. No external references."""
    theme_name = resolve_theme(theme)
    c = THEMES[theme_name]

    layers = _fill_layers(c) + _road_layers(c) + _poi_layers(c)
    if fonts_installed():
        layers += _label_layers(c)

    spec: dict = {
        "version": 8,
        "name": f"Nucleus {theme_name.title()} — {tiles.name}",
        "metadata": {"nucleus:theme": theme_name},
        "sources": {
            SOURCE_ID: {
                "type": "vector",
                "url": f"{base_url}/maps/tiles/{region}/tilejson.json",
            }
        },
        "layers": layers,
    }
    if fonts_installed():
        spec["glyphs"] = f"{base_url}/maps/fonts/{{fontstack}}/{{range}}.pbf"

    return spec
