"""
FastAPI Server for Local ThonburianTTS Speech Synthesis Service.
Listens on default port 13300 with /health, /ready, /voices, and /synthesize endpoints.
"""

import base64
import logging
import os
import sys
from contextlib import asynccontextmanager
import torch
from fastapi import FastAPI, HTTPException, Security, status, Response
from fastapi.responses import StreamingResponse
from fastapi.security import APIKeyHeader
import uvicorn

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure FFmpeg is on PATH
ffmpeg_path = r"C:\Users\shiraga\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-essentials_build\bin"
if os.path.exists(ffmpeg_path) and ffmpeg_path not in os.environ.get("PATH", ""):
    os.environ["PATH"] = ffmpeg_path + os.pathsep + os.environ.get("PATH", "")

from shared.config import settings
from shared.thai_normalizer import normalizer
from apps.tts_server.schemas import (
    SynthesizeRequest,
    SynthesizeResponse,
    VoicesListResponse,
    HealthResponse,
)
from apps.tts_server.voice_manager import voice_manager
from apps.tts_server.inference import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("tts_server")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)):
    if settings.TTS_API_KEY and api_key != settings.TTS_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key"
        )
    return api_key


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting TTS Server on port %d...", settings.TTS_PORT)
    try:
        engine.load_model()
    except Exception as e:
        logger.error("Failed to load model during startup: %s", e)
    yield
    logger.info("Shutting down TTS Server...")


app = FastAPI(
    title="Discord Advanced Thai TTS (DAT) Engine",
    description="Local GPU-accelerated Thai TTS service using ThonburianTTS",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    vram_alloc = 0.0
    vram_free = 0.0
    device_name = "cpu"

    if torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(0)
        vram_alloc = torch.cuda.memory_allocated() / (1024 ** 2)
        vram_free = torch.cuda.mem_get_info()[0] / (1024 ** 3)

    return HealthResponse(
        status="ok",
        model_loaded=engine.is_ready,
        device=device_name,
        vram_allocated_mb=vram_alloc,
        vram_free_gb=vram_free
    )


@app.get("/ready")
async def readiness_check():
    if not engine.is_ready:
        raise HTTPException(status_code=503, detail="TTS Model is not loaded or ready.")
    return {"ready": True, "model": settings.TTS_MODEL_TYPE}


@app.get("/voices", response_model=VoicesListResponse)
async def list_voices(api_key: str = Security(verify_api_key)):
    voices = voice_manager.list_voices()
    return VoicesListResponse(voices=voices)


@app.post("/synthesize")
async def synthesize_speech(
    request: SynthesizeRequest,
    api_key: str = Security(verify_api_key)
):
    if not engine.is_ready:
        raise HTTPException(status_code=503, detail="Model is still initializing.")

    # Normalize incoming text
    clean_text = normalizer.normalize(request.text)
    if not clean_text:
        raise HTTPException(status_code=400, detail="Text is empty after normalization.")

    try:
        wav_bytes, duration, gen_time = await engine.synthesize(
            text=clean_text,
            voice_id=request.voice_id,
            speed=request.speed
        )

        if request.stream:
            return Response(
                content=wav_bytes,
                media_type="audio/wav",
                headers={
                    "Content-Disposition": "inline; filename=speech.wav",
                    "X-Duration-Seconds": str(duration),
                    "X-Generation-Seconds": str(gen_time),
                }
            )

        audio_b64 = base64.b64encode(wav_bytes).decode("utf-8")
        return SynthesizeResponse(
            status="success",
            audio_base64=audio_b64,
            duration_seconds=duration,
            generation_seconds=gen_time,
            voice_id=request.voice_id,
            speed=request.speed
        )
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception("Synthesis error occurred")
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")


def run():
    uvicorn.run(
        "apps.tts_server.main:app",
        host=settings.TTS_HOST,
        port=settings.TTS_PORT,
        log_level="info",
        reload=False
    )


if __name__ == "__main__":
    run()
