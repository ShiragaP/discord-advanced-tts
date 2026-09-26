"""
Configuration management for Discord Advanced Thai TTS (DAT).
Uses Pydantic BaseSettings with environment variable support.
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Discord Bot Settings
    DISCORD_TOKEN: str = ""
    DISCORD_COMMAND_PREFIX: str = "!"
    
    # TTS Server & Connection Settings
    TTS_HOST: str = "0.0.0.0"
    TTS_PORT: int = 13300
    TTS_API_URL: str = "http://127.0.0.1:13300"
    TTS_API_KEY: Optional[str] = None
    
    # Model Configurations
    TTS_MODEL_TYPE: str = "F5"
    TTS_LANGUAGE: str = "th"
    TTS_CHECKPOINT: str = "hf://biodatlab/ThonburianTTS/megaF5/mega_f5_last.safetensors"
    TTS_VOCAB_FILE: str = "hf://biodatlab/ThonburianTTS/megaF5/mega_vocab.txt"
    TTS_VOCODER: str = "vocos"
    TTS_DEVICE: str = "cuda"
    TTS_ODE_METHOD: str = "euler"
    TTS_NFE_STEP: int = 32
    TTS_CFG_STRENGTH: float = 2.0
    
    # Voice & Audio Defaults
    DEFAULT_VOICE_ID: str = "female_default"
    DEFAULT_SPEED: float = 0.9
    MAX_TEXT_LENGTH: int = 250
    USER_RATE_LIMIT_SECONDS: float = 2.0
    
    # Storage Paths
    DATABASE_PATH: Path = BASE_DIR / "data" / "database" / "dat.db"
    CACHE_DIR: Path = BASE_DIR / "data" / "cache"
    VOICES_DIR: Path = BASE_DIR / "data" / "voices"
    CACHE_ENABLED: bool = True
    CACHE_MAX_SIZE_MB: int = 2048
    
    # Audio & FFmpeg
    FFMPEG_PATH: str = "ffmpeg"
    
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

# Ensure critical data directories exist
settings.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
settings.VOICES_DIR.mkdir(parents=True, exist_ok=True)
