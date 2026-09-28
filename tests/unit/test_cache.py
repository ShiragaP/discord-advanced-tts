"""
Unit tests for AudioCache.
"""

import tempfile
from pathlib import Path
import pytest
from apps.discord_bot.services.audio_cache import AudioCache


@pytest.fixture
def temp_cache():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield AudioCache(cache_dir=Path(tmpdir), max_size_mb=1)


def test_cache_miss_and_put(temp_cache):
    text = "ข้อความทดสอบ"
    voice_id = "female_default"
    speed = 1.0

    # 1. Initial miss
    assert temp_cache.get(text, voice_id, speed) is None

    # 2. Put audio bytes
    audio_data = b"RIFFFAKEWAVDATA"
    cached_path = temp_cache.put(text, voice_id, speed, audio_data)
    assert cached_path.exists()

    # 3. Cache hit
    retrieved = temp_cache.get(text, voice_id, speed)
    assert retrieved is not None
    assert retrieved == cached_path
    assert retrieved.read_bytes() == audio_data


def test_cache_key_different_parameters(temp_cache):
    text = "ข้อความทดสอบ"
    audio_1 = b"DATA1"
    audio_2 = b"DATA2"

    temp_cache.put(text, "voice_a", 1.0, audio_1)
    temp_cache.put(text, "voice_b", 1.0, audio_2)

    hit_a = temp_cache.get(text, "voice_a", 1.0)
    hit_b = temp_cache.get(text, "voice_b", 1.0)

    assert hit_a != hit_b
    assert hit_a.read_bytes() == audio_1
    assert hit_b.read_bytes() == audio_2


def test_cache_key_different_models(temp_cache):
    text = "ข้อความทดสอบโมเดล"
    voice = "voice_test"
    speed = 0.8
    audio_turbo = b"TURBO_AUDIO"
    audio_v3 = b"V3_AUDIO"

    path_turbo = temp_cache.put(text, voice, speed, audio_turbo, mode="wavespeed", model="elevenlabs/turbo-v2.5")
    path_v3 = temp_cache.put(text, voice, speed, audio_v3, mode="wavespeed", model="elevenlabs/eleven-v3")

    assert path_turbo != path_v3
    assert temp_cache.get(text, voice, speed, mode="wavespeed", model="elevenlabs/turbo-v2.5").read_bytes() == audio_turbo
    assert temp_cache.get(text, voice, speed, mode="wavespeed", model="elevenlabs/eleven-v3").read_bytes() == audio_v3
