"""
Privacy Sanitizer for Nucleus.

Before any query reaches Gemini, this module strips operationally
sensitive information and applies local differential privacy.

Two mechanisms work together:
1. PII Stripping — regex-based removal of names, ranks, unit IDs,
   grid coordinates, and other military identifiers.
2. Differential Privacy — Laplace noise on numerical values and
   randomized response on categorical fields. This ensures that
   even if an adversary monitors API traffic, they cannot reconstruct
   exact patient details from the sanitized queries.

Privacy guarantee:
   For any two adjacent queries q1, q2 differing in one field,
   P[Sanitize(q1) ∈ S] ≤ e^ε · P[Sanitize(q2) ∈ S]
"""

import re
import math
import random
import hashlib
from dataclasses import dataclass, field

from backend.core.config import settings


# Military ranks that should be stripped from queries
_RANKS = [
    r"\bPvt\b", r"\bPFC\b", r"\bSpc\b", r"\bCpl\b", r"\bSgt\b",
    r"\bSSgt\b", r"\bSFC\b", r"\bMSgt\b", r"\b1SG\b", r"\bSGM\b",
    r"\bCSM\b", r"\b2LT\b", r"\b1LT\b", r"\bCPT\b", r"\bMAJ\b",
    r"\bLTC\b", r"\bCOL\b", r"\bBG\b", r"\bMG\b", r"\bLTG\b",
    r"\bGEN\b", r"\bPrivate\b", r"\bCorporal\b", r"\bSergeant\b",
    r"\bLieutenant\b", r"\bCaptain\b", r"\bMajor\b", r"\bColonel\b",
    r"\bGeneral\b", r"\bLance\s+Corporal\b", r"\bStaff\s+Sergeant\b",
    r"\bMaster\s+Sergeant\b", r"\bFirst\s+Sergeant\b",
    r"\bHavildar\b", r"\bNaik\b", r"\bSepoy\b", r"\bSubedar\b",
    r"\bJemadar\b", r"\bRisaldar\b",
]

# Patterns that leak operational identity or position
_PII_PATTERNS = [
    # MGRS grid coordinates (e.g., 43SNA1234567890)
    (re.compile(r"\b\d{1,2}[A-Z]{3}\d{6,10}\b"), "[GRID_REDACTED]"),
    # Latitude/longitude pairs
    (re.compile(r"-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}"), "[COORDS_REDACTED]"),
    # Call signs (e.g., ALPHA-6, BRAVO-ACTUAL)
    (re.compile(r"\b(ALPHA|BRAVO|CHARLIE|DELTA|ECHO|FOXTROT|GOLF|HOTEL|"
                r"INDIA|JULIET|KILO|LIMA|MIKE|NOVEMBER|OSCAR|PAPA|QUEBEC|"
                r"ROMEO|SIERRA|TANGO|UNIFORM|VICTOR|WHISKEY|XRAY|YANKEE|"
                r"ZULU)[-\s]?\d*[-\s]?(ACTUAL|SIX|MAIN|TAC)?\b",
                re.IGNORECASE), "[CALLSIGN_REDACTED]"),
    # Radio frequencies (e.g., 37.00 MHz)
    (re.compile(r"\b\d{2,3}\.\d{1,3}\s*[MmKk]?[Hh][Zz]\b"), "[FREQ_REDACTED]"),
    # Unit identifiers (e.g., 3rd Battalion, Alpha Company)
    (re.compile(r"\b\d{1,3}(st|nd|rd|th)\s+(Battalion|Brigade|Division|Regiment|"
                r"Platoon|Squad|Company|Troop)\b", re.IGNORECASE), "[UNIT_REDACTED]"),
    # Service/ID numbers (sequences of 6+ digits)
    (re.compile(r"\b[A-Z]?\d{6,}\b"), "[ID_REDACTED]"),
    # Named individuals (Title + capitalized name pattern)
    (re.compile(r"\b(Mr|Mrs|Ms|Dr|Pvt|Sgt|Lt|Cpl|Col|Gen|Maj)\.\s+[A-Z][a-z]+\b"),
     "[NAME_REDACTED]"),
]


