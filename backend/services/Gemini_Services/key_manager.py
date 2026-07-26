"""API-key rotation to prevent rate limits.

Collect as many Gemini keys as you can and drop them in .env:

    GEMINI_API_KEY_1=AIza...
    GEMINI_API_KEY_2=AIza...
    GEMINI_API_KEY_3=AIza...
    ...
    GEMINI_API_KEY=AIza...     # optional single/base key

The manager round-robins across every key and, on a 429 / quota error, rotates
to the next key automatically. More keys == more free-tier headroom.
"""

import os
from typing import Callable, List

from dotenv import load_dotenv

load_dotenv()


class GeminiKeyManager:
    def __init__(self) -> None:
        self.keys: List[str] = self._load_keys()
        self.current_index = 0

    def _load_keys(self) -> List[str]:
        keys: List[str] = []

        # Numbered keys: GEMINI_API_KEY_1, _2, _3, ...
        i = 1
        while True:
            key = os.getenv(f"GEMINI_API_KEY_{i}")
            if not key:
                break
            keys.append(key.strip())
            i += 1

        # Optional single/base key
        base_key = os.getenv("GEMINI_API_KEY")
        if base_key:
            keys.append(base_key.strip())

        # Dedupe while preserving order, drop empties
        unique = [k for k in dict.fromkeys(keys) if k]
        if unique:
            print(f"[KEY_MANAGER] Loaded {len(unique)} unique Gemini API key(s)")
        else:
            print("[KEY_MANAGER] WARNING: no GEMINI_API_KEY* found — AI features disabled")
        return unique

    @property
    def is_ready(self) -> bool:
        return len(self.keys) > 0

    def get_next_key(self) -> str:
        if not self.keys:
            raise RuntimeError("No Gemini API keys configured")
        key = self.keys[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.keys)
        return key

    def execute_with_retry(self, func: Callable, *args, **kwargs):
        """Run ``func(api_key, *args)`` rotating keys on rate-limit errors."""
        if not self.keys:
            raise RuntimeError(
                "No Gemini API keys configured. Set GEMINI_API_KEY (or GEMINI_API_KEY_1..) in .env"
            )

        last_error = None
        for _ in range(len(self.keys)):
            key = self.get_next_key()
            try:
                return func(key, *args, **kwargs)
            except Exception as e:  # noqa: BLE001 — inspect message to decide retry
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
                    print(f"[KEY_MANAGER] Rate limit on key ...{key[-4:]}, rotating")
                    last_error = e
                    continue
                raise
        raise RuntimeError(f"All Gemini API keys exhausted. Last error: {last_error}")


key_manager = GeminiKeyManager()
