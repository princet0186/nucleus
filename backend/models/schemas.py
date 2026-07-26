from pydantic import BaseModel, Field
from typing import Optional

from backend.models.common import SanitizationMetadata
from backend.models.map_schemas import MapPayload

__all__ = ["SanitizationMetadata"]  # re-exported: existing imports expect it here


class PrivacyMetadata(BaseModel):
    sanitization_applied: bool
    dp_mechanism: str = ""
    fields_redacted: list[str] = Field(default_factory=list)
    fields_generalized: list[str] = Field(default_factory=list)
    pate_aggregation: bool = False
    pate_consensus: float = 0.0
    pate_teachers_voted: int = 0
    epsilon_spent: float = 0.0
    epsilon_remaining: float = 0.0
    zkp_commitment: str = ""
    zkp_proof: str = ""
    zkp_verified: bool = False
    response_scrubbed: bool = False
    response_fields_scrubbed: list[str] = Field(default_factory=list)


class NucleusQueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=3,
        description="Any military, tactical, medical, or logistics question",
        examples=["What is the correct procedure for a field tracheotomy?"],
    )
    context: Optional[str] = Field(
        default=None, description="Additional context for the query"
    )
    origin: Optional[str] = Field(
        default=None,
        description=(
            "Operator position as an MGRS grid or 'lat,lon'. Only used when the "
            "question needs a map ('nearest hospital'). Resolved on-device — a "
            "position is never sent to the cloud."
        ),
        examples=["42S WD 1234 5678"],
    )


class NucleusQueryResponse(BaseModel):
    query_id: str
    mode: str
    response: str
    timestamp: str
    cached: bool = False
    sanitization: Optional[SanitizationMetadata] = None
    # Present only when the question needed a map ("nearest evacuation centre").
    # Its presence is the frontend's signal to open the map sidebar.
    map: Optional[MapPayload] = None
    # DP layer stays parked — populated only if aggregate reporting ships later.
    privacy: Optional[PrivacyMetadata] = None


class TriageRequest(BaseModel):
    injury_description: str = Field(
        ...,
        min_length=5,
        description="Clinical description of the combat injury",
        examples=["GSW to left chest, difficulty breathing, decreased breath sounds"],
    )
    patient_demographics: Optional[dict] = Field(
        default=None,
        description="Optional: age, sex, weight — will be sanitized before API call",
    )
    origin: Optional[str] = Field(
        default=None,
        description=(
            "Operator's position (MGRS grid or 'lat, lon'). Stays on-device; used "
            "only if Gemini decides a map of nearby facilities would help."
        ),
    )


class TreatmentProtocol(BaseModel):
    priority: str = ""
    immediate_actions: list[str] = Field(default_factory=list)
    evacuation: str = ""


class TriageResult(BaseModel):
    triage_category: str = ""
    confidence_reasoning: str = ""
    treatment_protocol: TreatmentProtocol = Field(default_factory=TreatmentProtocol)
    recommended_drugs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class TriageResponse(BaseModel):
    query_id: str
    mode: str = "triage"
    triage_result: Optional[TriageResult] = None
    raw_response: Optional[str] = None
    timestamp: str
    sanitization: Optional[SanitizationMetadata] = None
    # Present when Gemini judged a map would help (e.g. nearest surgical care for
    # a T1). Its presence is the frontend's signal to open the map sidebar.
    map: Optional[MapPayload] = None
    # DP layer stays parked — populated only if aggregate reporting ships later.
    privacy: Optional[PrivacyMetadata] = None


class MedevacRequest(BaseModel):
    triage_category: str = Field(
        ...,
        description="NATO triage category (T1-IMMEDIATE, T2-DELAYED, T3-MINIMAL, T4-EXPECTANT)",
    )
    grid_coordinate: str = Field(default="UNKNOWN", description="MGRS grid coordinate")
    call_sign: str = Field(default="NUCLEUS-01")
    radio_freq: str = Field(default="37.00 MHz FM")
    num_patients: int = Field(default=1, ge=1)
    is_litter: bool = Field(default=True, description="True=litter, False=ambulatory")
    security: str = Field(
        default="N", description="N=No enemy, P=Possible, E=Enemy, X=Escort"
    )
    marking: str = Field(default="C", description="A=Panels, B=Pyro, C=Smoke, D=None")
    nationality: str = Field(
        default="A", description="A=US Mil, B=US Civ, C=Non-US Mil, D=Non-US Civ, E=EPW"
    )
    cbrn: str = Field(
        default="N", description="N=None, C=Chemical, B=Biological, R=Radiological"
    )


class MedevacNineLine(BaseModel):
    line_1: str
    line_2: str
    line_3: str
    line_4: str
    line_5: str
    line_6: str
    line_7: str
    line_8: str
    line_9: str


class MedevacResponse(BaseModel):
    request_id: str
    generated_at: str
    triage_category: str
    precedence: str
    nine_line: MedevacNineLine
    radio_format: str


class MedevacGenerateRequest(BaseModel):
    context: str = Field(
        ...,
        min_length=10,
        description="Concentrated chat context retrieved client-side (top-K relevant messages)",
    )
    origin: Optional[str] = Field(
        default=None,
        description=(
            "Operator's position (MGRS grid or 'lat, lon'). If omitted, the "
            "casualty grid is extracted from the context. Stays on-device; used "
            "to plot the casualty and the nearest evacuation facilities."
        ),
    )


class ConsensusReport(BaseModel):
    """PATE-style reliability vote across independent generations."""

    samples: int
    disputed_fields: list[str] = Field(default_factory=list)
    agreement: float = 1.0


class MedevacAIResponse(BaseModel):
    request_id: str
    generated_at: str
    source: str = Field(description="'gemini_consensus' or 'offline_template'")
    nine_line: MedevacNineLine
    precedence: str
    narrative: str = ""
    radio_format: str
    consensus: Optional[ConsensusReport] = None
    sanitization: Optional[SanitizationMetadata] = None
    # The casualty and nearest evacuation facilities, resolved on-device from the
    # grid in the context. Its presence opens the map sidebar alongside the 9-line.
    map: Optional[MapPayload] = None
