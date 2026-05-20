
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.db.models import CasualtyCard
from backend.services.gemini_engine import nucleus_ai
from backend.services.medevac_generator import generate_medevac_request
from backend.services.drug_checker import BATTLEFIELD_FORMULARY
from backend.models.schemas import (
    NucleusQueryRequest, NucleusQueryResponse,
    TriageRequest, TriageResponse, TriageResult, TreatmentProtocol,
    DrugCheckRequest, DrugCheckResponse, DrugAnalysis,
    MedevacRequest, MedevacResponse,
    PrivacyMetadata,
    CasualtyCreate, CasualtyResponse, CasualtyUpdate
)

router = APIRouter(prefix="/nucleus", tags=["Nucleus AI"])


def _build_privacy_metadata(raw: dict) -> PrivacyMetadata:
    # Extracts the privacy block from the engine response into a typed schema.
    p = raw.get("privacy", {})
    return PrivacyMetadata(
        sanitization_applied=p.get("sanitization_applied", False),
        fields_redacted=p.get("fields_redacted", []),
        differential_privacy_noise=p.get("differential_privacy_noise", False),
        epsilon_spent=p.get("epsilon_spent", 0),
        epsilon_remaining=p.get("epsilon_remaining", 0),
        zkp_commitment=p.get("zkp_commitment", ""),
        zkp_proof=p.get("zkp_proof", ""),
        zkp_verified=p.get("zkp_verified", False),
    )


@router.post("/query", response_model=NucleusQueryResponse)
async def general_query(request: NucleusQueryRequest):
    # General-purpose military and tactical AI assistant.
    if not nucleus_ai.is_ready:
        raise HTTPException(status_code=503, detail="Nucleus AI not initialized. Set GEMINI_API_KEY.")

    result = await nucleus_ai.query(request.query, request.context)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return NucleusQueryResponse(
        query_id=result["query_id"],
        mode=result["mode"],
        response=result["gemini_response"],
        timestamp=result["timestamp"],
        privacy=_build_privacy_metadata(result),
    )


@router.post("/triage", response_model=TriageResponse)
async def medical_triage(request: TriageRequest):

    if not nucleus_ai.is_ready:
        raise HTTPException(status_code=503, detail="Nucleus AI not initialized. Set GEMINI_API_KEY.")

    result = await nucleus_ai.triage(
        request.injury_description,
        request.patient_demographics,
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    # Parse structured triage data if Gemini returned valid JSON
    triage_result = None
    raw_response = None
    triage_data = result.get("triage_result", {})

    if isinstance(triage_data, dict) and "triage_category" in triage_data:
        protocol = triage_data.get("treatment_protocol", {})
        triage_result = TriageResult(
            triage_category=triage_data.get("triage_category", ""),
            confidence_reasoning=triage_data.get("confidence_reasoning", ""),
            treatment_protocol=TreatmentProtocol(
                priority=protocol.get("priority", ""),
                immediate_actions=protocol.get("immediate_actions", []),
                evacuation=protocol.get("evacuation", ""),
            ),
            recommended_drugs=triage_data.get("recommended_drugs", []),
            warnings=triage_data.get("warnings", []),
        )
    else:
        raw_response = result.get("gemini_response", "")

    return TriageResponse(
        query_id=result["query_id"],
        mode="triage",
        triage_result=triage_result,
        raw_response=raw_response,
        timestamp=result["timestamp"],
        privacy=_build_privacy_metadata(result),
    )


@router.post("/drug-check", response_model=DrugCheckResponse)
async def drug_interaction_check(request: DrugCheckRequest):
    # Checks drug interactions using Gemini's pharmacological knowledge.
    if not nucleus_ai.is_ready:
        raise HTTPException(status_code=503, detail="Nucleus AI not initialized. Set GEMINI_API_KEY.")

    result = await nucleus_ai.drug_check(
        request.drugs_to_administer,
        request.drugs_already_given,
        request.patient_context,
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    # Parse structured drug analysis
    drug_analysis = None
    raw_response = None
    drug_data = result.get("drug_analysis", {})

    if isinstance(drug_data, dict) and "safe_to_administer" in drug_data:
        from backend.models.schemas import DrugInteraction
        interactions = [
            DrugInteraction(**inter)
            for inter in drug_data.get("interactions", [])
        ]
        drug_analysis = DrugAnalysis(
            safe_to_administer=drug_data.get("safe_to_administer", True),
            interactions=interactions,
            overall_recommendation=drug_data.get("overall_recommendation", ""),
        )
    else:
        raw_response = result.get("gemini_response", "")

    return DrugCheckResponse(
        query_id=result["query_id"],
        mode="drug_check",
        drug_analysis=drug_analysis,
        raw_response=raw_response,
        timestamp=result["timestamp"],
        privacy=_build_privacy_metadata(result),
    )


@router.post("/medevac", response_model=MedevacResponse)
async def generate_medevac(request: MedevacRequest):
    # Generates a NATO-standard 9-Line MEDEVAC request.
    result = generate_medevac_request(
        triage_category=request.triage_category,
        grid_coordinate=request.grid_coordinate,
        call_sign=request.call_sign,
        radio_freq=request.radio_freq,
        num_patients=request.num_patients,
        is_litter=request.is_litter,
        security=request.security,
        marking=request.marking,
        nationality=request.nationality,
        cbrn=request.cbrn,
    )
    return result


@router.get("/formulary")
async def get_formulary():
    return {
        "formulary": BATTLEFIELD_FORMULARY,
        "total_drugs": len(BATTLEFIELD_FORMULARY),
    }

@router.post("/casualty/create", response_model=CasualtyResponse)
def create_casualty(casualty: CasualtyCreate, db: Session = Depends(get_db)):
    db_casualty = db.query(CasualtyCard).filter(CasualtyCard.patient_id == casualty.patient_id).first()
    if db_casualty:
        raise HTTPException(status_code=400, detail="Patient ID already exists")
    
    new_casualty = CasualtyCard(
        patient_id=casualty.patient_id,
        full_name=casualty.full_name,
        unit=casualty.unit,
        injury_type=casualty.injury_type,
        triage_category=casualty.triage_category,
        evacuation_role="Role 1"
    )
    db.add(new_casualty)
    db.commit()
    db.refresh(new_casualty)
    
    # We must format the response to handle the properties correctly, since SQLAlchemy models 
    # with properties need special care if from_attributes has issues with decrypted properties,
    # but pydantic should handle it. 
    return new_casualty

@router.get("/casualty", response_model=list[CasualtyResponse])
def get_all_casualties(db: Session = Depends(get_db)):
    return db.query(CasualtyCard).all()

@router.put("/casualty/{patient_id}", response_model=CasualtyResponse)
def update_casualty(patient_id: str, update_data: CasualtyUpdate, db: Session = Depends(get_db)):
    db_casualty = db.query(CasualtyCard).filter(CasualtyCard.patient_id == patient_id).first()
    if not db_casualty:
        raise HTTPException(status_code=404, detail="Casualty not found")
    
    if update_data.triage_category is not None:
        db_casualty.triage_category = update_data.triage_category
    if update_data.evacuation_role is not None:
        db_casualty.evacuation_role = update_data.evacuation_role
        
    db.commit()
    db.refresh(db_casualty)
    return db_casualty

