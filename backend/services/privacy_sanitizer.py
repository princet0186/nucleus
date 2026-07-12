import re
import math
import random
import hashlib
from dataclasses import dataclass, field
from typing import Optional
from backend.core.config import settings
from backend.security.key_derivation import hash_sha256

_RANKS = [
    r"\bPvt\b",
    r"\bPFC\b",
    r"\bSpc\b",
    r"\bCpl\b",
    r"\bSgt\b",
    r"\bSSgt\b",
    r"\bSFC\b",
    r"\bMSgt\b",
    r"\b1SG\b",
    r"\bSGM\b",
    r"\bCSM\b",
    r"\b2LT\b",
    r"\b1LT\b",
    r"\bCPT\b",
    r"\bMAJ\b",
    r"\bLTC\b",
    r"\bCOL\b",
    r"\bBG\b",
    r"\bMG\b",
    r"\bLTG\b",
    r"\bGEN\b",
    r"\bPrivate\b",
    r"\bCorporal\b",
    r"\bSergeant\b",
    r"\bLieutenant\b",
    r"\bCaptain\b",
    r"\bMajor\b",
    r"\bColonel\b",
    r"\bGeneral\b",
    r"\bLance\s+Corporal\b",
    r"\bStaff\s+Sergeant\b",
    r"\bMaster\s+Sergeant\b",
    r"\bFirst\s+Sergeant\b",
    r"\bHavildar\b",
    r"\bNaik\b",
    r"\bSepoy\b",
    r"\bSubedar\b",
    r"\bJemadar\b",
    r"\bRisaldar\b",
]
_GENERALIZATION_PATTERNS = [
    (re.compile(r"\b\d{1,2}[A-Z]{3}\d{6,10}\b"), "a designated grid location"),
    (re.compile(r"-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}"), "a field position"),
    (
        re.compile(
            r"\b(ALPHA|BRAVO|CHARLIE|DELTA|ECHO|FOXTROT|GOLF|HOTEL|"
            r"INDIA|JULIET|KILO|LIMA|MIKE|NOVEMBER|OSCAR|PAPA|QUEBEC|"
            r"ROMEO|SIERRA|TANGO|UNIFORM|VICTOR|WHISKEY|XRAY|YANKEE|"
            r"ZULU)[-\s]?\d*[-\s]?(ACTUAL|SIX|MAIN|TAC)?\b",
            re.IGNORECASE,
        ),
        "a tactical element",
    ),
    (re.compile(r"\b\d{2,3}\.\d{1,3}\s*[MmKk]?[Hh][Zz]\b"), "a radio channel"),
    (
        re.compile(
            r"\b\d{1,3}(st|nd|rd|th)\s+(Battalion|Brigade|Division|Regiment|"
            r"Platoon|Squad|Company|Troop)\b",
            re.IGNORECASE,
        ),
        "a military unit",
    ),
    (re.compile(r"\b[A-Z]?\d{6,}\b"), "a service member"),
    (
        re.compile(r"\b(Mr|Mrs|Ms|Dr|Pvt|Sgt|Lt|Cpl|Col|Gen|Maj)\.\s+[A-Z][a-z]+\b"),
        "a personnel member",
    ),
]
_RESPONSE_SCRUB_PATTERNS = [
    (re.compile(r"\b\d{1,2}[A-Z]{3}\d{6,10}\b"), "[grid reference]"),
    (re.compile(r"-?\d{1,3}\.\d{3,}\s*,\s*-?\d{1,3}\.\d{3,}"), "[coordinates]"),
    (re.compile(r"\b\d{2,3}\.\d{1,3}\s*[MmKk]?[Hh][Zz]\b"), "[frequency]"),
    (
        re.compile(
            r"\b\d{1,3}(st|nd|rd|th)\s+(Battalion|Brigade|Division|Regiment|"
            r"Platoon|Squad|Company|Troop)\b",
            re.IGNORECASE,
        ),
        "[unit]",
    ),
]


@dataclass
class SanitizationReport:
    original_hash: str
    sanitized_hash: str
    fields_redacted: list[str] = field(default_factory=list)
    fields_generalized: list[str] = field(default_factory=list)
    pate_applied: bool = False
    epsilon_spent: float = 0.0


@dataclass
class PATEVoteResult:
    selected_label: Optional[str]
    is_answered: bool
    vote_counts: dict[str, int] = field(default_factory=dict)
    consensus_ratio: float = 0.0
    epsilon_spent: float = 0.0


