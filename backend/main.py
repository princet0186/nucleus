from fastapi import FastAPI, HTTPException
from backend.core.config import settings
from backend.db.session import init_db
from backend.db.secure_wipe import secure_wipe_db
import uvicorn

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Offline AI for Combat Casualty Care with Anti-Extraction Privacy"
)

@app.on_event("startup")
async def startup_event():
    # Initialize the encrypted database on startup
    init_db()

@app.get("/")
async def root():
    return {
        "status": "Operational",
        "project": settings.PROJECT_NAME,
        "mode": "Offline-First",
        "security": "SQLCipher + PBKDF2 Enabled"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.VERSION}

@app.post("/privacy/panic-wipe")
async def panic_wipe():
    """
    EMERGENCY: Securely wipes the casualty database.
    This action is irreversible.
    """
    success = secure_wipe_db()
    if success:
        return {"message": "Emergency wipe completed. All casualty data destroyed."}
    else:
        raise HTTPException(status_code=500, detail="Wipe failed or database not found.")

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
