"""Mass-casualty prioritization guidance -> planning model, strict JSON.

No identities or per-person records are produced — only event-level triage
prioritization guidance.
"""

from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.services.Gemini_Services.gemini_client import GenerationResult, generate_structured
from backend.services.Gemini_Services.map_assist import MAP_ASSIST_INSTRUCTION, MapAssist
from backend.services.Gemini_Services.system_prompts import MASCAL_SYSTEM_PROMPT


class TriagePriority(BaseModel):
    category: str
    estimated_count: str = "unknown"
    action: str = ""


class MascalGuidance(BaseModel):
    situation_summary: str
    triage_priorities: list[TriagePriority] = Field(default_factory=list)
    immediate_actions: list[str] = Field(default_factory=list)
    resource_allocation: list[str] = Field(default_factory=list)
    evacuation_priority: str = ""
    map_assist: MapAssist = Field(default_factory=MapAssist)


def generate_mascal(incident_description: str) -> GenerationResult:
    return generate_structured(
        prompt=incident_description,
        system_prompt=MASCAL_SYSTEM_PROMPT + MAP_ASSIST_INSTRUCTION,
        primary_model=settings.GEMINI_PLANNING_MODEL,
        fallback_model=settings.GEMINI_PLANNING_FALLBACK,
        response_schema=MascalGuidance,
        temperature=0.2,
    )
