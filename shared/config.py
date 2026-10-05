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
    ENABLE_LOCAL_TTS: bool = False
    DEFAULT_VOICE_ID: str = "female_default"
    DEFAULT_SPEED: float = 0.9
    DEFAULT_TTS_MODE: str = "wavespeed"  # "wavespeed" or "local"
    MAX_TEXT_LENGTH: int = 250
    USER_RATE_LIMIT_SECONDS: float = 2.0
    WAVESPEED_ALLOW_ALL_WHEN_LOCAL_DISABLED: bool = True
    
    # Cloud TTS Providers (WaveSpeed / ElevenLabs)
    WAVESPEED_API_KEYS: str = ""
    WAVESPEED_MODEL: str = "elevenlabs/eleven-v4"
    WAVESPEED_VOICE_ID: str = "zGjIP4SZlMnY9m93k97r"
    WAVESPEED_DEFAULT_SPEED: float = 0.8
    WAVESPEED_WHITELIST: str = "peony,shiraga,misu,touru"
    ELEVENLABS_API_KEYS: str = ""
    ELEVENLABS_VOICE_ID: str = "zGjIP4SZlMnY9m93k97r"
    ELEVENLABS_MODEL_ID: str = "eleven_multilingual_v2"
    
    # Storage Paths
    DATABASE_PATH: Path = BASE_DIR / "data" / "database" / "dat.db"
    CACHE_DIR: Path = BASE_DIR / "data" / "cache"
    VOICES_DIR: Path = BASE_DIR / "data" / "voices"
    CACHE_ENABLED: bool = True
    CACHE_MAX_SIZE_MB: int = 2048
    
    # Audio & FFmpeg
    FFMPEG_PATH: str = "ffmpeg"

    @property
    def wavespeed_keys_list(self) -> list[str]:
        if not self.WAVESPEED_API_KEYS:
            return []
        return [k.strip() for k in self.WAVESPEED_API_KEYS.split(",") if k.strip()]

    @property
    def elevenlabs_keys_list(self) -> list[str]:
        if not self.ELEVENLABS_API_KEYS:
            return []
        return [k.strip() for k in self.ELEVENLABS_API_KEYS.split(",") if k.strip()]

    @property
    def wavespeed_whitelist_list(self) -> list[str]:
        if not self.WAVESPEED_WHITELIST:
            return ["peony", "shiraga", "misu", "touru"]
        return [k.strip().lower() for k in self.WAVESPEED_WHITELIST.split(",") if k.strip()]

    def is_user_allowed_wavespeed(self, username: str, display_name: str) -> bool:
        user_str = f"{username} {display_name}".lower()
        return any(keyword in user_str for keyword in self.wavespeed_whitelist_list)
    
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
