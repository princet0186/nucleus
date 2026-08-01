# Extracted Code Documentation

## /Users/princetrivedi/Desktop/repos/nucleus/backend/main.py

Inline Comment: # AI-powered endpoints (Gemini + privacy pipeline)


## /Users/princetrivedi/Desktop/repos/nucleus/backend/core/config.py

Inline Comment: # PromptPATE Settings (Duan et al., 2023 — arXiv:2305.15594)
Inline Comment: # Gaussian noise for consensus threshold check
Inline Comment: # Gaussian noise for label selection
Inline Comment: # Minimum noisy vote count to answer a query
Inline Comment: # δ parameter for (ε, δ)-differential privacy


## /Users/princetrivedi/Desktop/repos/nucleus/backend/core/__init__.py

Inline Comment: # Nucleus Core


## /Users/princetrivedi/Desktop/repos/nucleus/backend/security/__init__.py

Inline Comment: # Nucleus Security


## /Users/princetrivedi/Desktop/repos/nucleus/backend/security/key_derivation.py

Inline Comment: # Fernet requires a base64 encoded 32-byte key


## /Users/princetrivedi/Desktop/repos/nucleus/backend/models/__init__.py

Inline Comment: # Nucleus Models (Pydantic Schemas)


## /Users/princetrivedi/Desktop/repos/nucleus/backend/db/models.py

Inline Comment: # Relationship to the logs


## /Users/princetrivedi/Desktop/repos/nucleus/backend/db/secure_wipe.py

Inline Comment: # Implements a DoD 5220.22-M style secure wipe of the database file.


## /Users/princetrivedi/Desktop/repos/nucleus/backend/db/session.py

Inline Comment: # Import here to avoid circular imports


## /Users/princetrivedi/Desktop/repos/nucleus/backend/db/__init__.py

Inline Comment: # Nucleus Database


## /Users/princetrivedi/Desktop/repos/nucleus/backend/api/__init__.py

Inline Comment: # Nucleus API Routes


## /Users/princetrivedi/Desktop/repos/nucleus/backend/api/routes/__init__.py

Inline Comment: # Nucleus API Routes


## /Users/princetrivedi/Desktop/repos/nucleus/backend/api/routes/nucleus.py

Inline Comment: # Parse structured triage data if Gemini returned valid JSON


## /Users/princetrivedi/Desktop/repos/nucleus/backend/services/zero_knowledge.py

Inline Comment: # Generate a random 32-byte nonce
Inline Comment: # Hash of the sanitized output (this is what was actually sent)
Inline Comment: # Proof: ties the commitment to the sanitized output


## /Users/princetrivedi/Desktop/repos/nucleus/backend/services/__init__.py

Inline Comment: # Nucleus Services


## /Users/princetrivedi/Desktop/repos/nucleus/backend/services/medevac_generator.py

Inline Comment: # Urgent
Inline Comment: # Priority
Inline Comment: # Routine
Inline Comment: # Expectant
Inline Comment: # Try AI generation first


## /Users/princetrivedi/Desktop/repos/nucleus/backend/services/gemini_service.py

### triage
PromptPATE-powered triage classification.

Flow:
1. PII sanitization of the injury description
2. ZKP commitment for audit trail
3. Teacher ensemble queries (parallel, using Gemini Flash)
4. Confident-GNMax aggregation → private triage category
5. Detailed treatment protocol (single Gemini Pro call)
6. Response scrubbing + audit logging

### _query_teacher
Query one teacher LLM and return its triage vote.

Inline Comment: # System prompt for general military/tactical queries
Inline Comment: # System prompt for specialized medical triage
Inline Comment: # Build full prompt from injury + demographics
Inline Comment: # Step 1: PII sanitization (ranks, grid refs, call signs)
Inline Comment: # Step 2: ZKP commitment for audit
Inline Comment: # Step 3: Timing jitter (anti-traffic-analysis)
Inline Comment: # Step 4: Query each teacher in the PATE ensemble (parallel)
Inline Comment: # Step 5: Confident-GNMax aggregation (the DP mechanism)
Inline Comment: # Step 6: Get detailed treatment protocol using the privately-determined category
Inline Comment: # Step 7: Response scrubbing
Inline Comment: # Step 8: Audit log
Inline Comment: # Parse triage JSON and override category with PATE's private aggregate
Inline Comment: # Step 1: Pre-execution Data Sanitization (Minimization + Generalization)
Inline Comment: # Content Policy Check
Inline Comment: # Step 2: Zero Knowledge Commitment for Audit
Inline Comment: # Step 3: Local Encrypted Response Cache Lookup (with Fuzzy Query Normalization)
Inline Comment: # Zero DP budget spent on cache hits
Inline Comment: # Step 4: Metadata Sanitization - Timing Pattern Jitter (50-200ms)
Inline Comment: # Bandwidth/Latency Tuning: Choose Gemini Flash for general queries, Pro for specialized triage
Inline Comment: # Step 5: Post-Execution Response Scrubbing
Inline Comment: # Store to cache


