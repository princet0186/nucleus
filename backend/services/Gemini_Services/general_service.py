"""General tactical query -> fast instant model, strict JSON."""

from typing import Optional

from pydantic import BaseModel, Field

from backend.core.config import settings
from backend.services.Gemini_Services.gemini_client import GenerationResult, generate_structured
from backend.services.Gemini_Services.map_assist import MAP_ASSIST_INSTRUCTION, MapAssist
from backend.services.Gemini_Services.system_prompts import GENERAL_SYSTEM_PROMPT


class GeneralResponse(BaseModel):
    answer: str = Field(description="Concise, practical field answer")
    key_points: list[str] = Field(
        default_factory=list, description="Optional actionable bullet points"
    )
    map_assist: MapAssist = Field(default_factory=MapAssist)


def generate_general(query: str, context: Optional[str] = None) -> GenerationResult:
    prompt = query if not context else f"Context: {context}\n\nQuestion: {query}"
    return generate_structured(
        prompt=prompt,
        system_prompt=GENERAL_SYSTEM_PROMPT + MAP_ASSIST_INSTRUCTION,
        primary_model=settings.GEMINI_GENERAL_MODEL,
        fallback_model=settings.GEMINI_GENERAL_FALLBACK,
        response_schema=GeneralResponse,
        temperature=0.3,
    )