TRIAGE_LABELS = ["T1-IMMEDIATE", "T2-DELAYED", "T3-MINIMAL", "T4-EXPECTANT"]
PATE_TRIAGE_INSTRUCTION = (
    "You are a TCCC (Tactical Combat Casualty Care) triage expert.\n"
    "Classify the following injury into exactly one category:\n"
    "- T1-IMMEDIATE: Life-threatening, survivable with immediate intervention\n"
    "- T2-DELAYED: Serious but can wait 4-6 hours\n"
    "- T3-MINIMAL: Walking wounded, minor injuries\n"
    "- T4-EXPECTANT: Not survivable with available resources\n\n"
    "Respond with ONLY the category label (e.g., T1-IMMEDIATE). No explanation."
)
_PRIVATE_TRIAGE_EXAMPLES = [
    {
        "text": "Tension pneumothorax with tracheal deviation and absent breath sounds on left",
        "label": "T1-IMMEDIATE",
    },
    {
        "text": "Massive hemorrhage from femoral artery, no tourniquet applied, blood pooling",
        "label": "T1-IMMEDIATE",
    },
    {
        "text": "Penetrating chest wound with audible sucking sound, severe respiratory distress",
        "label": "T1-IMMEDIATE",
    },
    {
        "text": "Complete airway obstruction from maxillofacial blast injury, GCS dropping to 6",
        "label": "T1-IMMEDIATE",
    },
    {
        "text": "Open fracture of tibial shaft with controlled bleeding, distal pulses present",
        "label": "T2-DELAYED",
    },
    {
        "text": "Penetrating abdominal wound with stable hemodynamics, alert and oriented",
        "label": "T2-DELAYED",
    },
    {
        "text": "Second-degree burns across 15 percent TBSA, coherent and ambulatory with assistance",
        "label": "T2-DELAYED",
    },
    {
        "text": "Closed humeral fracture with intact neurovascular status, pain controlled",
        "label": "T2-DELAYED",
    },
    {
        "text": "Superficial lacerations to bilateral forearms from glass, self-ambulatory",
        "label": "T3-MINIMAL",
    },
    {
        "text": "Minor abrasions and contusions from blast concussion wave, no LOC, GCS 15",
        "label": "T3-MINIMAL",
    },
    {
        "text": "Grade 1 ankle sprain from debris, able to bear partial weight with assistance",
        "label": "T3-MINIMAL",
    },
    {
        "text": "Small superficial shrapnel wound to lateral deltoid, bleeding controlled with pressure",
        "label": "T3-MINIMAL",
    },
    {
        "text": "Massive craniocerebral trauma with exposed brain matter, fixed dilated pupils, no pulse",
        "label": "T4-EXPECTANT",
    },
    {
        "text": "Full-thickness burns over 95 percent TBSA with absent peripheral pulses, agonal breathing",
        "label": "T4-EXPECTANT",
    },
    {
        "text": "Complete high cervical spine transection at C2, no motor or sensory response below",
        "label": "T4-EXPECTANT",
    },
    {
        "text": "Bilateral above-knee traumatic amputations with uncontrolled hemorrhage, prolonged asystole",
        "label": "T4-EXPECTANT",
    },
]


