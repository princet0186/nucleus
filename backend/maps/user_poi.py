"""Operator-added places, encrypted at rest and destroyed by secure_wipe.

"There is an evacuation centre here" is intelligence about your own operating
area. A captured device must not give it up, so every field of an operator pin —
including its coordinates — is Fernet-encrypted before it touches the disk.

That choice costs the spatial index. You cannot R*Tree a ciphertext, so
proximity search decrypts and scans linearly. The tradeoff is deliberate and it
is cheap: ``MAPS_USER_POI_LIMIT`` caps the table at a few thousand rows, and
scanning 5,000 Fernet blobs is single-digit milliseconds — nothing next to the
network round-trip the caller already paid. The OSM index next door keeps its
R*Tree because public map data needs no confidentiality.

Rows live in ``nucleus.db``, so the existing ``secure_wipe_db`` already
overwrites and unlinks them along with everything else. Connections are opened
per call rather than pooled: after a wipe the file is gone, and a cached handle
would keep writing into an unlinked inode instead of failing loudly.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, Iterator, Optional

from backend.core.config import settings
from backend.maps.facility import (
    OPERATOR_KINDS,
    SOURCE_OPERATOR,
    Facility,
    label_of,
)
from backend.maps.geo import haversine_km
from backend.services.encryption_layer import encryption_layer

MAX_NAME_LEN = 120
MAX_NOTE_LEN = 500

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS user_poi (
    id   TEXT PRIMARY KEY,
    blob TEXT NOT NULL
)
"""
_COUNT_SQL = "SELECT COUNT(*) FROM user_poi"


class UserPoiError(ValueError):
    """An operator pin was rejected: bad kind, bad position, or store full."""


@contextmanager
def _session() -> Iterator[sqlite3.Connection]:
    """A committed, closed-on-exit connection to nucleus.db.

    ``sqlite3.Connection.__enter__`` commits but does not close, so it cannot be
    used directly here: opening per call would leak a descriptor every time.
    """
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    try:
        # Journal mode stays at the DELETE default on purpose. WAL would leave
        # nucleus.db-wal behind, which secure_wipe_db does not overwrite.
        conn.execute(_CREATE_SQL)
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_facility(poi_id: str, record: dict) -> Facility:
    return Facility(
        id=poi_id,
        name=record["name"],
        kind=record["kind"],
        lat=record["lat"],
        lon=record["lon"],
        source=SOURCE_OPERATOR,
        verified=False,
        tags={},
        note=record.get("note", ""),
        created_at=record.get("created_at"),
    )


def _decrypt_all(conn: sqlite3.Connection) -> list[Facility]:
    """Every stored pin. Rows that fail to decrypt are skipped, not fatal.

    A row can only fail if MASTER_KEY changed or the blob was tampered with. One
    unreadable pin must not take down the whole map, so we drop it and warn.
    """
    facilities: list[Facility] = []
    unreadable = 0
    for poi_id, blob in conn.execute("SELECT id, blob FROM user_poi"):
        # InvalidToken, JSONDecodeError, KeyError — any of them means this one
        # row is lost, never that the map should fail.
        try:
            facilities.append(_to_facility(poi_id, json.loads(encryption_layer.decrypt(blob))))
        except Exception:  # noqa: BLE001
            unreadable += 1
    if unreadable:
        print(f"[MAPS] {unreadable} operator POI(s) could not be decrypted; skipped")
    return facilities


# -- writes --------------------------------------------------------------


