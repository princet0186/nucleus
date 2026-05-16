from pydantic_settings import BaseSettings
from pathlib import Path
import os

class Settings(BaseSettings):
    PROJECT_NAME: str = "Nucleus"
    VERSION: str = "1.0.0"
    
    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR.parent / "data"
    DB_PATH: str = str(DATA_DIR / "db" / "nucleus.db")
    
    # Security
    MASTER_KEY: str = "nucleus_super_secret_field_key_2024" # Default for dev
    SALT: bytes = b"tactical_nucleus_salt_v1"
    
    # Privacy
    EPSILON_LIMIT: float = 8.0
    
    class Config:
        env_file = ".env"

settings = Settings()

# Ensure directories exist
os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
os.makedirs(settings.DATA_DIR / "models", exist_ok=True)
