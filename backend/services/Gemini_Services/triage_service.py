"""Individual TCCC triage -> planning model, strict JSON."""

from typing import Optional

from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.services.Gemini_Services.gemini_client import GenerationResult, generate_structured
from backend.services.Gemini_Services.map_assist import MAP_ASSIST_INSTRUCTION, MapAssist
from backend.services.Gemini_Services.system_prompts import TRIAGE_SYSTEM_PROMPT


class TreatmentProtocol(BaseModel):
    priority: str = ""
    immediate_actions: list[str] = Field(default_factory=list)
    evacuation: str = ""


class TriageAnalysis(BaseModel):
    triage_category: str
    confidence_reasoning: str
    treatment_protocol: TreatmentProtocol = Field(default_factory=TreatmentProtocol)
    recommended_drugs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    map_assist: MapAssist = Field(default_factory=MapAssist)


def generate_triage(
    injury_description: str, patient_demographics: Optional[dict] = None
) -> GenerationResult:
    prompt = injury_description
    if patient_demographics:
        demo = ", ".join(f"{k}: {v}" for k, v in patient_demographics.items())
        prompt = f"{injury_description}\n\nPatient demographics: {demo}"
    return generate_structured(
        prompt=prompt,
        system_prompt=TRIAGE_SYSTEM_PROMPT + MAP_ASSIST_INSTRUCTION,
        primary_model=settings.GEMINI_PLANNING_MODEL,
        fallback_model=settings.GEMINI_PLANNING_FALLBACK,
        response_schema=TriageAnalysis,
        temperature=0.2,
    )
