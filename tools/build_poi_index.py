#!/usr/bin/env python3
"""Build a facility index from an OpenStreetMap extract.

    python tools/build_poi_index.py <input.osm.pbf> <output.poi.sqlite>

Streams the extract with pyosmium (constant memory, no full graph in RAM) and
writes a SQLite R*Tree that ``backend/maps/poi_index.py`` reads at query time.
Run it against the *same* extract that produced the region's tiles, or the pins
will disagree with the basemap.

Classification is not duplicated here: it imports ``OSM_TAG_MAP`` from
``backend.maps.facility``, so the index can never be built with tags the runtime
search does not understand.

Coverage note: nodes and ways are indexed. A way's position is the mean of its
node coordinates — for a hospital building or a helipad polygon that is the
right pin to within a few metres. Multipolygon *relations* are skipped; they are
rare for the facility types we index, and supporting them would mean a second
pass over the file for a handful of extra rows. Skipped counts are reported so
the tradeoff is visible rather than silent.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Import from the application so the taxonomy has exactly one definition.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.maps.facility import OSM_TAG_MAP, USEFUL_TAGS, kind_of, label_of  # noqa: E402
from backend.maps.poi_index import CREATE_SQL, SCHEMA_VERSION  # noqa: E402

BATCH_SIZE = 10_000


def _name_for(tags: dict, kind: str) -> str:
    """Every row gets a name. An unnamed helipad is still a landing site."""
    for key in ("name", "name:en", "official_name", "operator"):
        value = tags.get(key)
        if value and value.strip():
            return value.strip()[:200]
    return f"Unnamed {label_of(kind).lower()}"


def _useful(tags: dict) -> dict:
    return {key: tags[key] for key in USEFUL_TAGS if key in tags}


def _way_centroid(way) -> tuple[float, float] | None:
    """Mean of a way's node coordinates. None when locations are unresolved."""
    total_lat = total_lon = 0.0
    count = 0
    for node in way.nodes:
        try:
            location = node.location
            if not location.valid():
                continue
            total_lat += location.lat
            total_lon += location.lon
            count += 1
        except Exception:  # noqa: BLE001 — osmium raises on unresolved locations
            continue
    if count == 0:
        return None
    return total_lat / count, total_lon / count


def _in_bbox(lat: float, lon: float, bbox: tuple[float, float, float, float] | None) -> bool:
    """True when a point is inside (min_lon, min_lat, max_lon, max_lat), or no bbox."""
    if bbox is None:
        return True
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def build(
    source: Path,
    target: Path,
    bbox: tuple[float, float, float, float] | None = None,
) -> dict:
    import osmium  # imported late so --help works without the build-only dep
    import osmium.filter  # noqa: F401 — KeyFilter lives in this submodule

    if target.exists():
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(target)
    conn.executescript(CREATE_SQL)

    rows: list[tuple] = []
    stats: Counter = Counter()
    next_id = 1

    def flush() -> None:
        if not rows:
            return
        conn.executemany(
            "INSERT INTO poi (id, osm_type, osm_id, name, kind, lat, lon, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.executemany(
            "INSERT INTO poi_rtree (id, min_lat, max_lat, min_lon, max_lon) "
            "VALUES (?, ?, ?, ?, ?)",
            [(row[0], row[5], row[5], row[6], row[6]) for row in rows],
        )
        conn.commit()
        rows.clear()

    # Pre-filter in C++ so the Python loop only sees objects carrying a key we
    # classify on. Without it, indexing a facility index from a country-sized
    # extract runs a Python callback over every one of ~200M objects — minutes of
    # pure overhead. KeyFilter drops the untagged 99% before they cross into
    # Python. Node locations are still gathered for every node (with_locations
    # runs independently), so way centroids remain correct.
    filter_keys = sorted({key for key, _, _ in OSM_TAG_MAP})
    processor = (
        osmium.FileProcessor(str(source))
        .with_locations()
        .with_filter(osmium.filter.KeyFilter(*filter_keys))
    )

    for obj in processor:
        tags = dict(obj.tags)
        kind = kind_of(tags)
        if kind is None:
            continue

        if isinstance(obj, osmium.osm.Node):
            osm_type = "node"
            position = (obj.location.lat, obj.location.lon)
        elif isinstance(obj, osmium.osm.Way):
            osm_type = "way"
            position = _way_centroid(obj)
            if position is None:
                stats["skipped_unresolved_way"] += 1
                continue
        else:
            stats["skipped_relation"] += 1
            continue

        lat, lon = position
        # Clip to the region of interest. Lets a city index be cut from a whole-
        # country extract without a separate osmium extract step.
        if not _in_bbox(lat, lon, bbox):
            stats["skipped_outside_bbox"] += 1
            continue

        rows.append(
            (
                next_id,
                osm_type,
                obj.id,
                _name_for(tags, kind),
                kind,
                lat,
                lon,
                json.dumps(_useful(tags), separators=(",", ":")),
            )
        )
        stats[kind] += 1
        next_id += 1

        if len(rows) >= BATCH_SIZE:
            flush()

    flush()

    indexed = next_id - 1
    conn.executemany(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        [
            ("schema_version", SCHEMA_VERSION),
            ("source", source.name),
            ("built_at", datetime.now(timezone.utc).isoformat()),
            ("facility_count", str(indexed)),
            ("attribution", "© OpenStreetMap contributors (ODbL)"),
        ],
    )
    conn.commit()
    conn.execute("ANALYZE")
    conn.close()

    return {"indexed": indexed, "by_kind": dict(stats)}


def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = [float(p) for p in raw.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("bbox must be min_lon,min_lat,max_lon,max_lat")
    return tuple(parts)  # type: ignore[return-value]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="Input .osm.pbf (or .osm XML)")
    parser.add_argument("target", type=Path, help="Output .poi.sqlite")
    parser.add_argument(
        "--bbox",
        type=str,
        default=None,
        help="Clip to min_lon,min_lat,max_lon,max_lat (cut a city from a country extract)",
    )
    args = parser.parse_args()

    if not args.source.is_file():
        print(f"error: no such file: {args.source}", file=sys.stderr)
        return 1

    bbox = _parse_bbox(args.bbox)
    print(f"Indexing facilities from {args.source} ...")
    if bbox:
        print(f"  clipped to bbox {bbox}")
    result = build(args.source, args.target, bbox=bbox)

    skipped = {k: v for k, v in result["by_kind"].items() if k.startswith("skipped_")}
    kinds = {k: v for k, v in result["by_kind"].items() if not k.startswith("skipped_")}

    print(f"\nIndexed {result['indexed']} facilities -> {args.target}")
    for kind, count in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"  {count:7d}  {kind}")
    for reason, count in sorted(skipped.items()):
        print(f"  skipped {count} ({reason.removeprefix('skipped_')})")

    if result["indexed"] == 0:
        print("\nwarning: no facilities found. Wrong extract, or wrong area?", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
