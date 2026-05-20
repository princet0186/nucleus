# Battlefield Drug Formulary & Interaction Checker.

# The drugs a combat medic actually carries in their aid bag
BATTLEFIELD_FORMULARY = {
    "tranexamic_acid": {
        "name": "Tranexamic Acid (TXA)",
        "dose": "1g IV over 10 min, then 1g over 8 hours",
        "indication": "Hemorrhage control, suspected significant bleeding",
        "contraindications": ["active thromboembolic event"],
        "tccc_phase": "Tactical Field Care"
    },
    "ketamine": {
        "name": "Ketamine",
        "dose": "50mg IV/IO or 200mg IM",
        "indication": "Battlefield analgesia, pain management",
        "contraindications": ["age < 1 year"],
        "tccc_phase": "Tactical Field Care"
    },
    "morphine": {
        "name": "Morphine Sulfate",
        "dose": "5mg IV/IO, repeat every 10 min as needed",
        "indication": "Severe pain when ketamine unavailable",
        "contraindications": ["altered consciousness", "respiratory depression", "hypotension"],
        "tccc_phase": "Tactical Field Care"
    },
    "meloxicam": {
        "name": "Meloxicam (Mobic)",
        "dose": "15mg PO once daily",
        "indication": "Mild-moderate pain, anti-inflammatory",
        "contraindications": ["active GI bleeding", "renal injury"],
        "tccc_phase": "Tactical Field Care"
    },
    "acetaminophen": {
        "name": "Acetaminophen (Tylenol)",
        "dose": "500-1000mg PO every 6 hours",
        "indication": "Mild pain, fever",
        "contraindications": ["liver injury", "hepatic failure"],
        "tccc_phase": "Tactical Field Care"
    },
    "ertapenem": {
        "name": "Ertapenem",
        "dose": "1g IV/IM once daily",
        "indication": "Wound infection prophylaxis (penetrating trauma)",
        "contraindications": ["known carbapenem allergy"],
        "tccc_phase": "Tactical Field Care"
    },
    "moxifloxacin": {
        "name": "Moxifloxacin (Avelox)",
        "dose": "400mg PO once daily",
        "indication": "Wound infection prophylaxis (oral alternative)",
        "contraindications": ["known fluoroquinolone allergy", "QT prolongation"],
        "tccc_phase": "Tactical Field Care"
    },
    "naloxone": {
        "name": "Naloxone (Narcan)",
        "dose": "0.4mg IV/IM, repeat every 2-3 min",
        "indication": "Opioid overdose reversal",
        "contraindications": [],
        "tccc_phase": "Tactical Field Care"
    },
    "ondansetron": {
        "name": "Ondansetron (Zofran)",
        "dose": "4mg IV/ODT every 8 hours",
        "indication": "Nausea/vomiting prevention with opioid use",
        "contraindications": ["QT prolongation"],
        "tccc_phase": "Tactical Field Care"
    },
    "epinephrine": {
        "name": "Epinephrine (EpiPen)",
        "dose": "0.3mg IM auto-injector",
        "indication": "Anaphylaxis, severe allergic reaction",
        "contraindications": [],
        "tccc_phase": "Care Under Fire / Tactical Field Care"
    },
}

# Known dangerous drug-drug interactions relevant to the battlefield
INTERACTION_RULES = [
    {
        "drug_a": "morphine",
        "drug_b": "ketamine",
        "severity": "MODERATE",
        "warning": "Combined CNS depression risk. Use reduced doses. Monitor respiratory rate closely. Prefer ketamine alone per TCCC guidelines."
    },
    {
        "drug_a": "morphine",
        "drug_b": "naloxone",
        "severity": "HIGH",
        "warning": "Naloxone reverses morphine. Do NOT administer morphine after naloxone unless pain reassessment confirms need. Effects of morphine will be blocked."
    },
    {
        "drug_a": "meloxicam",
        "drug_b": "tranexamic_acid",
        "severity": "MODERATE",
        "warning": "NSAIDs may impair platelet function, potentially counteracting TXA hemostatic effect. Avoid meloxicam in actively bleeding patients receiving TXA."
    },
    {
        "drug_a": "moxifloxacin",
        "drug_b": "ondansetron",
        "severity": "HIGH",
        "warning": "Both drugs prolong QT interval. Combined use increases risk of fatal cardiac arrhythmia (Torsades de Pointes). Use alternative antiemetic."
    },
    {
        "drug_a": "morphine",
        "drug_b": "morphine",
        "severity": "HIGH",
        "warning": "Duplicate opioid dosing. Cumulative respiratory depression risk. Verify total morphine dose does not exceed 30mg without medical officer authorization."
    },
]


def check_interactions(drugs_to_administer: list[str], drugs_already_given: list[str] = None) -> list[dict]:
    # Checks a list of drugs against each other and against previously administered drugs for dangerous interactions.
    if drugs_already_given is None:
        drugs_already_given = []
    
    all_drugs = list(set(drugs_to_administer + drugs_already_given))
    warnings = []
    checked_pairs = set()
    
    for rule in INTERACTION_RULES:
        a, b = rule["drug_a"], rule["drug_b"]
        pair_key = tuple(sorted([a, b]))
        
        if pair_key in checked_pairs:
            continue
        
        if a in all_drugs and b in all_drugs:
            warnings.append({
                "drug_a": BATTLEFIELD_FORMULARY.get(a, {}).get("name", a),
                "drug_b": BATTLEFIELD_FORMULARY.get(b, {}).get("name", b),
                "severity": rule["severity"],
                "warning": rule["warning"]
            })
            checked_pairs.add(pair_key)
    
    return warnings


def get_drug_info(drug_key: str) -> dict | None:
    # Returns formulary information for a given drug.
    return BATTLEFIELD_FORMULARY.get(drug_key)


def get_all_drugs() -> list[str]:
    # Returns all available drug keys in the formulary.
    return list(BATTLEFIELD_FORMULARY.keys())
