import os
import secrets
from backend.core.config import settings

def secure_wipe_db(passes=3):
    # Implements a DoD 5220.22-M style secure wipe of the database file.
    file_path = settings.DB_PATH
    if not os.path.exists(file_path):
        return False
    
    try:
        length = os.path.getsize(file_path)
        with open(file_path, "ba+", buffering=0) as f:
            for i in range(passes):
                f.seek(0)
                f.write(secrets.token_bytes(length))
                f.flush()
                os.fsync(f.fileno())
        
        os.remove(file_path)
        return True
    except Exception as e:
        print(f"Error during secure wipe: {e}")
        return False
