"""
Asynchronous Client for communicating with the local or tunneled TTS API service.
Handles audio retrieval, audio caching, and status checks.
"""

import aiohttp
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from shared.config import settings
from apps.discord_bot.services.audio_cache import audio_cache

logger = logging.getLogger("tts_client")


class TTSClient:
    def __init__(self, base_url: str = None, api_key: str = None):
        self.base_url = (base_url or settings.TTS_API_URL).rstrip("/")
        self.api_key = api_key or settings.TTS_API_KEY
        self._session: Optional[aiohttp.ClientSession] = None

    def _get_headers(self) -> Dict[str, str]:
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=60.0)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_health(self) -> Dict[str, Any]:
        if not settings.ENABLE_LOCAL_TTS:
            return {
                "status": "online",
                "device": "Cloud Only (WaveSpeed AI)",
                "vram_allocated_mb": 0.0,
                "vram_free_gb": 0.0,
                "model": settings.WAVESPEED_MODEL,
                "local_tts": "disabled"
            }
        session = await self.get_session()
        async with session.get(f"{self.base_url}/health") as resp:
            resp.raise_for_status()
            return await resp.json()

    async def is_ready(self) -> bool:
        if not settings.ENABLE_LOCAL_TTS:
            return True
        session = await self.get_session()
        try:
            async with session.get(f"{self.base_url}/ready", timeout=aiohttp.ClientTimeout(total=5.0)) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def get_voices(self) -> List[Dict[str, Any]]:
        if not settings.ENABLE_LOCAL_TTS:
            return [
                {
                    "id": settings.WAVESPEED_VOICE_ID,
                    "name": "WaveSpeed Cloud (ElevenLabs v3)",
                    "is_default": True,
                    "description": f"Model: {settings.WAVESPEED_MODEL}"
                }
            ]
        try:
            session = await self.get_session()
            async with session.get(f"{self.base_url}/voices") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get("voices", [])
        except Exception as e:
            logger.warning("Could not reach local TTS server for voice list: %s", e)
            return [
                {
                    "id": settings.WAVESPEED_VOICE_ID,
                    "name": "WaveSpeed Cloud (ElevenLabs v3)",
                    "is_default": True,
                    "description": f"Model: {settings.WAVESPEED_MODEL} (Local server offline)"
                }
            ]

    async def synthesize(
        self,
        text: str,
        voice_id: str = "female_default",
        speed: float = 1.0,
        mode: str = "local",
        model: Optional[str] = None
    ) -> Path:
        """
        Synthesizes speech or retrieves it from cache.
        Supports mode='local' (ThonburianTTS) and mode='cloud' (WaveSpeed / ElevenLabs).
        Returns the absolute Path to the local audio file.
        """
        # If local TTS is globally disabled, redirect all local synthesis to wavespeed
        if mode == "local" and not settings.ENABLE_LOCAL_TTS:
            logger.info("Local TTS is disabled (ENABLE_LOCAL_TTS=false); redirecting synthesis to wavespeed.")
            mode = "wavespeed"

        # Determine effective speed
        effective_speed = speed
        if mode in ["wavespeed", "cloud"]:
            if effective_speed is None or abs(effective_speed - 1.0) < 0.01:
                effective_speed = settings.WAVESPEED_DEFAULT_SPEED

        # 1. Check audio cache first
        cached_file = audio_cache.get(text, voice_id, effective_speed, mode=mode, model=model or "")
        if cached_file:
            logger.info("Audio cache hit for '%s' (mode=%s, model=%s, %s, x%.2f)", text[:20], mode, model or "default", voice_id, effective_speed)
            return cached_file

        # 2. Synthesize based on mode
        if mode in ["wavespeed", "cloud"]:
            try:
                from apps.discord_bot.services.cloud_tts_client import cloud_tts_client
                audio_bytes, ext = await cloud_tts_client.synthesize(text, voice_id=voice_id, speed=effective_speed, model=model)
                saved_path = audio_cache.put(text, voice_id, effective_speed, audio_bytes, mode=mode, ext=ext, model=model or "")
                return saved_path
            except Exception as e:
                if settings.ENABLE_LOCAL_TTS:
                    logger.error("Cloud TTS (%s) synthesis failed: %s. Falling back to local TTS...", mode, e)
                    return await self.synthesize(text, voice_id=voice_id, speed=speed, mode="local")
                logger.error("Cloud TTS (%s) synthesis failed: %s (Local TTS disabled, cannot fall back)", mode, e)
                raise

        # Local mode: call TTS server streaming endpoint
        session = await self.get_session()
        payload = {
            "text": text,
            "voice_id": voice_id,
            "speed": speed,
            "stream": True
        }

        async with session.post(f"{self.base_url}/synthesize", json=payload) as resp:
            if resp.status != 200:
                err_text = await resp.text()
                raise RuntimeError(f"TTS Server returned {resp.status}: {err_text}")

            audio_bytes = await resp.read()

        # 3. Store in audio cache
        saved_path = audio_cache.put(text, voice_id, speed, audio_bytes, mode=mode, ext="wav")
        return saved_path


tts_client = TTSClient()
