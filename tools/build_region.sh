#!/usr/bin/env bash
#
# Build one offline map region: vector tiles + facility index, from OpenStreetMap.
#
#   ./tools/build_region.sh <region-name> <geofabrik-area>
#   ./tools/build_region.sh kashmir india
#   ./tools/build_region.sh local     --osm-path=/data/extract.osm.pbf
#
# Produces, in data/tiles/:
#   <region>.mbtiles       vector tiles  (Planetiler, OpenMapTiles schema)
#   <region>.poi.sqlite    facility index (pyosmium -> SQLite R*Tree)
#
# Both derive from the SAME extract, so the pins always agree with the basemap.
#
# This is the only step in Nucleus that touches the network, and only to fetch
# public OpenStreetMap data. Once it has run, the device never needs a network
# for maps again. Run it before deployment, not in the field.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TILES_DIR="${TILES_DIR:-$REPO_ROOT/data/tiles}"
SOURCES_DIR="$REPO_ROOT/data/sources"
PLANETILER_JAR="$REPO_ROOT/tools/planetiler.jar"
PLANETILER_URL="https://github.com/onthegomap/planetiler/releases/latest/download/planetiler.jar"

# Zoom 14 is the standard OpenMapTiles ceiling: buildings and paths are present,
# and MapLibre overzooms past it for free. Raising it multiplies size for detail
# a field device cannot use.
MAX_ZOOM="${MAX_ZOOM:-14}"
JAVA_HEAP="${JAVA_HEAP:-4g}"
# The OpenMapTiles auxiliary sources (water polygons ~930 MB, Natural Earth
# ~430 MB) come from mirrors that throttle per connection. Splitting each file
# across parallel range requests gets past that; downloads resume, so a stopped
# run continues where it left off.
DOWNLOAD_THREADS="${DOWNLOAD_THREADS:-8}"

die() { echo "error: $*" >&2; exit 1; }

[ $# -ge 2 ] || die "usage: $0 <region-name> <geofabrik-area | --osm-path=FILE>"

REGION="$1"; shift
AREA_ARG="$1"; shift

[[ "$REGION" =~ ^[A-Za-z0-9_-]+$ ]] || die "region name must be [A-Za-z0-9_-]: $REGION"

command -v java >/dev/null || die "java is required for Planetiler (apt install openjdk-21-jre)"
[ -x "$REPO_ROOT/venv/bin/python3" ] && PY="$REPO_ROOT/venv/bin/python3" || PY="python3"

mkdir -p "$TILES_DIR" "$SOURCES_DIR"

# Planetiler resolves --download-dir relative to the working directory, so run
# from the repo root and pass it explicitly. Otherwise the extract lands
# somewhere the POI index step will not find it.
cd "$REPO_ROOT"

# -- 1. Planetiler jar ----------------------------------------------------
if [ ! -f "$PLANETILER_JAR" ]; then
  echo ">> Fetching Planetiler ..."
  curl -fL --progress-bar -o "$PLANETILER_JAR" "$PLANETILER_URL" \
    || die "could not download Planetiler; place planetiler.jar in tools/ manually"
fi

# Optional BOUNDS="min_lon,min_lat,max_lon,max_lat" clips a city out of a whole-
# country extract: Planetiler renders only tiles inside it, and the POI index is
# filtered to the same box. Without it the whole extract is built.
#   BOUNDS=76.80,28.35,77.40,28.90 ./tools/build_region.sh delhi --osm-path=india.osm.pbf
BOUNDS="${BOUNDS:-}"
PLANETILER_BOUNDS=()
POI_BBOX=()
if [ -n "$BOUNDS" ]; then
  PLANETILER_BOUNDS=(--bounds="$BOUNDS")
  POI_BBOX=(--bbox="$BOUNDS")
  echo ">> Clipping region to bounds: $BOUNDS"
fi

# -- 2. Vector tiles ------------------------------------------------------
MBTILES="$TILES_DIR/$REGION.mbtiles"
echo ">> Building tiles -> $MBTILES"

if [[ "$AREA_ARG" == --osm-path=* ]]; then
  OSM_PBF="${AREA_ARG#--osm-path=}"
  [ -f "$OSM_PBF" ] || die "no such extract: $OSM_PBF"
  # --download still applies to the OpenMapTiles *auxiliary* sources (water
  # polygons, Natural Earth, lake centerlines). They are required by the profile
  # regardless of the OSM extract, are fetched once, and are reused across every
  # region. --osm-path keeps the OSM source local; only the aux data is fetched.
  java "-Xmx$JAVA_HEAP" -jar "$PLANETILER_JAR" \
    --osm-path="$OSM_PBF" --download --download-dir="$SOURCES_DIR" \
    --download-threads="$DOWNLOAD_THREADS" "${PLANETILER_BOUNDS[@]}" \
    --output="$MBTILES" --maxzoom="$MAX_ZOOM" --force
else
  # Planetiler downloads the Geofabrik extract into data/sources/ and reuses it.
  java "-Xmx$JAVA_HEAP" -jar "$PLANETILER_JAR" \
    --download --area="$AREA_ARG" --download-dir="$SOURCES_DIR" \
    --download-threads="$DOWNLOAD_THREADS" "${PLANETILER_BOUNDS[@]}" \
    --output="$MBTILES" --maxzoom="$MAX_ZOOM" --force
  OSM_PBF="$SOURCES_DIR/${AREA_ARG}.osm.pbf"
fi

[ -f "$MBTILES" ] || die "Planetiler produced no tiles"

# -- 3. Facility index (same extract) -------------------------------------
POI_DB="$TILES_DIR/$REGION.poi.sqlite"
if [ -f "$OSM_PBF" ]; then
  echo ""
  echo ">> Building facility index -> $POI_DB"
  "$PY" "$REPO_ROOT/tools/build_poi_index.py" "$OSM_PBF" "$POI_DB" "${POI_BBOX[@]}"
else
  echo "warning: extract not found at $OSM_PBF; skipping facility index." >&2
  echo "         Nearest-facility search will be unavailable for '$REGION'." >&2
  echo "         Run: $PY tools/build_poi_index.py <extract.osm.pbf> $POI_DB" >&2
fi

# -- 4. Report ------------------------------------------------------------
echo ""
echo "Region '$REGION' installed:"
du -h "$MBTILES" | awk '{printf "  %-10s %s\n", $1, $2}'
[ -f "$POI_DB" ] && du -h "$POI_DB" | awk '{printf "  %-10s %s\n", $1, $2}'
echo ""
echo "Set MAPS_DEFAULT_REGION=$REGION in .env (or leave empty if it is the only region)."
echo "Verify with: curl -s localhost:8000/maps/status | python3 -m json.tool"
