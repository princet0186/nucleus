"""Let Gemini decide, from tokenized text, whether a map would help the answer.

This is the "Gemini as the brain" half of the map feature. The device already
runs a local regex intent detector (``backend/maps/intent``) that catches
explicit questions like "nearest hospital" with no egress at all. But a lot of
map-worthy situations are not phrased that way:

    "my guy took shrapnel to the leg, we're pinned in a compound"
    "vehicle rolled, two unconscious, closest place we can get them treated?"

Regex misses the intent; Gemini reads it instantly. So every mode that already
calls Gemini gets one extra field in its response schema — ``map_assist`` — and
Gemini fills it in the SAME call. No extra round-trip, no extra egress.

The privacy boundary is untouched. Gemini decides the *category* of help from
tokenized text ("show evac and medical facilities") and never sees a coordinate.
The device takes that category, adds the operator's real position (which never
left the device), and resolves the actual facilities against the offline index.
Brain in the cloud, hands on the device.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MapAssist(BaseModel):
    """Gemini's judgement on whether to open the map, and with what on it."""

    should_open: bool = Field(
        default=False,
        description="True only if showing nearby facilities on a map would materially help this answer.",
    )
    facility_kinds: list[str] = Field(
        default_factory=list,
        description=(
            "Which facility categories to plot. Use group names "
            "('medical', 'evac', 'support') or specific kinds "
            "('hospital', 'clinic', 'aid_station', 'pharmacy', 'helipad', "
            "'evac_point', 'casualty_collection_point', 'airfield', "
            "'fire_station', 'police', 'shelter', 'water_point', 'fuel'). "
            "Empty means 'all nearby facilities'."
        ),
    )
    wants_route: bool = Field(
        default=False,
        description="True if the operator needs to get to the facility (routing/bearing), not just locate it.",
    )
    reason: str = Field(
        default="",
        description="One short phrase on why the map helps, shown to the operator.",
    )


# Appended to a mode's system prompt. Kept terse: the schema field descriptions
# already carry the allowed values, so this only has to convey the WHEN and the
# hard privacy fact that keeps the model from asking for a location it cannot see.
MAP_ASSIST_INSTRUCTION = """

MAP ASSIST — decide if a map would help this answer:
- Set map_assist.should_open = true when knowing WHERE nearby facilities are
  would materially improve the answer or the plan: finding the nearest hospital,
  aid station, helipad or evacuation point; planning a casualty evacuation;
  staging resources for a mass-casualty event; or any question about getting a
  patient to care.
- Set map_assist.should_open = false for purely clinical or procedural questions
  ("how do I apply a tourniquet", "what dose of TXA") where a map adds nothing.
- When true, fill facility_kinds with the relevant categories and set wants_route
  if the operator has to travel there.
- You will NOT be given coordinates — positions appear only as tokens like
  [GRID_1]. Do not ask for a location and do not guess one. The device resolves
  the real facilities locally from the operator's own position. Your only job
  here is to judge whether a map helps and which facilities to show."""
