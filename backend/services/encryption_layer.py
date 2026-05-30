
import json
import os
import time
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64
import hashlib

from backend.core.config import settings

CACHE_TTL_SECONDS = 48 * 60 * 60  # 48 hours


def _derive_fernet_key(master_key: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(master_key.encode()))


class EncryptionLayer:


    def __init__(self):
        self._fernet = Fernet(
            _derive_fernet_key(settings.MASTER_KEY, settings.SALT)
        )
        self._audit_path = settings.AUDIT_PATH
        self._cache_dir = os.path.join(os.path.dirname(settings.DB_PATH), "query_cache")
        os.makedirs(self._cache_dir, exist_ok=True)

    def encrypt(self, plaintext: str) -> str:

        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:

        return self._fernet.decrypt(ciphertext.encode()).decode()

    # --- Encrypted Response Cache ---

    def cache_key(self, normalized_query: str) -> str:
        return hashlib.sha256(normalized_query.encode()).hexdigest()

    def get_cached_response(self, normalized_query: str) -> dict | None:
        key = self.cache_key(normalized_query)
        path = os.path.join(self._cache_dir, f"{key}.enc")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                encrypted = f.read().strip()
            decrypted = self.decrypt(encrypted)
            entry = json.loads(decrypted)
            if time.time() - entry.get("cached_at", 0) > CACHE_TTL_SECONDS:
                os.remove(path)
                return None
            return entry
        except Exception:
            return None

    def set_cached_response(self, normalized_query: str, response_text: str, mode: str) -> None:
        key = self.cache_key(normalized_query)
        path = os.path.join(self._cache_dir, f"{key}.enc")
        entry = {
            "response": response_text,
            "mode": mode,
            "cached_at": time.time(),
        }
        encrypted = self.encrypt(json.dumps(entry))
        with open(path, "w") as f:
            f.write(encrypted)

    # --- Audit Log ---

    def log_query(self, query_id: str, sanitized_query: str,
                  response_summary: str, epsilon_spent: float,
                  zkp_commitment: str) -> None:

        entry = {
            "query_id": query_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sanitized_query_hash": self._hash_text(sanitized_query),
            "response_length": len(response_summary),
            "epsilon_spent": epsilon_spent,
            "zkp_commitment": zkp_commitment,
        }
        encrypted_entry = self.encrypt(json.dumps(entry))

        with open(self._audit_path, "a") as f:
            f.write(encrypted_entry + "\n")

    def read_audit_log(self) -> list[dict]:

        if not os.path.exists(self._audit_path):
            return []

        entries = []
        with open(self._audit_path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    decrypted = self.decrypt(line)
                    entries.append(json.loads(decrypted))
        return entries

    def wipe_audit_log(self) -> bool:
        if not os.path.exists(self._audit_path):
            return False

        file_size = os.path.getsize(self._audit_path)
        with open(self._audit_path, "wb") as f:
            f.write(b"\x00" * file_size)
            f.seek(0)
            f.write(b"\xFF" * file_size)
            f.seek(0)
            f.write(os.urandom(file_size))
        os.remove(self._audit_path)
        return True

    @staticmethod
    def _hash_text(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()


encryption_layer = EncryptionLayer()

