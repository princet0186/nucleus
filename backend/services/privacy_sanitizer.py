
import re
import math
import random
import hashlib
from dataclasses import dataclass, field
from typing import Optional

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

# Generalization patterns: replace PII with context-preserving generic labels
# instead of [REDACTED] which breaks Gemini's ability to reason
_GENERALIZATION_PATTERNS = [
    (re.compile(r"\b\d{1,2}[A-Z]{3}\d{6,10}\b"), "a designated grid location"),
    (re.compile(r"-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}"), "a field position"),
    (re.compile(r"\b(ALPHA|BRAVO|CHARLIE|DELTA|ECHO|FOXTROT|GOLF|HOTEL|"
                r"INDIA|JULIET|KILO|LIMA|MIKE|NOVEMBER|OSCAR|PAPA|QUEBEC|"
                r"ROMEO|SIERRA|TANGO|UNIFORM|VICTOR|WHISKEY|XRAY|YANKEE|"
                r"ZULU)[-\s]?\d*[-\s]?(ACTUAL|SIX|MAIN|TAC)?\b",
                re.IGNORECASE), "a tactical element"),
    (re.compile(r"\b\d{2,3}\.\d{1,3}\s*[MmKk]?[Hh][Zz]\b"), "a radio channel"),
    (re.compile(r"\b\d{1,3}(st|nd|rd|th)\s+(Battalion|Brigade|Division|Regiment|"
                r"Platoon|Squad|Company|Troop)\b", re.IGNORECASE), "a military unit"),
    (re.compile(r"\b[A-Z]?\d{6,}\b"), "a service member"),
    (re.compile(r"\b(Mr|Mrs|Ms|Dr|Pvt|Sgt|Lt|Cpl|Col|Gen|Maj)\.\s+[A-Z][a-z]+\b"),
     "a personnel member"),
]

# Patterns to scrub from Gemini RESPONSES (hallucinated OPSEC data)
_RESPONSE_SCRUB_PATTERNS = [
    (re.compile(r"\b\d{1,2}[A-Z]{3}\d{6,10}\b"), "[grid reference]"),
    (re.compile(r"-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}"), "[coordinates]"),
    (re.compile(r"\b\d{2,3}\.\d{1,3}\s*[MmKk]?[Hh][Zz]\b"), "[frequency]"),
    (re.compile(r"\b\d{1,3}(st|nd|rd|th)\s+(Battalion|Brigade|Division|Regiment|"
                r"Platoon|Squad|Company|Troop)\b", re.IGNORECASE), "[unit]"),
]


@dataclass
class SanitizationReport:
    original_hash: str
    sanitized_hash: str
    fields_redacted: list[str] = field(default_factory=list)
    fields_generalized: list[str] = field(default_factory=list)
    noise_applied: bool = False
    epsilon_spent: float = 0.0


class PrivacySanitizer:
    # Strips PII and applies differential privacy before queries leave the device.

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
        original_hash = hashlib.sha256(text.encode()).hexdigest()
        redacted_fields = []
        generalized_fields = []

        # Step 1: Strip military ranks (remove entirely)
        for rank_pattern in _RANKS:
            if re.search(rank_pattern, text, re.IGNORECASE):
                text = re.sub(rank_pattern, "", text, flags=re.IGNORECASE)
                redacted_fields.append("rank")

        # Step 2: Generalize PII (context-preserving replacement)
        for pattern, replacement in _GENERALIZATION_PATTERNS:
            if pattern.search(text):
                generalized_fields.append(replacement)
                text = pattern.sub(replacement, text)

        # Step 3: Apply Laplace noise to remaining numeric values
        text, noise_applied = self._apply_laplace_noise(text)

        text = re.sub(r"\s{2,}", " ", text).strip()

        epsilon_spent = self._epsilon if noise_applied else self._epsilon / 2
        self._total_epsilon_spent += epsilon_spent
        self._query_count += 1

        sanitized_hash = hashlib.sha256(text.encode()).hexdigest()

        report = SanitizationReport(
            original_hash=original_hash,
            sanitized_hash=sanitized_hash,
            fields_redacted=list(set(redacted_fields)),
            fields_generalized=list(set(generalized_fields)),
            noise_applied=noise_applied,
            epsilon_spent=epsilon_spent,
        )

        return text, report

    def sanitize_response(self, text: str) -> tuple[str, list[str]]:
        """Scrub Gemini's response for hallucinated OPSEC data."""
        scrubbed_fields = []
        for pattern, replacement in _RESPONSE_SCRUB_PATTERNS:
            if pattern.search(text):
                scrubbed_fields.append(replacement.strip("[]"))
                text = pattern.sub(replacement, text)
        return text, scrubbed_fields

    def _apply_laplace_noise(self, text: str) -> tuple[str, bool]:
        noise_added = False
        scale = 1.0 / self._epsilon if self._epsilon > 0 else 10.0

        def _add_noise(match):
            nonlocal noise_added
            value = int(match.group())
            if 1 <= value <= 200:
                noise = self._laplace_sample(scale)
                noisy_value = max(1, round(value + noise))
                noise_added = True
                return str(noisy_value)
            return match.group()

        result = re.sub(r"(?<![A-Z_\[/])\b(\d{1,3})\b(?![A-Z_\]%])", _add_noise, text)
        return result, noise_added

    @staticmethod
    def _laplace_sample(scale: float) -> float:
        u = random.random() - 0.5
        sign = 1 if u >= 0 else -1
        return -scale * sign * math.log(1 - 2 * abs(u))

    @staticmethod
    def normalize_for_cache(text: str) -> str:
        """Normalize query for cache key: lowercase, strip stopwords, sort tokens."""
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "do", "does",
                     "in", "on", "at", "to", "for", "of", "and", "or", "but",
                     "how", "what", "when", "where", "which", "who", "that",
                     "this", "it", "i", "my", "me", "we", "our", "can", "you"}
        tokens = re.sub(r"[^\w\s]", "", text.lower()).split()
        filtered = sorted(set(t for t in tokens if t not in stopwords and len(t) > 1))
        return " ".join(filtered)


privacy_sanitizer = PrivacySanitizer()
