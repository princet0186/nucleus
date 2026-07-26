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
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_FLASH_MODEL: str = "gemini-2.5-flash"

    # --- Model routing (intent -> real Gemini model id) ------------------
    # "instant" tier: fast general query   (requested as "3.5 flash")
    # "planning" tier: triage / mascal     (requested as "3.1 pro")
    # NOTE: there is no public "gemini-3.5-flash" / "gemini-3.1-pro". These map
    # the intent to the closest real ids; override in .env when new ids ship.
    GEMINI_GENERAL_MODEL: str = "gemini-2.5-flash"
    GEMINI_GENERAL_FALLBACK: str = "gemini-2.0-flash"
    GEMINI_PLANNING_MODEL: str = "gemini-2.5-pro"
    GEMINI_PLANNING_FALLBACK: str = "gemini-2.5-flash"

    # --- Privacy / egress -------------------------------------------------
    # SANITIZE_EGRESS: tokenize PII before any text leaves for the cloud.
    # Flip to False only to demonstrate the unprotected baseline.
    # EGRESS_DEBUG: print the exact outbound prompt so the boundary is auditable.
    SANITIZE_EGRESS: bool = True
    EGRESS_DEBUG: bool = False

    # --- MEDEVAC consensus (PATE-style reliability voting) ----------------
    MEDEVAC_CONSENSUS_SAMPLES: int = 3

    # --- Offline maps (OpenStreetMap -> MBTiles) --------------------------
    # Tiles and the POI index are public OSM data: static, read-only, and NOT
    # wiped. Operator-added POIs live in nucleus.db and ARE wiped with it.
    #
    # Map queries never reach Gemini with a real coordinate. Intent detection,
    # POI lookup and distance all run locally against these files; only a
    # tokenized fact sheet ([POI_1] at [GRID_1]) is ever sent for phrasing.
    TILES_DIR: Path = DATA_DIR / "tiles"
    FONTS_DIR: Path = DATA_DIR / "tiles" / "fonts"
    # Empty = auto-select when exactly one region is installed.
    MAPS_DEFAULT_REGION: str = ""
    MAPS_SEARCH_RADIUS_KM: float = 25.0
    MAPS_MAX_SEARCH_RADIUS_KM: float = 200.0
    MAPS_MAX_RESULTS: int = 10
    MAPS_USER_POI_LIMIT: int = 5000
    # "straight_line" needs no service. Swap for "valhalla"/"osrm" when the
    # live-tracking phase lands; the RouteProvider seam keeps the API identical.
    MAPS_ROUTING_PROVIDER: str = "straight_line"
    # False = deterministic offline template, zero egress for map answers.
    MAPS_AI_PROSE: bool = True
    # Default basemap look: "day" (light street map) or "night" (dark tactical).
    # The frontend can override per-request with ?theme=; this is the fallback.
    MAPS_STYLE_THEME: str = "day"
    # Deadline for the cloud phrasing step. A degraded link blackholes packets
    # rather than refusing them, so without a deadline the request hangs and the
    # operator never receives the local answer that was ready in milliseconds.
    MAPS_AI_TIMEOUT_S: float = 8.0

    # --- Transport (TLS 1.3 when certs provided; see .env.example) --------
    SSL_CERTFILE: str = ""
    SSL_KEYFILE: str = ""
    EPSILON_BUDGET: float = 10.0
    PATE_NUM_TEACHERS: int = 8
    PATE_SIGMA1: float = 1.0
    PATE_SIGMA2: float = 1.0
    PATE_THRESHOLD: float = 5.0
    PATE_DELTA: float = 1e-6

    class Config:
        env_file = ".env"


settings = Settings()
os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
os.makedirs(settings.DATA_DIR / "models", exist_ok=True)
os.makedirs(settings.TILES_DIR, exist_ok=True)
