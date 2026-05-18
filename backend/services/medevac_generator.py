"""
9-Line MEDEVAC Request Generator.

Generates a formatted NATO-standard 9-Line MEDEVAC request
from triage classification and casualty card data.

Standard 9-Line Format:
  Line 1: Location (MGRS grid coordinate)
  Line 2: Radio frequency / call sign
  Line 3: Number of patients by precedence (A-Urgent, B-Priority, C-Routine, D-Convenience, E-Expectant)
  Line 4: Special equipment required (A-None, B-Hoist, C-Extraction, D-Ventilator)
  Line 5: Number of patients by type (L-Litter, A-Ambulatory)
  Line 6: Security of pickup site (N-No enemy, P-Possible, E-Enemy in area, X-Armed escort required)
  Line 7: Method of marking pickup site (A-Panels, B-Pyro, C-Smoke, D-None, E-Other)
  Line 8: Patient nationality and status (A-US Military, B-US Civilian, C-Non-US Military, D-Non-US Civilian, E-EPW)
  Line 9: CBRN contamination (N-None, C-Chemical, B-Biological, R-Radiological, N-Nuclear)
"""

from datetime import datetime

# Maps our T1-T4 to the 9-Line precedence codes
TRIAGE_TO_PRECEDENCE = {
    "T1-IMMEDIATE": "A",   # Urgent
    "T2-DELAYED": "B",     # Priority
    "T3-MINIMAL": "C",     # Routine
    "T4-EXPECTANT": "E",   # Expectant
}

PRECEDENCE_LABELS = {
    "A": "URGENT (T1-Immediate)",
    "B": "PRIORITY (T2-Delayed)",
    "C": "ROUTINE (T3-Minimal)",
    "E": "EXPECTANT (T4-Expectant)",
}


def generate_medevac_request(
    triage_category: str,
    grid_coordinate: str = "UNKNOWN",
    call_sign: str = "NUCLEUS-01",
    radio_freq: str = "37.00 MHz FM",
    num_patients: int = 1,
    is_litter: bool = True,
    security: str = "N",
    marking: str = "C",
    nationality: str = "A",
    cbrn: str = "N",
    special_equipment: str = "A",
    casualty_info: dict = None,
) -> dict:
    """
    Generates a complete 9-Line MEDEVAC request.
    
    Returns both a structured dict and a formatted text block
    ready for radio transmission.
    """
    precedence = TRIAGE_TO_PRECEDENCE.get(triage_category, "C")
    patient_type = "L" if is_litter else "A"
    
    nine_line = {
        "line_1": f"Location: {grid_coordinate}",
        "line_2": f"Callsign: {call_sign}, Freq: {radio_freq}",
        "line_3": f"{num_patients}{precedence} - {PRECEDENCE_LABELS.get(precedence, 'UNKNOWN')}",
        "line_4": f"Special Equipment: {_equipment_label(special_equipment)}",
        "line_5": f"Patients: {num_patients}{patient_type} - {'Litter' if is_litter else 'Ambulatory'}",
        "line_6": f"Security: {_security_label(security)}",
        "line_7": f"Marking: {_marking_label(marking)}",
        "line_8": f"Nationality: {_nationality_label(nationality)}",
        "line_9": f"CBRN: {_cbrn_label(cbrn)}",
    }
    
    # Generate the radio-ready text block
    formatted = _format_for_radio(nine_line, triage_category)
    
    return {
        "request_id": f"MEDEVAC-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "generated_at": datetime.utcnow().isoformat(),
        "triage_category": triage_category,
        "precedence": precedence,
        "nine_line": nine_line,
        "radio_format": formatted,
    }


def _format_for_radio(nine_line: dict, triage_cat: str) -> str:
    """Formats the 9-Line into a plain-text block suitable for radio transmission."""
    lines = [
        "═══════════════════════════════════════",
        "         9-LINE MEDEVAC REQUEST         ",
        f"         Triage: {triage_cat}          ",
        "═══════════════════════════════════════",
    ]
    for key in sorted(nine_line.keys()):
        line_num = key.replace("line_", "LINE ")
        lines.append(f"  {line_num}: {nine_line[key]}")
    lines.append("═══════════════════════════════════════")
    return "\n".join(lines)


def _equipment_label(code: str) -> str:
    return {"A": "None required", "B": "Hoist", "C": "Extraction equipment", "D": "Ventilator"}.get(code, code)

def _security_label(code: str) -> str:
    return {"N": "No enemy troops", "P": "Possibly enemy", "E": "Enemy in area (armed escort required)", "X": "Armed escort required"}.get(code, code)

def _marking_label(code: str) -> str:
    return {"A": "Panels", "B": "Pyrotechnic signal", "C": "Smoke signal", "D": "None", "E": "Other"}.get(code, code)

def _nationality_label(code: str) -> str:
    return {"A": "US Military", "B": "US Civilian", "C": "Non-US Military", "D": "Non-US Civilian", "E": "EPW/Detainee"}.get(code, code)

def _cbrn_label(code: str) -> str:
    return {"N": "None", "C": "Chemical", "B": "Biological", "R": "Radiological"}.get(code, code)
