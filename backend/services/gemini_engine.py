
import json
import uuid
from datetime import datetime, timezone

from google import genai
from google.genai import types

from backend.core.config import settings
from backend.services.privacy_sanitizer import privacy_sanitizer
from backend.services.encryption_layer import encryption_layer
from backend.services.zero_knowledge import zkp, ZKCommitment


# System prompt for general military/tactical queries
_GENERAL_SYSTEM_PROMPT = """You are Nucleus AI, a tactical assistant deployed on military field devices.

Your role:
- Answer questions about military operations, tactics, logistics, field procedures, and survival.
- Provide practical, actionable guidance suitable for field conditions.
- Support combat medics, field officers, and support personnel.
- Be concise — operators in the field need fast answers, not essays.

Constraints:
- Never fabricate specific unit names, personnel, or classified procedures.
- If unsure, say so clearly rather than guessing.
- Prioritize life-safety information above all else.
- All responses should be usable without internet connectivity once received.

You may also receive medical queries. Handle them with clinical accuracy
following Tactical Combat Casualty Care (TCCC) guidelines."""

# System prompt for specialized medical triage
_TRIAGE_SYSTEM_PROMPT = """You are Nucleus AI operating in MEDICAL TRIAGE mode.

You are a TCCC (Tactical Combat Casualty Care) expert assisting combat medics
with NATO T1-T4 casualty classification in mass casualty (MASCAL) events.

Classification criteria:
  T1-IMMEDIATE: Life-threatening injuries that are survivable with immediate intervention.
                Examples: tension pneumothorax, massive hemorrhage, airway compromise.
  T2-DELAYED:   Serious injuries that can wait 4-6 hours without becoming T1.
                Examples: open fractures with controlled bleeding, stable penetrating wounds.
  T3-MINIMAL:   Walking wounded. Minor injuries, patient can self-aid or buddy-aid.
                Examples: superficial lacerations, sprains, minor burns.
  T4-EXPECTANT: Injuries that are not survivable given available field resources.
                Examples: massive head trauma with no brain function, 90%+ burns with no pulse.

For every injury description, you MUST respond with this exact JSON structure:
{
  "triage_category": "T1-IMMEDIATE | T2-DELAYED | T3-MINIMAL | T4-EXPECTANT",
  "confidence_reasoning": "Brief clinical reasoning for this classification",
  "treatment_protocol": {
    "priority": "Description of treatment priority",
    "immediate_actions": ["action1", "action2", ...],
    "evacuation": "Evacuation priority and timeframe"
  },
  "recommended_drugs": ["drug1", "drug2"],
  "warnings": ["any critical warnings"]
}

Be clinically precise. Lives depend on accurate triage."""

# System prompt for drug interaction analysis
_DRUG_CHECK_SYSTEM_PROMPT = """You are Nucleus AI operating in DRUG INTERACTION ANALYSIS mode.

You are assisting a combat medic in checking drug interactions before
administering medications to a battlefield casualty.

The standard battlefield formulary includes:
- Tranexamic Acid (TXA), Ketamine, Morphine, Meloxicam, Acetaminophen,
  Ertapenem, Moxifloxacin, Naloxone, Ondansetron, Epinephrine

For every drug interaction query, respond with this exact JSON structure:
{
  "safe_to_administer": true/false,
  "interactions": [
    {
      "drug_pair": "Drug A + Drug B",
      "severity": "HIGH | MODERATE | LOW",
      "warning": "Clinical explanation of the interaction",
      "recommendation": "What to do instead"
    }
  ],
  "overall_recommendation": "Summary recommendation for the medic"
}

Be conservative — flag potential interactions even if they are moderate.
In the field, there is no pharmacist to double-check."""


