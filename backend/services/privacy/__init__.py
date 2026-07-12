"""Privacy layer: deterministic PII sanitization at the cloud-egress boundary.

Design: identifiers are replaced with indexed tokens (``[GRID-1]``) before any
text leaves the device; a per-request reversible map restores real values into
the response locally. The cloud provider only ever sees tokens.

Rules-first (regex/gazetteer, no ML) so redaction is deterministic, auditable,
and works fully offline. The parked DP/PATE modules in ``backend/services``
address a different threat (aggregate-statistics release) and are not part of
this boundary.
"""

from backend.services.privacy.sanitizer import extract_facts, rehydrate, sanitize

__all__ = ["sanitize", "rehydrate", "extract_facts"]
