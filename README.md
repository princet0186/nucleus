# Nucleus 

Welcome to Nucleus AI.

This project is a supportive tool designed to assist combat medics in high-stress, offline(hybrid) environments.

When the medical team is working in the field, they often need to make quick decisions about medical care, triage, and casualty management. Nucleus helps by providing an intelligent assistant that can analyze medical descriptions, suggest treatment protocols, and manage casualty records in mass casualty events. Importantly, it is built to keep all patient and operational data secure and private, ensuring that sensitive information never leaves the device or gets exposed unnecessarily.

## Core Features

### 1. Medical Assistance Tools
*   **Triage Assistant**: Medics can enter a description of a casualty's injuries. The system then helps classify the urgency of the injuries (using standard military categories like Immediate or Delayed) and suggests step-by-step treatment protocols.
*   **MEDEVAC Request Generator**: A simple tool that automatically formats a standard 9-line medical evacuation request, so the medic can quickly radio for help.

### 2. Privacy and Data Security
Operating in the field means data security is a top priority. Nucleus uses a multi-layered approach to protect sensitive information before any AI processing happens:
1.  **Removing Personal Identifiers**: The system automatically scans for and removes sensitive details like military ranks, unit names, and specific locations.
2.  **Adding Privacy Noise**: It slightly alters numerical data (like age) just enough to protect the individual's identity without changing the medical context.
3.  **Data Verification**: It creates a secure digital receipt (using a hashing method) to prove that the data was safely sanitized before being processed.
4.  **Local Encryption**: Any patient records saved on the device are fully encrypted so they cannot be read if the device is lost or captured.
5.  **Emergency Wipe**: A secure wipe function is available to immediately delete all data if necessary.

---

## API Endpoints

The system provides several straightforward endpoints to handle these tasks:
*   `POST /nucleus/query` — For general questions.
*   `POST /nucleus/triage` — To evaluate and classify injuries.
*   `POST /nucleus/mascal` — To plan a mass-casualty response.
*   `POST /nucleus/medevac` — To build a deterministic 9-line from form fields (offline).
*   `POST /nucleus/medevac/generate` — To draft a consensus-voted 9-line from chat context.
*   `GET /maps/...` — Offline map tiles, styles, and local facility search.

---

## Getting Started

### 1. What You Need
*   Python (version 3.12 or newer)
*   Node.js (version 18 or newer)

### 2. Setup
Create a `.env` file in the main folder and add your keys:
```env
MASTER_KEY="your_secure_passphrase"
GEMINI_API_KEY="your_google_gemini_api_key"
```

### 3. Running the Project

**One command (backend + frontend together):**
```bash
./dev.sh
```
*Activates the venv, then starts the backend at `http://localhost:8800` and the frontend at `http://localhost:3000`. Ctrl-C stops both.*

**Or start each part manually:**

Backend server:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. python3 backend/main.py
```
*The server will start at `http://localhost:8800` (API documentation is at `/docs`).*

Frontend interface:
```bash
cd frontend
npm install
npm run dev
```
*The user interface will be available at `http://localhost:3000`.*

---

## Docker Deployment

If you prefer to run the backend in an isolated container, you can use Docker:

```bash
# Build the Docker image
docker build -t nucleus-backend .

# Run the container
docker run -d -p 8800:8800 --env-file .env nucleus-backend
```
