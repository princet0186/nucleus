from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from backend.core.config import settings
from backend.db.session import init_db
from backend.services.Gemini_Services.key_manager import key_manager
from backend.api.routes.nucleus import router as nucleus_router
from backend.api.routes.maps import router as maps_router
from backend.maps import catalog as maps_catalog


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if key_manager.is_ready:
        print(f"[NUCLEUS] Gemini ready — {len(key_manager.keys)} API key(s) loaded")
    else:
        print("[NUCLEUS] Gemini NOT ready — set GEMINI_API_KEY in .env")

    regions = maps_catalog.region_names()
    if regions:
        print(f"[NUCLEUS] Offline maps ready — region(s): {', '.join(regions)}")
    else:
        print(
            f"[NUCLEUS] No offline map regions in {settings.TILES_DIR} "
            "— see docs/maps.md to build one"
        )
    yield
    print("[NUCLEUS] Server shutting down.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Privacy-Preserving AI for Military Field Operations. "
        "Gemini-powered triage, tactical assistance, and MEDEVAC generation "
        "— with differential privacy, zero-knowledge proofs, "
        "and encrypted audit trails."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(nucleus_router)
app.include_router(maps_router)


@app.get("/")
async def root():
    return {
        "status": "Operational",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "ai_engine": (
            f"Gemini ({settings.GEMINI_GENERAL_MODEL} / {settings.GEMINI_PLANNING_MODEL})"
            if key_manager.is_ready
            else "Not configured"
        ),
        "api_keys_loaded": len(key_manager.keys),
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": settings.VERSION,
        "gemini_ready": key_manager.is_ready,
    }


if __name__ == "__main__":
    import uvicorn

    # TLS 1.3 when certs are configured (see .env.example); plain HTTP is only
    # acceptable while frontend and backend share the same device.
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8800,
        reload=True,
        ssl_certfile=settings.SSL_CERTFILE or None,
        ssl_keyfile=settings.SSL_KEYFILE or None,
    )