def add(
    name: str,
    kind: str,
    lat: float,
    lon: float,
    note: str = "",
) -> Facility:
    """Store an operator pin. Raises UserPoiError on invalid input or a full store."""
    name = (name or "").strip()
    if not name:
        raise UserPoiError("A name is required.")
    if len(name) > MAX_NAME_LEN:
        raise UserPoiError(f"Name exceeds {MAX_NAME_LEN} characters.")

    kind = (kind or "").strip().lower()
    if kind not in OPERATOR_KINDS:
        allowed = ", ".join(sorted(OPERATOR_KINDS))
        raise UserPoiError(f"Kind must be one of: {allowed}")

    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise UserPoiError(f"Position out of range: {lat}, {lon}")

    note = (note or "").strip()[:MAX_NOTE_LEN]

    with _session() as conn:
        stored = conn.execute(_COUNT_SQL).fetchone()[0]
        if stored >= settings.MAPS_USER_POI_LIMIT:
            raise UserPoiError(
                f"Operator POI store is full ({settings.MAPS_USER_POI_LIMIT}). "
                "Delete unused pins first."
            )

        poi_id = f"op:{uuid.uuid4().hex}"
        record = {
            "name": name,
            "kind": kind,
            "lat": float(lat),
            "lon": float(lon),
            "note": note,
            "created_at": _now(),
        }
        conn.execute(
            "INSERT INTO user_poi (id, blob) VALUES (?, ?)",
            (poi_id, encryption_layer.encrypt(json.dumps(record))),
        )

    return _to_facility(poi_id, record)


def delete(poi_id: str) -> bool:
    """Remove one pin. Returns False when it was not there."""
    with _session() as conn:
        cursor = conn.execute("DELETE FROM user_poi WHERE id = ?", (poi_id,))
        return cursor.rowcount > 0


def wipe() -> int:
    """Delete every operator pin. Returns how many were removed.

    Clears the rows; ``secure_wipe_db`` is what overwrites the bytes. Use this to
    drop annotations without destroying the rest of the application state.
    """
    with _session() as conn:
        removed = int(conn.execute(_COUNT_SQL).fetchone()[0])
        conn.execute("DELETE FROM user_poi")

    _vacuum()
    return removed


def _vacuum() -> None:
    """Release freed pages so deleted blobs are not left in the file's slack.

    Must run outside a transaction and needs an exclusive lock, so it gets its
    own autocommit connection. Best-effort: if SQLAlchemy is mid-write the lock
    is unavailable, and the rows are already gone either way.
    """
    conn = sqlite3.connect(settings.DB_PATH, isolation_level=None)
    try:
        conn.execute("VACUUM")
    except sqlite3.Error as exc:
        print(f"[MAPS] VACUUM after POI wipe skipped: {exc}")
    finally:
        conn.close()


# -- reads ---------------------------------------------------------------


def count() -> int:
    with _session() as conn:
        return int(conn.execute(_COUNT_SQL).fetchone()[0])


def list_all() -> list[Facility]:
    with _session() as conn:
        facilities = _decrypt_all(conn)
    facilities.sort(key=lambda f: f.created_at or "", reverse=True)
    return facilities


def within(
    lat: float,
    lon: float,
    radius_km: float,
    kinds: Iterable[str] = (),
    limit: int = 200,
) -> list[tuple[Facility, float]]:
    """Operator pins within ``radius_km``, as (facility, distance_km), nearest first.

    Linear scan by design — see the module docstring.
    """
    wanted = set(kinds)
    with _session() as conn:
        facilities = _decrypt_all(conn)

    hits: list[tuple[Facility, float]] = []
    for facility in facilities:
        if wanted and facility.kind not in wanted:
            continue
        distance = haversine_km(lat, lon, facility.lat, facility.lon)
        if distance <= radius_km:
            hits.append((facility, distance))

    hits.sort(key=lambda hit: hit[1])
    return hits[:limit]


def get(poi_id: str) -> Optional[Facility]:
    with _session() as conn:
        row = conn.execute("SELECT id, blob FROM user_poi WHERE id = ?", (poi_id,)).fetchone()
    if not row:
        return None
    try:
        return _to_facility(row[0], json.loads(encryption_layer.decrypt(row[1])))
    except Exception:  # noqa: BLE001 — an undecryptable pin reads as a missing pin
        return None


def operator_kind_choices() -> list[dict[str, str]]:
    """What the UI may offer in the 'add a place' form."""
    return [{"kind": kind, "label": label_of(kind)} for kind in sorted(OPERATOR_KINDS)]