## /Users/princetrivedi/Desktop/repos/nucleus/backend/services/encryption_layer.py

Inline Comment: # 48 hours
Inline Comment: # --- Encrypted Response Cache ---
Inline Comment: # --- Audit Log ---


## /Users/princetrivedi/Desktop/repos/nucleus/backend/services/privacy_sanitizer.py

### Module
Privacy Sanitizer for Nucleus AI — PromptPATE Edition

This module implements the privacy pipeline for Nucleus AI, combining:
1. PII Sanitization: Regex-based removal and generalization of military-sensitive
   identifiers (ranks, grid references, call signs, unit names, etc.)
2. PromptPATE Aggregation: Differentially private ensemble voting using the
   Confident-GNMax mechanism for private triage classification.

Reference: "Flocks of Stochastic Parrots: Differentially Private Prompt Learning
for Large Language Models" — Duan, Dziedzic, Papernot, Boenisch (2023)
arXiv:2305.15594

Architecture Change (v2):
  Replaced Local DP (Laplace noise on individual numeric fields) with PromptPATE's
  Confident-GNMax ensemble aggregation. Key improvements:
  - Stronger formal (ε, δ)-DP guarantees via Rényi DP accounting
  - Better utility: no noise injected into the query text itself
  - Data-dependent privacy costs: high teacher consensus = lower ε spend
  - Aligns with state-of-the-art research in privacy-preserving LLM usage

### SanitizationReport
Report from the pre-query PII sanitization step.

### PATEVoteResult
Result from a single round of Confident-GNMax aggregation.

### PromptPATEAggregator
PromptPATE: Privacy-preserving prompt learning via noisy ensemble voting.

Based on the Confident-GNMax mechanism from PATE (Papernot et al., 2018)
adapted for LLM prompt ensembles (Duan et al., 2023).

How it works:
  1. Private data is partitioned into disjoint subsets (one per teacher).
  2. Each teacher = the LLM prompted with its private subset as few-shot examples.
  3. For each input, all teachers independently predict a label (triage category).
  4. Confident-GNMax aggregates votes with two-phase Gaussian noise:
     - Phase 1 (σ1): Noisy threshold check — reject low-consensus queries.
     - Phase 2 (σ2): Noisy argmax — select the private label.
  5. Privacy cost is computed via data-dependent Rényi DP accounting.
     High consensus → low cost (unanimous teachers reveal nothing).

Privacy Guarantee:
  Each answered query satisfies (ε, δ)-DP where ε depends on teacher
  consensus and δ = PATE_DELTA (default 10⁻⁶).

### PrivacySanitizer
Nucleus AI Privacy Engine — PromptPATE Edition.

Combines two orthogonal privacy protection layers:

Layer 1 — PII Sanitization (applied to EVERY query):
  Regex-based stripping and generalization of military-sensitive identifiers.
  This is a data minimization technique, not a DP mechanism.

Layer 2 — PromptPATE Aggregation (applied to triage/classification queries):
  Differential privacy through Confident-GNMax voting among an ensemble of
  teacher prompts. Provides formal (ε, δ)-DP guarantees.

Architecture:
  PII sanitization runs in sanitize() — called for every query.
  PATE aggregation is orchestrated by gemini_service.py, which calls
  pate.get_teacher_prompts() and pate.confident_gnmax().

### _partition_teachers
Partition private examples into disjoint subsets for each teacher.

Disjointness is CRITICAL for PATE's privacy guarantee:
- Changing one private example affects exactly ONE teacher.
- The sensitivity of the vote count vector is bounded by 1.
- This enables tight privacy accounting via RDP.

With 16 examples and 8 teachers → each teacher gets 2 few-shot examples.

### get_teacher_prompts
Build a discrete prompt string for each teacher.

Each prompt = shared instruction + that teacher's unique few-shot examples.
Returns one prompt per teacher (num_teachers total).

### confident_gnmax
Confident-GNMax: Two-phase noisy aggregation of teacher votes.

Phase 1 — Threshold Check:
  noisy_max = max(vote_counts) + N(0, σ1²)
  If noisy_max < T: REJECT (consensus too low, would leak private info).
  Rejected queries consume ZERO privacy budget.

Phase 2 — Noisy Selection:
  For each label: noisy_count = count + N(0, σ2²)
  Return label with highest noisy_count.

Args:
    teacher_votes: Raw text predictions from each teacher LLM.
    candidate_labels: Valid labels (default: TRIAGE_LABELS).

Returns:
    PATEVoteResult with the private aggregated label and ε cost.