class NucleusAI:


    def __init__(self):
        self._client = None
        self._model = settings.GEMINI_MODEL
        self._initialized = False

    def initialize(self) -> None:
        if not settings.GEMINI_API_KEY:
            print("[NUCLEUS AI] WARNING: GEMINI_API_KEY not set. AI features disabled.")
            return

        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._initialized = True
        print(f"[NUCLEUS AI] Initialized with model: {self._model}")

    @property
    def is_ready(self) -> bool:
        return self._initialized and self._client is not None

    async def query(self, user_query: str, context: str = None) -> dict:
        return await self._execute(
            user_input=user_query,
            system_prompt=_GENERAL_SYSTEM_PROMPT,
            mode="general",
            context=context,
        )

    async def triage(self, injury_description: str,
                     patient_demographics: dict = None) -> dict:
        prompt_parts = [injury_description]
        if patient_demographics:
            demo_str = ", ".join(
                f"{k}: {v}" for k, v in patient_demographics.items()
            )
            prompt_parts.append(f"Patient demographics: {demo_str}")

        full_prompt = "\n".join(prompt_parts)

        result = await self._execute(
            user_input=full_prompt,
            system_prompt=_TRIAGE_SYSTEM_PROMPT,
            mode="triage",
            response_mime_type="application/json",
        )

        if result.get("gemini_response"):
            try:
                triage_data = json.loads(result["gemini_response"])
                result["triage_result"] = triage_data
            except json.JSONDecodeError:
                result["triage_result"] = {
                    "raw_response": result["gemini_response"]
                }

        return result

    async def drug_check(self, drugs_to_administer: list[str],
                         drugs_already_given: list[str] = None,
                         patient_context: str = None) -> dict:
        drugs_already_given = drugs_already_given or []

        prompt = (
            f"Check interactions for administering: {', '.join(drugs_to_administer)}\n"
            f"Already given: {', '.join(drugs_already_given) if drugs_already_given else 'None'}"
        )
        if patient_context:
            prompt += f"\nPatient context: {patient_context}"

        result = await self._execute(
            user_input=prompt,
            system_prompt=_DRUG_CHECK_SYSTEM_PROMPT,
            mode="drug_check",
            response_mime_type="application/json",
        )

        if result.get("gemini_response"):
            try:
                drug_data = json.loads(result["gemini_response"])
                result["drug_analysis"] = drug_data
            except json.JSONDecodeError:
                result["drug_analysis"] = {
                    "raw_response": result["gemini_response"]
                }

        return result

    async def _execute(self, user_input: str, system_prompt: str,
                       mode: str, context: str = None,
                       response_mime_type: str = None) -> dict:
        query_id = str(uuid.uuid4())

        if not self.is_ready:
            return {
                "query_id": query_id,
                "error": "Nucleus AI not initialized. Set GEMINI_API_KEY in .env",
                "mode": mode,
            }

        if privacy_sanitizer.epsilon_remaining <= 0:
            return {
                "query_id": query_id,
                "error": "Privacy budget exhausted. No more queries allowed "
                         "until budget is reset to protect operational security.",
                "mode": mode,
                "epsilon_remaining": 0,
            }

        sanitized_input, sanitization_report = privacy_sanitizer.sanitize(user_input)

        commitment = zkp.commit(user_input, sanitized_input)

        full_prompt = sanitized_input
        if context:
            sanitized_context, _ = privacy_sanitizer.sanitize(context)
            full_prompt = f"Context: {sanitized_context}\n\nQuery: {sanitized_input}"

        try:
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.2 if mode == "triage" else 0.4,
            )
            if response_mime_type:
                config.response_mime_type = response_mime_type

            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=full_prompt,
                config=config,
            )
            gemini_response = response.text

        except Exception as e:
            return {
                "query_id": query_id,
                "error": f"Gemini API error: {str(e)}",
                "mode": mode,
                "privacy": {
                    "sanitization_applied": True,
                    "fields_redacted": sanitization_report.fields_redacted,
                    "epsilon_spent": sanitization_report.epsilon_spent,
                },
            }

        encryption_layer.log_query(
            query_id=query_id,
            sanitized_query=sanitized_input,
            response_summary=gemini_response[:200],
            epsilon_spent=sanitization_report.epsilon_spent,
            zkp_commitment=commitment.commitment,
        )

        return {
            "query_id": query_id,
            "mode": mode,
            "gemini_response": gemini_response,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "privacy": {
                "sanitization_applied": True,
                "fields_redacted": sanitization_report.fields_redacted,
                "differential_privacy_noise": sanitization_report.noise_applied,
                "epsilon_spent": sanitization_report.epsilon_spent,
                "epsilon_remaining": privacy_sanitizer.epsilon_remaining,
                "zkp_commitment": commitment.commitment,
                "zkp_proof": commitment.proof,
                "zkp_verified": zkp.verify(commitment),
            },
        }


nucleus_ai = NucleusAI()
