"""
Voice Profile Manager for TTS Server.
Ensures administrator-approved voice profiles, loads reference audio and metadata.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from apps.tts_server.schemas import VoiceProfile
from shared.config import settings


class VoiceManager:
    def __init__(self, profiles_file: Optional[Path] = None):
        self.profiles_file = profiles_file or (settings.VOICES_DIR / "profiles.json")
        self.voices: Dict[str, VoiceProfile] = {}
        self.load_profiles()

    def load_profiles(self):
        self.voices.clear()
        if not self.profiles_file.exists():
            # Create default profile pointing to existing default audio
            default_profile = VoiceProfile(
                id="female_default",
                name="ฟ้าใส (Fahsai - Female)",
                gender="female",
                description="เสียงผู้หญิงไทย นุ่มนวล เป็นธรรมชาติ (Default)",
                ref_audio_path="data/voices/samples/default_female.wav",
                ref_text="ใครเป็นผู้รับ",
                default_speed=1.0,
                is_default=True,
                is_approved=True
            )
            self.voices[default_profile.id] = default_profile
            self.save_profiles()
            return

        with open(self.profiles_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                profile = VoiceProfile(**item)
                self.voices[profile.id] = profile

    def save_profiles(self):
        with open(self.profiles_file, "w", encoding="utf-8") as f:
            json.dump([v.model_dump() for v in self.voices.values()], f, ensure_ascii=False, indent=2)

    def get_voice(self, voice_id: str) -> Optional[VoiceProfile]:
        return self.voices.get(voice_id, self.voices.get(settings.DEFAULT_VOICE_ID))

    def list_voices(self) -> List[VoiceProfile]:
        return list(self.voices.values())

    def add_voice(self, profile: VoiceProfile):
        self.voices[profile.id] = profile
        self.save_profiles()


voice_manager = VoiceManager()
