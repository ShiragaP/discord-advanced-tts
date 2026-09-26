"""
Pydantic Schemas for TTS FastAPI Server.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500, description="Thai text to synthesize")
    voice_id: str = Field(default="female_default", description="Voice profile ID")
    speed: float = Field(default=1.0, ge=0.5, le=2.0, description="Speech playback speed multiplier")
    stream: bool = Field(default=False, description="Whether to return binary stream or base64 JSON")


class SynthesizeResponse(BaseModel):
    status: str
    audio_base64: str
    duration_seconds: float
    generation_seconds: float
    voice_id: str
    speed: float


class VoiceProfile(BaseModel):
    id: str
    name: str
    gender: str
    description: str
    ref_audio_path: str
    ref_text: str
    default_speed: float = 1.0
    is_default: bool = False
    is_approved: bool = True


class VoicesListResponse(BaseModel):
    voices: List[VoiceProfile]


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    device: str
    vram_allocated_mb: float
    vram_free_gb: float
