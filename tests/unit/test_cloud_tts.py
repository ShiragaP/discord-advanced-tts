"""
Unit tests for Cloud TTS and permission checks.
"""

import pytest
from unittest.mock import patch, MagicMock
from shared.config import Settings
from apps.discord_bot.services.cloud_tts_client import CloudTTSClient


def check_user_allowed(author_name: str, display_name: str) -> bool:
    user_str = f"{author_name} {display_name}".lower()
    return "peony" in user_str or "shiraga" in user_str


def test_user_permission_check():
    # Allowed cases
    assert check_user_allowed("peony", "Peony") is True
    assert check_user_allowed("User123", "Peony_V") is True
    assert check_user_allowed("Shiraga", "Administrator") is True
    assert check_user_allowed("normal_user", "SHIRAGA") is True
    assert check_user_allowed("pEoNy", "Random") is True

    # Blocked cases
    assert check_user_allowed("alice", "Alice") is False
    assert check_user_allowed("bob", "Bob") is False
    assert check_user_allowed("guest_user", "Guest 01") is False


def test_wavespeed_keys_property():
    s = Settings(WAVESPEED_API_KEYS="key1, key2,key3 ")
    assert s.wavespeed_keys_list == ["key1", "key2", "key3"]

    s_empty = Settings(WAVESPEED_API_KEYS="")
    assert s_empty.wavespeed_keys_list == []
