# Nucleus

**Offline AI for Combat Casualty Care — TCCC-Aligned Triage, Secure Casualty Tracking, and Multilingual Field Communication with Anti-Extraction Privacy Guarantees for Military Field Hospitals**

Nucleus is an offline-first AI platform built specifically for the combat medic's workflow. It provides rapid AI-assisted triage, an encrypted digital DD Form 1380 (Casualty Card), and multilingual voice translation—running entirely on a local tactical device with mathematically provable anti-extraction security.

## Core Capabilities

- **MASCAL Triage Engine**: AI-assisted NATO T1–T4 casualty classification and auto-generated 9-Line MEDEVAC requests.
- **Digital Casualty Card (DD-1380)**: Encrypted digital records replacing paper cards, preventing data loss during the Role 1 → Role 2 → Role 3 evacuation chain.
- **Tactical Multilingual Voice**: Offline speech-to-text and translation for patient interviews with non-English speakers.
- **Anti-Extraction Privacy Engine**: Application-level Fernet encryption, PBKDF2 key derivation, Differentially Private training (DP-SGD), and DoD 5220.22-M compliant "Panic Wipe".

## Quickstart

### 1. Setup Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configuration
Create your `.env` file based on the template:
```bash
cp .env.example .env
```
Update the `MASTER_KEY` in the `.env` file to a secure string.

### 3. Run the Server
```bash
export PYTHONPATH=$PYTHONPATH:.
python3 backend/main.py
```
The API will be available at `http://localhost:8000`.

## Architecture Note
This project heavily prioritizes OPSEC (Operational Security). If the device running Nucleus is captured, the combination of encrypted storage and Differentially Private AI models ensures that individual casualty data cannot be extracted by adversarial forces.
