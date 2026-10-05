"""
Cloud TTS Service integration for WaveSpeed AI and ElevenLabs.
Supports multiple API keys with random selection and automatic failover.
"""

import aiohttp
import asyncio
import logging
import os
import random
import re
import shutil
from typing import Tuple, Optional, List
from shared.config import settings

logger = logging.getLogger("cloud_tts")


class CloudTTSClient:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=30,
                keepalive_timeout=60.0,
                ttl_dns_cache=300,
                enable_cleanup_closed=True
            )
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=45.0)
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        speed: float = 1.0,
        model: Optional[str] = None
    ) -> Tuple[bytes, str]:
        """
        Synthesizes text using configured Cloud providers.
        Tries WaveSpeed (ElevenLabs proxy) first if keys are configured,
        or direct ElevenLabs. Randomly chooses a key each time with failover.
        Returns: (audio_bytes, format_ext) e.g. (b'...', 'mp3')
        """
        wavespeed_keys = settings.wavespeed_keys_list
        elevenlabs_keys = settings.elevenlabs_keys_list

        if not wavespeed_keys and not elevenlabs_keys:
            raise RuntimeError(
                "No Cloud TTS API keys configured! Please set WAVESPEED_API_KEYS or ELEVENLABS_API_KEYS in .env"
            )

        # 1. Try WaveSpeed AI if keys available
        if wavespeed_keys:
            # Shuffle keys to randomly choose one each time and failover if quota/auth fails
            shuffled_keys = list(wavespeed_keys)
            random.shuffle(shuffled_keys)
            
            last_err = None
            for key in shuffled_keys:
                try:
                    target_model = model or settings.WAVESPEED_MODEL
                    logger.info("Attempting Cloud TTS via WaveSpeed (model=%s, key ...%s, speed=%.2f)", target_model, key[-6:], speed)
                    audio_bytes = await self._synthesize_wavespeed(text, key, voice_id=voice_id, model=model)
                    audio_bytes = await self._adjust_speed(audio_bytes, speed)
                    return audio_bytes, "mp3"
                except Exception as e:
                    logger.warning("WaveSpeed key ...%s failed: %s. Trying next key...", key[-6:], e)
                    last_err = e

            if last_err and not elevenlabs_keys:
                raise last_err

        # 2. Try direct ElevenLabs if configured
        if elevenlabs_keys:
            shuffled_keys = list(elevenlabs_keys)
            random.shuffle(shuffled_keys)

            last_err = None
            for key in shuffled_keys:
                try:
                    logger.info("Attempting Cloud TTS via direct ElevenLabs (key ...%s, speed=%.2f)", key[-6:], speed)
                    audio_bytes = await self._synthesize_elevenlabs(text, key, voice_id=voice_id)
                    audio_bytes = await self._adjust_speed(audio_bytes, speed)
                    return audio_bytes, "mp3"
                except Exception as e:
                    logger.warning("ElevenLabs key ...%s failed: %s. Trying next key...", key[-6:], e)
                    last_err = e

            if last_err:
                raise last_err

        raise RuntimeError("All cloud TTS keys failed.")

    async def _adjust_speed(self, audio_bytes: bytes, speed: float) -> bytes:
        if abs(speed - 1.0) < 0.02:
            return audio_bytes

        ffmpeg_cmd = settings.FFMPEG_PATH
        if not shutil.which(ffmpeg_cmd):
            winget_ffmpeg = r"C:\Users\shiraga\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe"
            if os.path.exists(winget_ffmpeg):
                ffmpeg_cmd = winget_ffmpeg

        try:
            proc = await asyncio.create_subprocess_exec(
                ffmpeg_cmd, "-y", "-i", "pipe:0",
                "-filter:a", f"atempo={speed}",
                "-f", "mp3", "pipe:1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate(input=audio_bytes)
            if proc.returncode == 0 and len(stdout) > 0:
                logger.info("Adjusted audio speed to %.2fx using FFmpeg (%d bytes -> %d bytes)", speed, len(audio_bytes), len(stdout))
                return stdout
            logger.warning("FFmpeg speed adjustment error: %s", stderr.decode(errors="replace"))
        except Exception as e:
            logger.warning("Failed to adjust speed with FFmpeg: %s", e)

        return audio_bytes

    async def _synthesize_wavespeed(self, text: str, api_key: str, voice_id: Optional[str] = None, model: Optional[str] = None) -> bytes:
        session = await self.get_session()
        local_presets = {"female_default", "female_fast", "male_default", "vachana_female", "vachana_male", "pythaitts_default"}
        if not voice_id or voice_id in local_presets:
            target_voice = settings.WAVESPEED_VOICE_ID
        else:
            target_voice = voice_id

        target_model = model or settings.WAVESPEED_MODEL
        url = f"https://api.wavespeed.ai/api/v3/{target_model}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        # Add natural trail-off padding if sentence has no terminal punctuation
        prompt_text = text.strip()
        if prompt_text and not prompt_text.endswith((".", "!", "?", "…", "...", "~")):
            prompt_text = f"{prompt_text} ..."

        # Check if text contains Thai characters to enforce Thai pronunciation
        has_thai = bool(re.search(r"[\u0e00-\u0e7f]", text))

        payload = {
            "text": prompt_text,
            "voice_id": target_voice,
            "similarity": 0.75,
            "stability": 0.5,
            "use_speaker_boost": True,
            "enable_sync_mode": True
        }
        if has_thai:
            payload["language_code"] = "th"

        # 1. Submit prediction with synchronous mode
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"WaveSpeed submission error {resp.status}: {body}")
            result_json = await resp.json()

        data = result_json.get("data", {})
        
        # Check if generation already completed synchronously (saves 1.5 - 2.5s of polling!)
        if data.get("status") == "completed" and data.get("outputs"):
            audio_url = data["outputs"][0]
        else:
            get_url = data.get("urls", {}).get("get")
            if not get_url:
                raise RuntimeError(f"WaveSpeed response missing polling url: {result_json}")

            # 2. Fast poll for completion if sync didn't finish immediately (every 200ms)
            for _ in range(35):
                await asyncio.sleep(0.2)
                async with session.get(get_url, headers=headers) as poll_resp:
                    if poll_resp.status != 200:
                        continue
                    poll_json = await poll_resp.json()
                    poll_data = poll_json.get("data", {})
                    status = poll_data.get("status")

                    if status == "completed":
                        outputs = poll_data.get("outputs", [])
                        if not outputs:
                            raise RuntimeError("WaveSpeed completed but returned empty outputs")
                        audio_url = outputs[0]
                        break
                    elif status in ["failed", "error"]:
                        err_msg = poll_data.get("error", "Unknown error")
                        raise RuntimeError(f"WaveSpeed prediction failed: {err_msg}")
            else:
                raise TimeoutError("WaveSpeed prediction timed out after 10 seconds")

        # 3. Download audio file
        async with session.get(audio_url) as audio_resp:
            if audio_resp.status != 200:
                raise RuntimeError(f"Failed to download audio from {audio_url}: {audio_resp.status}")
            return await audio_resp.read()

    async def _synthesize_elevenlabs(self, text: str, api_key: str, voice_id: Optional[str] = None) -> bytes:
        session = await self.get_session()
        target_voice = voice_id or settings.ELEVENLABS_VOICE_ID

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{target_voice}"
        headers = {
            "xi-api-key": api_key,
            "Content-Type": "application/json"
        }

        # Add natural trail-off padding if sentence has no terminal punctuation
        prompt_text = text.strip()
        if prompt_text and not prompt_text.endswith((".", "!", "?", "…", "...", "~")):
            prompt_text = f"{prompt_text} ..."

        payload = {
            "text": prompt_text,
            "model_id": settings.ELEVENLABS_MODEL_ID,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }

        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"ElevenLabs error {resp.status}: {body}")
            return await resp.read()


cloud_tts_client = CloudTTSClient()
