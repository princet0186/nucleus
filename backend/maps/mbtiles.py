"""Read-only MBTiles reader for vector tiles.

MBTiles is a SQLite container (mapbox/mbtiles-spec). Two details bite:

1. ``tile_row`` is TMS, whose origin is bottom-left; web clients speak XYZ,
   whose origin is top-left. The row must be flipped on every read.
2. Planetiler and tippecanoe store vector tiles gzip-compressed. We serve those
   bytes verbatim with ``Content-Encoding: gzip`` rather than paying to
   decompress and recompress a blob the browser will just re-inflate.

Connections are opened read-only (``mode=ro``) and cached per thread, because
FastAPI runs sync path operations in a bounded worker pool and a SQLite
connection may not cross threads.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

_GZIP_MAGIC = b"\x1f\x8b"

DEFAULT_ATTRIBUTION = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'


class MBTilesError(RuntimeError):
    """The MBTiles file is missing, unreadable, or not a tile container."""


def is_gzipped(data: bytes) -> bool:
    return data[:2] == _GZIP_MAGIC


def tile_etag(data: bytes) -> str:
    """Content-addressed ETag. blake2b-64 is ~3x faster than md5 and non-crypto here."""
    return f'"{hashlib.blake2b(data, digest_size=8).hexdigest()}"'


class MBTiles:
    """One installed region, backed by a single ``.mbtiles`` file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise MBTilesError(f"No such MBTiles file: {self.path}")
        self._local = threading.local()
        self.metadata = self._load_metadata()

        fmt = self.metadata.get("format", "").lower()
        if not fmt:
            raise MBTilesError(f"{self.path.name}: metadata table has no 'format' row")
        self.format = fmt

    # -- connection ------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        conn: Optional[sqlite3.Connection] = getattr(self._local, "conn", None)
        if conn is None:
            try:
                conn = sqlite3.connect(
                    f"file:{self.path}?mode=ro", uri=True, check_same_thread=False
                )
            except sqlite3.Error as exc:
                raise MBTilesError(f"Cannot open {self.path}: {exc}") from exc
            self._local.conn = conn
        return conn

    def _load_metadata(self) -> dict[str, str]:
        try:
            rows = self._conn().execute("SELECT name, value FROM metadata").fetchall()
        except sqlite3.Error as exc:
            raise MBTilesError(f"{self.path.name} is not a valid MBTiles file: {exc}") from exc
        return {str(name): str(value) for name, value in rows}

    # -- typed metadata accessors ----------------------------------------

    @property
    def is_vector(self) -> bool:
        return self.format in ("pbf", "mvt")

    @property
    def name(self) -> str:
        return self.metadata.get("name", self.path.stem)

    @property
    def minzoom(self) -> int:
        return int(self.metadata.get("minzoom", 0))

    @property
    def maxzoom(self) -> int:
        return int(self.metadata.get("maxzoom", 14))

    @property
    def attribution(self) -> str:
        return self.metadata.get("attribution") or DEFAULT_ATTRIBUTION

    @property
    def bounds(self) -> list[float]:
        """[west, south, east, north]; whole-world when the file omits it."""
        return self._floats("bounds", 4) or [-180.0, -85.0511, 180.0, 85.0511]

    @property
    def center(self) -> list[float]:
        """[lon, lat, zoom]; derived from bounds when absent."""
        center = self._floats("center", 3)
        if center:
            return center
        west, south, east, north = self.bounds
        return [(west + east) / 2, (south + north) / 2, float(self.minzoom)]

    @property
    def vector_layers(self) -> list[dict[str, Any]]:
        """Layer descriptors from the ``json`` metadata row (required by TileJSON 3)."""
        raw = self.metadata.get("json")
        if not raw:
            return []
        try:
            return json.loads(raw).get("vector_layers", [])
        except (json.JSONDecodeError, AttributeError):
            return []

    def _floats(self, key: str, expected: int) -> Optional[list[float]]:
        raw = self.metadata.get(key)
        if not raw:
            return None
        try:
            values = [float(part) for part in raw.split(",")]
        except ValueError:
            return None
        return values if len(values) == expected else None

    # -- tiles -----------------------------------------------------------

    def tile(self, z: int, x: int, y: int) -> Optional[bytes]:
        """Fetch an XYZ tile. Returns None when the tile is absent (a valid empty area)."""
        side = 1 << z
        if z < 0 or not (0 <= x < side) or not (0 <= y < side):
            return None

        row = self._conn().execute(
            "SELECT tile_data FROM tiles "
            "WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
            (z, x, side - 1 - y),  # XYZ -> TMS
        ).fetchone()
        return bytes(row[0]) if row and row[0] is not None else None