class PromptPATEAggregator:
    def __init__(self):
        self._sigma1 = settings.PATE_SIGMA1
        self._sigma2 = settings.PATE_SIGMA2
        self._threshold = settings.PATE_THRESHOLD
        self._num_teachers = settings.PATE_NUM_TEACHERS
        self._delta = settings.PATE_DELTA
        self._total_epsilon_spent = 0.0
        self._queries_answered = 0
        self._queries_rejected = 0
        self._teacher_partitions = self._partition_teachers(
            _PRIVATE_TRIAGE_EXAMPLES, self._num_teachers
        )

    @property
    def total_epsilon_spent(self) -> float:
        return self._total_epsilon_spent

    @property
    def epsilon_remaining(self) -> float:
        return max(0, settings.EPSILON_BUDGET - self._total_epsilon_spent)

    @property
    def queries_answered(self) -> int:
        return self._queries_answered

    @property
    def queries_rejected(self) -> int:
        return self._queries_rejected

    @property
    def num_teachers(self) -> int:
        return self._num_teachers

    def _partition_teachers(
        self, examples: list[dict], n_teachers: int
    ) -> list[list[dict]]:
        shuffled = examples.copy()
        random.Random(42).shuffle(shuffled)
        teachers = [[] for _ in range(n_teachers)]
        for i, example in enumerate(shuffled):
            teachers[i % n_teachers].append(example)
        return teachers

    def get_teacher_prompts(self, instruction: str = None) -> list[str]:
        inst = instruction or PATE_TRIAGE_INSTRUCTION
        prompts = []
        for partition in self._teacher_partitions:
            parts = [inst, "Examples:"]
            for ex in partition:
                parts.append(f"Injury: {ex['text']}\nCategory: {ex['label']}")
            prompts.append("\n\n".join(parts))
        return prompts

    def confident_gnmax(
        self,
        teacher_votes: list[str],
        candidate_labels: list[str] = None,
    ) -> PATEVoteResult:
        labels = candidate_labels or TRIAGE_LABELS
        vote_counts = {label: 0 for label in labels}
        for vote in teacher_votes:
            cleaned = vote.strip().upper()
            for label in labels:
                if label in cleaned:
                    vote_counts[label] += 1
                    break
        total_votes = sum(vote_counts.values())
        counts = list(vote_counts.values())
        label_list = list(vote_counts.keys())
        if total_votes == 0:
            return PATEVoteResult(
                selected_label=None,
                is_answered=False,
                vote_counts=vote_counts,
                consensus_ratio=0.0,
                epsilon_spent=0.0,
            )
        max_count = max(counts)
        noisy_max = max_count + random.gauss(0, self._sigma1)
        if noisy_max < self._threshold:
            self._queries_rejected += 1
            return PATEVoteResult(
                selected_label=None,
                is_answered=False,
                vote_counts=vote_counts,
                consensus_ratio=max_count / total_votes,
                epsilon_spent=0.0,
            )
        noisy_counts = [c + random.gauss(0, self._sigma2) for c in counts]
        winner_idx = noisy_counts.index(max(noisy_counts))
        winner_label = label_list[winner_idx]
        epsilon_spent = self._rdp_privacy_cost(counts)
        self._total_epsilon_spent += epsilon_spent
        self._queries_answered += 1
        return PATEVoteResult(
            selected_label=winner_label,
            is_answered=True,
            vote_counts=vote_counts,
            consensus_ratio=max_count / total_votes,
            epsilon_spent=epsilon_spent,
        )

    def _rdp_privacy_cost(self, vote_counts: list[int]) -> float:
        sorted_counts = sorted(vote_counts, reverse=True)
        if len(sorted_counts) < 2:
            return 0.0
        top1, top2 = sorted_counts[0], sorted_counts[1]
        margin = top1 - top2
        q = math.exp(-0.5 * (margin / self._sigma2) ** 2)
        if q >= 1.0:
            return 1.0
        if q < 1e-15:
            return 0.0
        best_epsilon = float("inf")
        for alpha in [2, 4, 8, 16, 32, 64, 128, 256]:
            try:
                rdp_cost = alpha * q**2 / (2.0 * max((1.0 - q) ** 2, 1e-10))
            except (OverflowError, ZeroDivisionError):
                continue
            epsilon = rdp_cost + math.log(1.0 / self._delta) / (alpha - 1)
            best_epsilon = min(best_epsilon, epsilon)
        return min(best_epsilon, 1.0)

    def generate_student_prompt(
        self,
        public_examples: list[dict],
        noisy_labels: list[Optional[str]],
        instruction: str = None,
    ) -> str:
        inst = instruction or PATE_TRIAGE_INSTRUCTION
        parts = [inst, "Examples:"]
        for example, label in zip(public_examples, noisy_labels):
            if label is not None:
                parts.append(f"Injury: {example['text']}\nCategory: {label}")
        return "\n\n".join(parts)


class PrivacySanitizer:
    def __init__(self):
        self._pate = PromptPATEAggregator()
        self._query_count = 0

    @property
    def total_epsilon_spent(self) -> float:
        return self._pate.total_epsilon_spent

    @property
    def epsilon_remaining(self) -> float:
        return self._pate.epsilon_remaining

    @property
    def query_count(self) -> int:
        return self._query_count

    @property
    def pate(self) -> PromptPATEAggregator:
        return self._pate

    def sanitize(self, text: str) -> tuple[str, SanitizationReport]:
        original_hash = hash_sha256(text)
        redacted_fields = []
        generalized_fields = []
        for rank_pattern in _RANKS:
            if re.search(rank_pattern, text, re.IGNORECASE):
                text = re.sub(rank_pattern, "", text, flags=re.IGNORECASE)
                redacted_fields.append("rank")
        for pattern, replacement in _GENERALIZATION_PATTERNS:
            if pattern.search(text):
                generalized_fields.append(replacement)
                text = pattern.sub(replacement, text)
        text = re.sub(r"\s{2,}", " ", text).strip()
        sanitized_hash = hash_sha256(text)
        self._query_count += 1
        report = SanitizationReport(
            original_hash=original_hash,
            sanitized_hash=sanitized_hash,
            fields_redacted=list(set(redacted_fields)),
            fields_generalized=list(set(generalized_fields)),
            pate_applied=False,
            epsilon_spent=0.0,
        )
        return text, report

    def sanitize_response(self, text: str) -> tuple[str, list[str]]:
        scrubbed_fields = []
        for pattern, replacement in _RESPONSE_SCRUB_PATTERNS:
            if pattern.search(text):
                scrubbed_fields.append(replacement.strip("[]"))
                text = pattern.sub(replacement, text)
        return text, scrubbed_fields

    @staticmethod
    def normalize_for_cache(text: str) -> str:
        stopwords = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "do",
            "does",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "and",
            "or",
            "but",
            "how",
            "what",
            "when",
            "where",
            "which",
            "who",
            "that",
            "this",
            "it",
            "i",
            "my",
            "me",
            "we",
            "our",
            "can",
            "you",
        }
        tokens = re.sub(r"[^\w\s]", "", text.lower()).split()
        filtered = sorted(set(t for t in tokens if t not in stopwords and len(t) > 1))
        return " ".join(filtered)


privacy_sanitizer = PrivacySanitizer()
