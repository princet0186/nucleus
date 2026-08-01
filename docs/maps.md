# Offline Maps

OpenStreetMap vector tiles, nearest-facility search, and encrypted operator pins
— all resolved on-device. A map question is answered with the radio off.

---

## Why the cloud model cannot answer a map question

This is the load-bearing fact of the whole design, so it goes first.

Every prompt leaving Nucleus passes through the egress sanitizer
(`backend/services/privacy/sanitizer.py`), which tokenizes MGRS grids and
coordinates. Ask *"nearest evacuation centre to 42S WD 1234 5678"* and Gemini
receives:

```
nearest evacuation centre to [GRID_1]
```

It has no coordinate. It has no offline OSM data. It **cannot** resolve the
question, and it should not be able to — a cloud provider learning where a unit
is standing is precisely the threat this application exists to prevent.

So the work happens locally:

```
question
  → intent detection      regex, on-device, no egress          intent.py
  → origin                MGRS grid or lat/lon                 geo.py
  → facilities            SQLite R*Tree over OSM + operator    poi_index.py
  → route                 straight-line today                  routing.py
  → map payload           opens the sidebar                    resolver.py
```

Gemini is invited afterwards, and only to write a sentence, from a fact sheet
built entirely of tokens:

```
Operator question: nearest evacuation point to [GRID_1]

Facilities resolved on-device:
1. [POI_1] - Evacuation point - GRID [GRID_2] - 0.1 km NE - source: operator pin (UNVERIFIED) - has an operator note (shown on device)

Route to nearest: 0.1 km, bearing 36 (NE), straight-line (no road network, NO travel time available).
```

Rehydration restores the real names and grids on-device after the round-trip.
Set `MAPS_AI_PROSE=false` to skip this step entirely and answer from a
deterministic local template — zero egress, works with the radio off.

If the model references a facility that was not on the fact sheet (an invented
`[POI_9]`), the answer is **discarded whole** and the local template is used. A
fabricated token is a fabricated facility, and it would read perfectly while
pointing a casualty at a place that does not exist.

---

## Quick start (no downloads)

A region is two independent files, and **either one alone is useful**:

| File | Gives you | Size |
|---|---|---|
| `<region>.mbtiles` | a basemap to look at | 100s of MB – GBs |
| `<region>.poi.sqlite` | "nearest hospital", grid + bearing | a few MB |

So you can have working facility search with no basemap under it. The pins and
bearings are exact; there is simply no terrain drawn. That is a supported field
configuration, not a broken one — and it is the fastest way to try the thing:

```bash
python tools/build_poi_index.py tools/demo_region.osm data/tiles/demo.poi.sqlite
```

`tools/demo_region.osm` is invented data around New Delhi (hospitals, helipads,
a landing site, a clinic mapped as a building). Set your position to
`28.6139, 77.2090` and ask *"where is the nearest evacuation point?"*.

## Building a real region

Requires Java (Planetiler) and the build-only Python deps. Neither is needed to
*run* Nucleus — the field device serves prebuilt files.

```bash
pip install -r requirements-tools.txt
./tools/build_region.sh <region-name> <geofabrik-area>

# smallest real region — good for a first run, ~1 minute
./tools/build_region.sh monaco monaco

# examples
./tools/build_region.sh kashmir india
./tools/build_region.sh local --osm-path=/data/my-extract.osm.pbf
```

The script downloads Planetiler (~100 MB) on first use and then the Geofabrik
extract. This is the **only** step that touches the network, and only to fetch
public OpenStreetMap data. Run it before deployment, never in the field.

Both outputs derive from the same extract, so pins always agree with the
basemap. Neither is wiped: they are public data an adversary could download
themselves, and destroying them would cost the operator their map for nothing.

Rough sizes at `maxzoom=14`: a district is ~80 MB, a large state ~1–2 GB.

### Labels (optional)

MapLibre cannot draw text without glyph PBFs. Drop a font directory at
`data/tiles/fonts/Noto Sans Regular/0-255.pbf` (etc.) and the generated style
grows `road-label` and `place-label` layers automatically. With no fonts
installed the map renders unlabelled rather than emitting 404s — and never
reaches a CDN for a glyph.

## Themes

The MapLibre style is **generated** from a palette, not shipped as a static
asset, so the look is fully customizable without touching layer logic. Two
themes ship:

| Theme | Look | For |
|---|---|---|
| `day` (default) | light street map — white roads, amber motorways, blue water | daylight use, familiar road-atlas feel |
| `night` | dark, low-emission — muted roads on near-black | night operations / EMCON |

Select per request with `?theme=`:

```
GET /maps/tiles/{region}/style.json?theme=day
GET /maps/tiles/{region}/style.json?theme=night
```

The frontend map has a 🌙/☀️ toggle (remembered per device). The server-side
default is `MAPS_STYLE_THEME` in `.env`. A new theme is ~25 hex values added to
`THEMES` in [`backend/maps/style.py`](../backend/maps/style.py) — every colour
the renderer uses comes from the active palette, so adding a look never touches
a layer definition.

