import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet
from backend.core.config import settings

def derive_encryption_key() -> bytes:

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=settings.SALT,
        iterations=100000,
    )
    key = kdf.derive(settings.MASTER_KEY.encode())
    # Fernet requires a base64 encoded 32-byte key
    return base64.urlsafe_b64encode(key)

def get_cipher():
    return Fernet(derive_encryption_key())
