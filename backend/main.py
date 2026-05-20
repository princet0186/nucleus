
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from backend.core.config import settings
from backend.db.session import init_db
from backend.services.gemini_engine import nucleus_ai
from backend.api.routes.nucleus import router as nucleus_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    nucleus_ai.initialize()
    yield
    print("[NUCLEUS] Server shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Privacy-Preserving AI for Military Field Operations. "
        "Gemini-powered triage, tactical assistance, and drug interaction "
        "analysis — with differential privacy, zero-knowledge proofs, "
        "and encrypted audit trails."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# AI-powered endpoints (Gemini + privacy pipeline)
app.include_router(nucleus_router)


@app.get("/")
async def root():
    return {
        "status": "Operational",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "ai_engine": "Gemini " + settings.GEMINI_MODEL if nucleus_ai.is_ready else "Not configured",
        "privacy": {
            "encryption": "Fernet AES-128-CBC + PBKDF2",
            "differential_privacy": "Laplace Mechanism (local DP)",
            "zero_knowledge_proofs": "SHA-256 Hash Commitment",
        },
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "gemini_ready": nucleus_ai.is_ready,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