---

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/maps/status` | What is installed and what works right now |
| `GET` | `/maps/regions` | Installed regions and the default |
| `GET` | `/maps/tiles/{region}/tilejson.json` | TileJSON 3.0.0 |
| `GET` | `/maps/tiles/{region}/style.json` | Self-contained MapLibre style |
| `GET` | `/maps/tiles/{region}/{z}/{x}/{y}.pbf` | One vector tile |
| `GET` | `/maps/fonts/{fontstack}/{range}.pbf` | Glyphs, from disk |
| `POST` | `/maps/search` | Nearest facilities to a position |
| `POST` | `/maps/resolve` | Interpret a chat question |
| `GET`/`POST` | `/maps/poi` | List / create operator pins |
| `DELETE` | `/maps/poi/{id}` | Delete one pin |
| `POST` | `/maps/poi/wipe` | Delete all pins |

An absent tile returns **204**, not 404: empty ocean is a legitimate answer, and
MapLibre retries on 404.

### Frontend: opening the map sidebar

`POST /nucleus/query` gains an optional `origin` (MGRS grid or `"lat,lon"`).
When the question needs a map, the response carries a `map` object and
`mode: "map"`. Its presence is the signal to open the sidebar.

```jsonc
{
  "mode": "map",
  "response": "**Nearest: Evac point Alpha (Evacuation point) — GRID …**",
  "sanitization": null,          // null = nothing was transmitted
  "map": {
    "open_map": true,
    "needs_origin": false,       // true = ask the operator for a grid
    "origin": { "lat": 28.61, "lon": 77.20, "grid": "43RGM1598067204" },
    "kinds": ["evac_point"],
    "wants_route": false,
    "facilities": [ { "name": "…", "grid": "…", "distance_km": 0.084,
                      "compass": "NE", "source": "operator",
                      "verified": false, "note": "…" } ],
    "route": { "distance_km": 0.084, "bearing_deg": 36.0,
               "duration_min": null, "is_straight_line": true,
               "geometry": [[77.209, 28.6139], [77.2095, 28.6145]] },
    "warning": ""
  }
}
```

`needs_origin: true` is a normal outcome, not an error. "Where's the nearest
hospital" is a fine question the device cannot answer until it knows where the
operator is standing. Prompt for a grid and ask again.

### Reading `sanitization`

| Value | Meaning |
|---|---|
| `null` | Nothing was transmitted. The radio stayed silent. |
| `applied: true` | A tokenized prompt was sent. `egress_preview` is the literal text. |

A fallback to the offline template after a failed AI call still reports the
egress, because the prompt did go out even though its answer was thrown away.

---

## Operator pins

An operator can record a place they found — *"there is an evacuation centre
here"* — and it ranks alongside OSM facilities on every later search.

Every field, **including the coordinates**, is Fernet-encrypted before it
touches the disk. "Evac centre here" is intelligence about your own operating
area; a captured device must not give it up. That costs the spatial index — you
cannot R*Tree a ciphertext — so proximity search decrypts and scans linearly.
At `MAPS_USER_POI_LIMIT` (5000) rows that is single-digit milliseconds.

Pins live in `nucleus.db`, so the existing `secure_wipe_db` destroys them along
with everything else. The OSM basemap survives.

Results always carry provenance. An operator pin is one person's word:

```
0.08 km NE   Evac point Alpha    evac_point  [UNVERIFIED]  tarmac, marked with green smoke
1.32 km SW   Unnamed helipad     helipad     [osm]
```

Operators may only create the kinds in `OPERATOR_KINDS` (`evac_point`,
`casualty_collection_point`, `aid_station`, `helipad`, `shelter`,
`water_point`). Pinning a "hospital" is rejected — it would launder an
unverified pin into an authoritative one.

The operator's free-text **note is never sent to the cloud**. It is the most
sensitive string in the payload and the reason pins are encrypted at all; the
model is told only that a note exists, and the medic reads it on-device.

---

## Routing

`MAPS_ROUTING_PROVIDER=straight_line` is the only provider today. It answers
what the 9-line MEDEVAC actually asks — *how far, on what bearing* — with no
container and no graph build.

**It never reports an ETA.** `duration_min` is always `null`. Dividing a
crow-flight distance by an assumed speed produces a number that looks like an
ETA and is not one, and in a MEDEVAC that number gets read over a radio. Road
distance typically runs 20–40% longer; terrain can make it far worse. The
straight-line distance is a lower bound and the response says so.

A `ValhallaProvider` (road distance, real ETA, map-matched live traces, re-route
on deviation) drops in behind the same `RouteProvider` interface without moving
the API contract. That decision belongs to the live-tracking phase.

---

## Configuration

```bash
TILES_DIR=./data/tiles           # where regions live
FONTS_DIR=./data/tiles/fonts     # glyph PBFs (optional)
MAPS_DEFAULT_REGION=             # empty = auto-select the only installed region
MAPS_SEARCH_RADIUS_KM=25
MAPS_MAX_SEARCH_RADIUS_KM=200
MAPS_MAX_RESULTS=10
MAPS_USER_POI_LIMIT=5000
MAPS_ROUTING_PROVIDER=straight_line
MAPS_AI_PROSE=true               # false = deterministic template, zero egress
MAPS_AI_TIMEOUT_S=8.0            # deadline before falling back to the template
MAPS_STYLE_THEME=day             # default basemap look: day (light) | night (dark)
```

---

## Frontend

`/map` is a standalone page for working the layer directly. In the chat, a map
question opens the same panel as a right sidebar, and your position is kept in
`localStorage` so you do not retype a grid every turn.

Two things the UI will not do:

- **Imply a road route.** The line is dashed and captioned straight-line,
  because that is what was computed.
- **Flatten provenance.** An operator pin is drawn as a dashed ring, listed with
  an `UNVERIFIED` badge, and never rendered like a surveyed facility.

Map answers are **never** written to the on-device response cache. The cache key
is `(mode, query)` and carries no position, so a cached "nearest hospital" would
be replayed after the operator had moved. Recomputing a local lookup is free.

---

## Not built yet

Live tracking, and therefore the routing engine that serves it. The seam is in
place (`routing.RouteProvider`), and position is accepted per-request rather
than streamed, so neither choice is baked in.
