from pydantic_settings import BaseSettings
from pathlib import Path
import os


class Settings(BaseSettings):
    PROJECT_NAME: str = "Nucleus"
    VERSION: str = "2.0.0"

    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = BASE_DIR.parent / "data"
    DB_PATH: str = str(DATA_DIR / "db" / "nucleus.db")
    AUDIT_PATH: str = str(DATA_DIR / "db" / "privacy_audit.enc")

    MASTER_KEY: str = "nucleus_super_secret_field_key_2024"
    SALT: bytes = b"tactical_nucleus_salt_v1"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.0-pro"

    EPSILON_BUDGET: float = 10.0
    EPSILON_PER_QUERY: float = 0.1

    class Config:
        env_file = ".env"


settings = Settings()

os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
os.makedirs(settings.DATA_DIR / "models", exist_ok=True)
