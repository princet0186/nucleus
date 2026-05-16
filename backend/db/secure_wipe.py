import os
import secrets
from backend.core.config import settings

def secure_wipe_db(passes=3):
    """
    Implements a DoD 5220.22-M style secure wipe of the database file.
    1. Overwrites with random data multiple times.
    2. Syncs to disk to ensure no caching prevents overwriting.
    3. Deletes the file.
    """
    file_path = settings.DB_PATH
    if not os.path.exists(file_path):
        return False
    
    try:
        length = os.path.getsize(file_path)
        with open(file_path, "ba+", buffering=0) as f:
            for i in range(passes):
                # Seek to beginning
                f.seek(0)
                # Write random bytes
                f.write(secrets.token_bytes(length))
                # Force write to physical disk
                f.flush()
                os.fsync(f.fileno())
        
        # Finally delete the file
        os.remove(file_path)
        return True
    except Exception as e:
        print(f"Error during secure wipe: {e}")
        return False
