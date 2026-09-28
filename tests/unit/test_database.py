"""
Unit tests for DatabaseManager.
"""

import tempfile
from pathlib import Path
import pytest
import pytest_asyncio
from shared.database import DatabaseManager


@pytest_asyncio.fixture
async def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        manager = DatabaseManager(db_path=str(db_path))
        await manager.init_db()
        yield manager


@pytest.mark.asyncio
async def test_user_preferences(temp_db):
    user_id = "123456789"
    # Default lookup
    pref = await temp_db.get_user_preference(user_id)
    assert pref["voice_id"] == "female_default"
    assert pref["speed"] == 1.0

    # Set new preference
    await temp_db.set_user_preference(user_id, voice_id="female_fast", speed=1.2)
    updated = await temp_db.get_user_preference(user_id)
    assert updated["voice_id"] == "female_fast"
    assert updated["speed"] == 1.2


@pytest.mark.asyncio
async def test_guild_settings_and_pronunciations(temp_db):
    guild_id = "987654321"

    # Set active channels
    await temp_db.set_guild_channel(guild_id, text_channel_id="111", voice_channel_id="222")
    settings = await temp_db.get_guild_settings(guild_id)
    assert settings["active_text_channel_id"] == "111"
    assert settings["active_voice_channel_id"] == "222"
    assert settings["is_active"] == 1

    # Pronunciation replacement
    await temp_db.set_pronunciation(guild_id, "GG", "จีจี")
    pronunciations = await temp_db.get_guild_pronunciations(guild_id)
    assert pronunciations.get("GG") == "จีจี"

    # Guild mode settings
    assert await temp_db.get_guild_mode(guild_id) == "local"
    await temp_db.set_guild_mode(guild_id, "wavespeed")
    assert await temp_db.get_guild_mode(guild_id) == "wavespeed"
    await temp_db.set_guild_mode(guild_id, "local")
    assert await temp_db.get_guild_mode(guild_id) == "local"

    # Guild wavespeed voice
    default_ws = await temp_db.get_guild_wavespeed_voice(guild_id)
    assert default_ws == "zGjIP4SZlMnY9m93k97r"
    await temp_db.set_guild_wavespeed_voice(guild_id, "custom_voice_abc")
    assert await temp_db.get_guild_wavespeed_voice(guild_id) == "custom_voice_abc"

    # Guild wavespeed model
    from shared.config import settings
    default_model = await temp_db.get_guild_wavespeed_model(guild_id)
    assert default_model == settings.WAVESPEED_MODEL
    target_custom = "elevenlabs/multilingual-v2" if settings.WAVESPEED_MODEL == "elevenlabs/eleven-v3" else "elevenlabs/eleven-v3"
    await temp_db.set_guild_wavespeed_model(guild_id, target_custom)
    assert await temp_db.get_guild_wavespeed_model(guild_id) == target_custom


@pytest.mark.asyncio
async def test_guild_whitelist(temp_db):
    guild_id = "555666777"

    # Initial get falls back to defaults
    initial_wl = await temp_db.get_guild_whitelist(guild_id)
    assert "peony" in initial_wl
    assert "shiraga" in initial_wl
    assert "misu" in initial_wl
    assert "touru" in initial_wl

    # Allowed check on default whitelist
    assert await temp_db.is_user_allowed_wavespeed(guild_id, "PeonyGamer", "Alice") is True
    assert await temp_db.is_user_allowed_wavespeed(guild_id, "john_doe", "Shiraga Fan") is True
    assert await temp_db.is_user_allowed_wavespeed(guild_id, "random_user", "Nobody") is False

    # Add new keyword
    updated = await temp_db.add_guild_whitelist(guild_id, "Somchai")
    assert "somchai" in updated
    assert "peony" in updated
    assert await temp_db.is_user_allowed_wavespeed(guild_id, "somchai123", "User") is True
    assert await temp_db.is_user_allowed_wavespeed(guild_id, "user", "Mr. SOMCHAI") is True

    # Remove a keyword
    deleted, after_del = await temp_db.remove_guild_whitelist(guild_id, "misu")
    assert deleted is True
    assert "misu" not in after_del
    assert await temp_db.is_user_allowed_wavespeed(guild_id, "misu39", "Misu") is False

    # Remove non-existent keyword
    deleted, _ = await temp_db.remove_guild_whitelist(guild_id, "nonexistent")
    assert deleted is False
