
from datetime import datetime

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
