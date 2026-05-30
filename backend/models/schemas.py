

from pydantic import BaseModel, Field
from typing import Optional



class PrivacyMetadata(BaseModel):
    sanitization_applied: bool
    fields_redacted: list[str] = Field(default_factory=list)
    fields_generalized: list[str] = Field(default_factory=list)
    differential_privacy_noise: bool = False
    epsilon_spent: float = 0.0
    epsilon_remaining: float = 0.0
    zkp_commitment: str = ""
    zkp_proof: str = ""
    zkp_verified: bool = False
    response_scrubbed: bool = False
    response_fields_scrubbed: list[str] = Field(default_factory=list)



class NucleusQueryRequest(BaseModel):
    query: str = Field(
        ..., min_length=3,
        description="Any military, tactical, medical, or logistics question",
        examples=["What is the correct procedure for a field tracheotomy?"]
    )
    context: Optional[str] = Field(
        default=None,
        description="Additional context for the query"
    )

class NucleusQueryResponse(BaseModel):
    query_id: str
    mode: str
    response: str
    timestamp: str
    cached: bool = False
    privacy: PrivacyMetadata



class TriageRequest(BaseModel):
    injury_description: str = Field(
        ..., min_length=5,
        description="Clinical description of the combat injury",
        examples=["GSW to left chest, difficulty breathing, decreased breath sounds"]
    )
    patient_demographics: Optional[dict] = Field(
        default=None,
        description="Optional: age, sex, weight — will be sanitized before API call"
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
    privacy: PrivacyMetadata



class DrugCheckRequest(BaseModel):
    drugs_to_administer: list[str] = Field(
        ...,
        description="Drug names to check before administering",
        examples=[["morphine", "ketamine"]]
    )
    drugs_already_given: list[str] = Field(
        default_factory=list,
        description="Drugs the patient has already received"
    )
    patient_context: Optional[str] = Field(
        default=None,
        description="Injury context for smarter interaction analysis"
    )

class DrugInteraction(BaseModel):
    drug_pair: str = ""
    severity: str = ""
    warning: str = ""
    recommendation: str = ""

class DrugAnalysis(BaseModel):
    safe_to_administer: bool = True
    interactions: list[DrugInteraction] = Field(default_factory=list)
    overall_recommendation: str = ""

class DrugCheckResponse(BaseModel):
    query_id: str
    mode: str = "drug_check"
    drug_analysis: Optional[DrugAnalysis] = None
    raw_response: Optional[str] = None
    timestamp: str
    privacy: PrivacyMetadata



class MedevacRequest(BaseModel):
    triage_category: str = Field(
        ...,
        description="NATO triage category (T1-IMMEDIATE, T2-DELAYED, T3-MINIMAL, T4-EXPECTANT)"
    )
    grid_coordinate: str = Field(default="UNKNOWN", description="MGRS grid coordinate")
    call_sign: str = Field(default="NUCLEUS-01")
    radio_freq: str = Field(default="37.00 MHz FM")
    num_patients: int = Field(default=1, ge=1)
    is_litter: bool = Field(default=True, description="True=litter, False=ambulatory")
    security: str = Field(default="N", description="N=No enemy, P=Possible, E=Enemy, X=Escort")
    marking: str = Field(default="C", description="A=Panels, B=Pyro, C=Smoke, D=None")
    nationality: str = Field(default="A", description="A=US Mil, B=US Civ, C=Non-US Mil, D=Non-US Civ, E=EPW")
    cbrn: str = Field(default="N", description="N=None, C=Chemical, B=Biological, R=Radiological")

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



class CasualtyCreate(BaseModel):
    patient_id: str = Field(..., description="Unique alphanumeric military designation or generic ID")
    full_name: str = Field(..., description="Casualty name — will be fully encrypted on-device")
    unit: str = Field(..., description="Casualty unit designation — will be fully encrypted on-device")
    injury_type: str = Field(..., description="Description of the injury — will be fully encrypted")
    triage_category: str = Field(..., description="Plaintext categorization for search/sorting (T1-T4)")

class CasualtyResponse(BaseModel):
    id: int
    patient_id: str
    full_name: str
    unit: str
    injury_type: str
    triage_category: str
    evacuation_role: str = "Role 1"
    created_at: str

    class Config:
        from_attributes = True


class CasualtyUpdate(BaseModel):
    triage_category: Optional[str] = Field(None, description="Updated triage category")
    evacuation_role: Optional[str] = Field(None, description="Role 1, Role 2, or Role 3")