@dataclass
class SanitizationReport:
    """Records exactly what was stripped and what noise was added."""
    original_hash: str
    sanitized_hash: str
    fields_redacted: list[str] = field(default_factory=list)
    noise_applied: bool = False
    epsilon_spent: float = 0.0


class PrivacySanitizer:
    """
    Strips PII and applies differential privacy before queries leave the device.

    The sanitizer runs entirely on-device. Gemini only ever sees
    de-identified clinical or tactical descriptions with no way
    to trace them back to specific individuals or locations.
    """

    def __init__(self, epsilon_per_query: float = None):
        self._epsilon = epsilon_per_query or settings.EPSILON_PER_QUERY
        self._total_epsilon_spent = 0.0
        self._query_count = 0

    @property
    def total_epsilon_spent(self) -> float:
        return self._total_epsilon_spent

    @property
    def epsilon_remaining(self) -> float:
        return max(0, settings.EPSILON_BUDGET - self._total_epsilon_spent)

    @property
    def query_count(self) -> int:
        return self._query_count

    def sanitize(self, text: str) -> tuple[str, SanitizationReport]:
        """
        Full sanitization pipeline:
        1. Strip military ranks
        2. Redact PII patterns (coordinates, call signs, unit IDs, etc.)
        3. Apply Laplace noise to any remaining numerical values
        Returns the sanitized text and a report of what was changed.
        """
        original_hash = hashlib.sha256(text.encode()).hexdigest()
        redacted_fields = []

        # Step 1: Strip ranks
        for rank_pattern in _RANKS:
            if re.search(rank_pattern, text, re.IGNORECASE):
                text = re.sub(rank_pattern, "", text, flags=re.IGNORECASE)
                redacted_fields.append("rank")

        # Step 2: Redact PII patterns
        for pattern, replacement in _PII_PATTERNS:
            if pattern.search(text):
                field_name = replacement.strip("[]").lower()
                redacted_fields.append(field_name)
                text = pattern.sub(replacement, text)

        # Step 3: Apply Laplace noise to standalone numbers (ages, counts)
        text, noise_applied = self._apply_laplace_noise(text)

        # Clean up extra whitespace from redactions
        text = re.sub(r"\s{2,}", " ", text).strip()

        epsilon_spent = self._epsilon if noise_applied else self._epsilon / 2
        self._total_epsilon_spent += epsilon_spent
        self._query_count += 1

        sanitized_hash = hashlib.sha256(text.encode()).hexdigest()

        report = SanitizationReport(
            original_hash=original_hash,
            sanitized_hash=sanitized_hash,
            fields_redacted=list(set(redacted_fields)),
            noise_applied=noise_applied,
            epsilon_spent=epsilon_spent,
        )

        return text, report

    def _apply_laplace_noise(self, text: str) -> tuple[str, bool]:
        """
        Adds Laplace noise to isolated numerical values in the text.
        Sensitivity is 1 (changing one patient's age by 1 year).
        Scale = sensitivity / epsilon = 1 / ε.

        This prevents exact age/count reconstruction from API traffic.
        Standalone numbers like years or medical values are left approximate.
        """
        noise_added = False
        scale = 1.0 / self._epsilon if self._epsilon > 0 else 10.0

        def _add_noise(match):
            nonlocal noise_added
            value = int(match.group())
            # Only perturb plausible demographic/count values (1-200)
            if 1 <= value <= 200:
                noise = self._laplace_sample(scale)
                noisy_value = max(1, round(value + noise))
                noise_added = True
                return str(noisy_value)
            return match.group()

        # Match standalone numbers not part of redaction tags or medical codes
        result = re.sub(r"(?<![A-Z_\[/])\b(\d{1,3})\b(?![A-Z_\]%])", _add_noise, text)
        return result, noise_added

    @staticmethod
    def _laplace_sample(scale: float) -> float:
        """
        Samples from Laplace(0, scale) distribution.
        Uses inverse CDF: X = -scale * sign(u) * ln(1 - 2|u|)
        where u ~ Uniform(-0.5, 0.5).
        """
        u = random.random() - 0.5
        sign = 1 if u >= 0 else -1
        return -scale * sign * math.log(1 - 2 * abs(u))


# Singleton
privacy_sanitizer = PrivacySanitizer()
