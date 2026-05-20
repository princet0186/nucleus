# Nucleus AI Studio ✦

**Offline-First Combat Casualty Care & Tactical Intelligence Engine powered by Gemini 3.0 Pro with mathematically provable Anti-Extraction Privacy guarantees.**

Nucleus AI Studio is a next-generation decision-support and tactical operations platform designed for forward-deployed combat medics (Role 1 and Role 2 medical care). Built for offline tactical environments, it delivers advanced medical reasoning, drug interaction checking, and secure patient logging while maintaining strict operational security (OPSEC).

---

## ✦ Core Capabilities

### 1. Modern AI Studio Playgrounds
*   **MASCAL Triage Playground**: Input combat casualty trauma reports. Gemini 3.0 Pro analyzes clinical descriptions, classifies injuries into standard NATO precedence categories (`T1-IMMEDIATE`, `T2-DELAYED`, `T3-MINIMAL`, `T4-EXPECTANT`), and outputs step-by-step TCCC treatment protocols.
*   **Drug Formulary Playground**: Analyze battlefield drug combinations (e.g. Ketamine, Morphine, Fentanyl) against patient context (e.g. hemorrhagic shock) to flag lethal contraindications before administration.
*   **MEDEVAC Builder**: A deterministic, zero-net-dependency NATO-standard 9-Line evacuation request generator ready for secure radio transmission.

### 2. Zero-Retention On-Device Privacy Gateway
When operating on contested battlefields, cloud-based LLM queries risk leaking troop movements, rank designations, and operational sizes to adversary intercept networks. Nucleus filters all queries through a multi-layer **Privacy Gateway** *before* they leave the field device:
1.  **PII Sanitizer**: Scans and strips military ranks, unit call signs, locations, MGRS grid coordinates, and personal identifiers.
2.  **Differential Privacy**: Perturbs numeric data (e.g. patient age) using local Laplace noise mechanism (calibrated by an epsilon privacy budget $\epsilon$) to prevent tracking of unique individuals.
3.  **Zero-Knowledge Proofs (ZKP)**: Uses a cryptographic SHA-256 hash-commitment scheme. Medics receive verifiable proof that data was sanitized and processed without exposing the original query content.
4.  **Automatic DB Encryption**: Patient cards are stored in SQLite using automatic field-level **AES-128-CBC + HMAC-SHA256** (Fernet) encryption. Cryptographic keys are dynamically derived at boot time using **PBKDF2** with 100,000 iterations.
5.  **DoD 5220.22-M Secure Wipe**: Instant emergency wipe protocol for high-risk capture scenarios.

---

### API Endpoints:
*   `POST /nucleus/query` — General military operations assistant.
*   `POST /nucleus/triage` — Structured clinical MASCAL triage classification.
*   `POST /nucleus/drug-check` — Pharmacological interaction checker.
*   `POST /nucleus/medevac` — Deterministic 9-Line generator.
*   `POST /nucleus/casualties` — Register casualty (PII auto-encrypted).
*   `GET /nucleus/casualties` — List active casualties (PII decrypted in-memory).
*   `DELETE /nucleus/casualties/{patient_id}` — Secure discharge and card deletion.

---

## ✦ Getting Started

### 1. Prerequisites
*   Python 3.12 or 3.13
*   Node.js (v18+)

### 2. Configure Environment variables
Create a `.env` file in the root directory:
```env
MASTER_KEY="your_secure_pbkdf2_derivation_passphrase"
GEMINI_API_KEY="your_google_gemini_api_key"
```

### 3. Run Locally

#### Run the Backend Server:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python3 backend/main.py
```
*The FastAPI server runs at `http://localhost:8000` with Swagger docs available at `/docs`.*

#### Run the Frontend Studio:
```bash
cd frontend
npm install
npm run dev
```
*The studio interface runs at `http://localhost:3000`.*

---

## ✦ Docker Deployment

You can deploy the backend securely as a self-contained container using the optimized Docker configurations:

```bash
# Build the Docker image
docker build -t nucleus-backend .

# Run the container
docker run -d -p 8000:8000 --env-file .env nucleus-backend
```
