"""
Local Audio Cache Service.
Saves and reuses synthesized WAV files keyed by normalized text, voice profile, and speed.
Provides LRU / size-bounded cleanup.
"""

import hashlib
import os
import time
from pathlib import Path
from typing import Optional
from shared.config import settings


class AudioCache:
    def __init__(self, cache_dir: Optional[Path] = None, max_size_mb: int = None):
        self.cache_dir = cache_dir or settings.CACHE_DIR
        self.max_size_mb = max_size_mb or settings.CACHE_MAX_SIZE_MB
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _generate_key(self, text: str, voice_id: str, speed: float, mode: str = "local") -> str:
        raw_key = f"{text.strip()}:{voice_id}:{speed:.2f}:{mode}:{settings.TTS_MODEL_TYPE}:v3"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(self, text: str, voice_id: str, speed: float, mode: str = "local") -> Optional[Path]:
        if not settings.CACHE_ENABLED:
            return None

        key = self._generate_key(text, voice_id, speed, mode=mode)
        for ext in ["wav", "mp3"]:
            cache_path = self.cache_dir / f"{key}.{ext}"
            if cache_path.exists():
                try:
                    cache_path.touch()
                except Exception:
                    pass
                return cache_path
        return None

    def put(self, text: str, voice_id: str, speed: float, audio_bytes: bytes, mode: str = "local", ext: str = "wav") -> Path:
        key = self._generate_key(text, voice_id, speed, mode=mode)
        cache_path = self.cache_dir / f"{key}.{ext}"

        # Check size before writing
        self._prune_if_needed(incoming_bytes=len(audio_bytes))

        with open(cache_path, "wb") as f:
            f.write(audio_bytes)
        return cache_path

    def _prune_if_needed(self, incoming_bytes: int):
        max_bytes = self.max_size_mb * 1024 * 1024
        files = list(self.cache_dir.glob("*.wav")) + list(self.cache_dir.glob("*.mp3"))
        total_size = sum(f.stat().st_size for f in files)

        if total_size + incoming_bytes > max_bytes:
            # Sort by access/modify time ascending (oldest first)
            files.sort(key=lambda f: f.stat().st_mtime)
            for f in files:
                try:
                    total_size -= f.stat().st_size
                    f.unlink()
                except Exception:
                    pass
                if total_size + incoming_bytes <= max_bytes * 0.8:
                    break


audio_cache = AudioCache()
