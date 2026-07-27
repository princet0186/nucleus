"""Models shared across response schemas.

``SanitizationMetadata`` lives here rather than in ``schemas.py`` because both
``schemas.py`` and ``map_schemas.py`` need it, and ``schemas.py`` already imports
from ``map_schemas``. Putting it in either one would close an import cycle.
"""

from pydantic import BaseModel, Field


class SanitizationMetadata(BaseModel):
    """What the PII sanitizer did at the cloud-egress boundary for this call.

    ``egress_preview`` is the tokenized text that actually left the device, so
    the UI can prove no identifier crossed the wire. When ``applied`` is False
    and the preview is empty, nothing was sent at all.
    """

    applied: bool = False
    fields_redacted: list[str] = Field(default_factory=list)
    egress_preview: str = ""
