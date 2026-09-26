"""
Unit tests for Cloud TTS and permission checks.
"""

import pytest
from unittest.mock import patch, MagicMock
from shared.config import Settings
from apps.discord_bot.services.cloud_tts_client import CloudTTSClient


def test_user_permission_check():
    s = Settings(WAVESPEED_WHITELIST="peony,shiraga,misu")

    # Allowed cases
    assert s.is_user_allowed_wavespeed("peony", "Peony") is True
    assert s.is_user_allowed_wavespeed("User123", "Peony_V") is True
    assert s.is_user_allowed_wavespeed("Shiraga", "Administrator") is True
    assert s.is_user_allowed_wavespeed("normal_user", "SHIRAGA") is True
    assert s.is_user_allowed_wavespeed("pEoNy", "Random") is True
    assert s.is_user_allowed_wavespeed("misu", "Misu") is True
    assert s.is_user_allowed_wavespeed("cat_lover", "MiSu_San") is True
    assert s.is_user_allowed_wavespeed("MISU", "Cute") is True

    # Blocked cases
    assert s.is_user_allowed_wavespeed("alice", "Alice") is False
    assert s.is_user_allowed_wavespeed("bob", "Bob") is False
    assert s.is_user_allowed_wavespeed("guest_user", "Guest 01") is False


def test_wavespeed_keys_property():
    s = Settings(WAVESPEED_API_KEYS="key1, key2,key3 ")
    assert s.wavespeed_keys_list == ["key1", "key2", "key3"]

    s_empty = Settings(WAVESPEED_API_KEYS="")
    assert s_empty.wavespeed_keys_list == []


def test_wavespeed_default_speed_setting():
    s = Settings(WAVESPEED_DEFAULT_SPEED=0.8)
    assert s.WAVESPEED_DEFAULT_SPEED == 0.8


@pytest.mark.asyncio
async def test_cloud_tts_adjust_speed_noop_for_1_0():
    client = CloudTTSClient()
    dummy_audio = b"dummy_mp3_data"
    result = await client._adjust_speed(dummy_audio, 1.0)
    assert result == dummy_audio
