from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.core.config import settings

# Create the SQLite URL from the config path
SQLALCHEMY_DATABASE_URL = f"sqlite:///{settings.DB_PATH}"

# Setup the SQLAlchemy engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False} # Needed for SQLite
)

# Create the session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for our models
Base = declarative_base()

def init_db():
    """Initializes the database schema using SQLAlchemy models."""
    from backend.db import models # Import here to avoid circular imports
    Base.metadata.create_all(bind=engine)

def get_db():
    """Dependency for FastAPI to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