### _rdp_privacy_cost
Data-dependent Rényi DP privacy cost per answered query.

Based on the RDP analysis from Papernot et al. (2018), Theorem 1:
The privacy cost depends on the MARGIN between the top-2 vote counts.
Larger margin (higher consensus) → exponentially lower cost.

Intuition: If all teachers unanimously agree, the vote reveals nothing
about any individual teacher's private data — sensitivity is 1, but the
signal-to-noise ratio makes the output independent of any single vote.

We optimize over multiple RDP orders α to find the tightest (ε, δ)-DP
bound, matching the paper's data-dependent accounting approach:
  For each α: ε_α = RDP_cost(α) + log(1/δ) / (α - 1)
  Return min over all α.

### generate_student_prompt
Create a public student prompt from noisy teacher-labeled public data.

The student prompt contains ZERO private data — only:
- Public input sequences (non-sensitive)
- Labels assigned by the noisy teacher ensemble

This prompt is safe for deployment, storage in source code, and
transmission. It satisfies the same (ε, δ)-DP guarantee as the
aggregation step that produced the labels.

### pate
Access the PATE aggregator for teacher ensemble voting.

### sanitize
Pre-query PII sanitization pipeline.

Step 1: Strip military ranks (complete removal)
Step 2: Generalize sensitive patterns (context-preserving replacement)

NOTE: Unlike v1, NO Laplace noise is applied to the query text.
Differential privacy is now achieved via PromptPATE's Confident-GNMax
at the service layer, providing stronger (ε, δ)-DP guarantees while
preserving full query utility for the LLM.

### sanitize_response
Scrub Gemini's response for hallucinated OPSEC data.

### normalize_for_cache
Normalize query for cache key: lowercase, strip stopwords, sort tokens.

Inline Comment: # PII PATTERNS — Orthogonal to DP, applied to every query
Inline Comment: # Military ranks that should be stripped from queries
Inline Comment: # Generalization patterns: replace PII with context-preserving generic labels
Inline Comment: # instead of [REDACTED] which breaks Gemini's ability to reason
Inline Comment: # Patterns to scrub from Gemini RESPONSES (hallucinated OPSEC data)
Inline Comment: # PROMPTPATE DATA STRUCTURES
Inline Comment: # PRIVATE TEACHER DATA
Inline Comment: # Instruction shared by all teachers — contains no private data.
Inline Comment: # Private few-shot examples partitioned among teachers.
Inline Comment: # In production, these originate from an encrypted classified medical database.
Inline Comment: # Each teacher receives a DISJOINT subset — this disjointness is the foundation
Inline Comment: # of PATE's privacy guarantee: changing one example affects exactly one teacher.
Inline Comment: # T1-IMMEDIATE
Inline Comment: # T2-DELAYED
Inline Comment: # T3-MINIMAL
Inline Comment: # T4-EXPECTANT
Inline Comment: # PROMPTPATE AGGREGATOR — Confident-GNMax
Inline Comment: # Partition private examples into disjoint teacher subsets
Inline Comment: # Seeded for reproducibility
Inline Comment: # Parse teacher votes into canonical label counts
Inline Comment: # Rejected queries spend ZERO budget
Inline Comment: # Probability of noise flipping the majority vote
Inline Comment: # Worst case: no consensus at all
Inline Comment: # Near-zero flip probability → negligible cost
Inline Comment: # Optimize over multiple RDP orders for tightest bound
Inline Comment: # RDP at order α (data-dependent bound from Papernot 2018)
Inline Comment: # Convert RDP → (ε, δ)-DP
Inline Comment: # Cap at 1.0 per query
Inline Comment: # MAIN PRIVACY SANITIZER
Inline Comment: # Step 1: Strip military ranks (remove entirely)
Inline Comment: # Step 2: Generalize PII (context-preserving replacement)
Inline Comment: # PATE runs at service layer, not here
Inline Comment: # ε is tracked by the PATE aggregator



# Frontend Extracted Comments

## /Users/princetrivedi/Desktop/repos/nucleus/frontend/src/pages/CasualtyTrackerPage.jsx

Inline Comment: New Casualty Form State
Inline Comment: localhost:8000/nucleus/casualty');
Inline Comment: localhost:8000/nucleus/casualty/create', {
Inline Comment: refresh list
Inline Comment: localhost:8000/nucleus/casualty/${patient_id}`, {
Inline Comment: refresh list


## /Users/princetrivedi/Desktop/repos/nucleus/frontend/src/pages/MedevacPage.jsx

Inline Comment: Left Pane - Input
Inline Comment: Triage Selection
Inline Comment: Right Pane - Results


## /Users/princetrivedi/Desktop/repos/nucleus/frontend/src/pages/TriagePage.jsx

Inline Comment: Left Pane - Input
Inline Comment: Right Pane - Results & Privacy Metadata

