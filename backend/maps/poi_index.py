"""Read-only spatial index over OpenStreetMap facilities.

Built offline by ``tools/build_poi_index.py`` from the same ``.osm.pbf`` that
produced the region's tiles, so the pins always agree with the basemap.

The index is a SQLite R*Tree. Python ships with R*Tree compiled in, so nearest-
facility search costs zero runtime dependencies — which matters on a field
device that must not reach the network to answer "where is the nearest
hospital".

Search is bbox-then-haversine: the R*Tree narrows millions of rows to a handful
using 32-bit float bounds (it rounds *outward*, so it never drops a candidate),
then exact spherical distance ranks the survivors.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Iterable, Optional

from backend.maps.facility import SOURCE_OSM, Facility
from backend.maps.geo import bbox_around, haversine_km

SCHEMA_VERSION = "1"


class PoiIndexError(RuntimeError):
    """The POI index is missing, unreadable, or built by an incompatible version."""


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS poi (
    id       INTEGER PRIMARY KEY,
    osm_type TEXT NOT NULL,
    osm_id   INTEGER NOT NULL,
    name     TEXT NOT NULL,
    kind     TEXT NOT NULL,
    lat      REAL NOT NULL,
    lon      REAL NOT NULL,
    tags     TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS poi_kind_idx ON poi (kind);
CREATE VIRTUAL TABLE IF NOT EXISTS poi_rtree USING rtree (
    id, min_lat, max_lat, min_lon, max_lon
);
"""


class PoiIndex:
    """One region's facility index. Opened read-only, connection cached per thread."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise PoiIndexError(f"No such POI index: {self.path}")
        self._local = threading.local()
        self._verify()

    def _conn(self) -> sqlite3.Connection:
        conn: Optional[sqlite3.Connection] = getattr(self._local, "conn", None)
        if conn is None:
            try:
                conn = sqlite3.connect(
                    f"file:{self.path}?mode=ro", uri=True, check_same_thread=False
                )
            except sqlite3.Error as exc:
                raise PoiIndexError(f"Cannot open {self.path}: {exc}") from exc
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _verify(self) -> None:
        try:
            row = self._conn().execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
        except sqlite3.Error as exc:
            raise PoiIndexError(f"{self.path.name} is not a POI index: {exc}") from exc

        found = row["value"] if row else None
        if found != SCHEMA_VERSION:
            raise PoiIndexError(
                f"{self.path.name} has schema version {found!r}, expected "
                f"{SCHEMA_VERSION!r}. Rebuild with tools/build_poi_index.py."
            )

    # -- reads -----------------------------------------------------------

    def count(self) -> int:
        return int(self._conn().execute("SELECT COUNT(*) FROM poi").fetchone()[0])

    def meta(self) -> dict[str, str]:
        rows = self._conn().execute("SELECT key, value FROM meta").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def bounds(self) -> Optional[tuple[float, float, float, float]]:
        """(min_lat, max_lat, min_lon, max_lon) over every facility, or None if empty.

        Lets a POI-only region (no basemap) still tell the map where to look, so
        the view opens on the facilities instead of the whole globe.
        """
        row = self._conn().execute(
            "SELECT MIN(lat), MAX(lat), MIN(lon), MAX(lon) FROM poi"
        ).fetchone()
        if not row or row[0] is None:
            return None
        return (float(row[0]), float(row[1]), float(row[2]), float(row[3]))

    def center(self) -> Optional[tuple[float, float]]:
        """(lat, lon) midpoint of the facility bounds, or None if empty."""
        box = self.bounds()
        if box is None:
            return None
        min_lat, max_lat, min_lon, max_lon = box
        return ((min_lat + max_lat) / 2, (min_lon + max_lon) / 2)

    def all(self, limit: int = 5000) -> list[Facility]:
        """Every indexed facility, for map overview (no position, no ranking)."""
        rows = self._conn().execute(
            "SELECT id, osm_type, osm_id, name, kind, lat, lon, tags "
            "FROM poi LIMIT ?",
            (max(1, limit),),
        ).fetchall()
        return [self._to_facility(row) for row in rows]

    def within(
        self,
        lat: float,
        lon: float,
        radius_km: float,
        kinds: Iterable[str] = (),
        limit: int = 200,
    ) -> list[tuple[Facility, float]]:
        """Facilities within ``radius_km``, as (facility, distance_km), nearest first.

        ``limit`` bounds the *candidate* rows pulled from SQLite, not the final
        answer — callers rank and truncate. It exists so a query centred on a
        dense city cannot pull 50k rows into memory.
        """
        min_lat, max_lat, min_lon, max_lon = bbox_around(lat, lon, radius_km)

        sql = [
            "SELECT p.id, p.osm_type, p.osm_id, p.name, p.kind, p.lat, p.lon, p.tags",
            "FROM poi_rtree r JOIN poi p ON p.id = r.id",
            "WHERE r.max_lat >= ? AND r.min_lat <= ?",
            "  AND r.max_lon >= ? AND r.min_lon <= ?",
        ]
        params: list = [min_lat, max_lat, min_lon, max_lon]

        kind_list = tuple(kinds)
        if kind_list:
            sql.append(f"AND p.kind IN ({','.join('?' * len(kind_list))})")
            params.extend(kind_list)
        sql.append("LIMIT ?")
        params.append(max(1, limit))

        rows = self._conn().execute("\n".join(sql), params).fetchall()

        hits: list[tuple[Facility, float]] = []
        for row in rows:
            distance = haversine_km(lat, lon, row["lat"], row["lon"])
            if distance > radius_km:  # bbox corners lie outside the circle
                continue
            hits.append((self._to_facility(row), distance))

        hits.sort(key=lambda hit: hit[1])
        return hits

    @staticmethod
    def _to_facility(row: sqlite3.Row) -> Facility:
        try:
            tags = json.loads(row["tags"])
        except (json.JSONDecodeError, TypeError):
            tags = {}
        return Facility(
            id=f"osm:{row['osm_type']}/{row['osm_id']}",
            name=row["name"],
            kind=row["kind"],
            lat=row["lat"],
            lon=row["lon"],
            source=SOURCE_OSM,
            verified=True,
            tags=tags,
        )
