from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.session import Base
from backend.security.key_derivation import get_cipher

def encrypt_val(data: str) -> str:
    if not data: return data
    return get_cipher().encrypt(data.encode()).decode()

def decrypt_val(data: str) -> str:
    if not data: return data
    try:
        return get_cipher().decrypt(data.encode()).decode()
    except Exception:
        return "[ENCRYPTED_OR_CORRUPT]"

class CasualtyCard(Base):
    __tablename__ = "casualty_cards"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(String, unique=True, index=True, nullable=False)
    
    _full_name = Column("full_name", String)
    _unit = Column("unit", String)
    _injury_type = Column("injury_type", String)
    
    triage_category = Column(String) 
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship to the logs
    logs = relationship("TriageLog", back_populates="casualty")

    
    @property
    def full_name(self):
        return decrypt_val(self._full_name)

    @full_name.setter
    def full_name(self, value):
        self._full_name = encrypt_val(value)

    @property
    def unit(self):
        return decrypt_val(self._unit)

    @unit.setter
    def unit(self, value):
        self._unit = encrypt_val(value)

    @property
    def injury_type(self):
        return decrypt_val(self._injury_type)

    @injury_type.setter
    def injury_type(self, value):
        self._injury_type = encrypt_val(value)

class TriageLog(Base):
    __tablename__ = "triage_logs"

    id = Column(Integer, primary_key=True, index=True)
    casualty_id = Column(Integer, ForeignKey("casualty_cards.id"))
    
    _injury_description = Column("injury_description", String)
    predicted_category = Column(String)
    confidence = Column(Float)
    epsilon_spent = Column(Float)

    casualty = relationship("CasualtyCard", back_populates="logs")

    @property
    def injury_description(self):
        return decrypt_val(self._injury_description)

    @injury_description.setter
    def injury_description(self, value):
        self._injury_description = encrypt_val(value)
