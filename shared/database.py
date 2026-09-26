"""
Database management for user preferences, guild configurations, and pronunciation dictionaries.
Uses aiosqlite for non-blocking asynchronous operations in discord.py.
"""

import aiosqlite
from typing import Optional, Dict, Any, List
from shared.config import settings


CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY,
    voice_id TEXT NOT NULL DEFAULT 'female_default',
    speed REAL NOT NULL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id TEXT PRIMARY KEY,
    active_text_channel_id TEXT,
    active_voice_channel_id TEXT,
    is_active INTEGER NOT NULL DEFAULT 0,
    max_chars INTEGER NOT NULL DEFAULT 250,
    tts_mode TEXT NOT NULL DEFAULT 'local',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS custom_pronunciation (
    guild_id TEXT NOT NULL,
    word TEXT NOT NULL,
    replacement TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (guild_id, word)
);
"""


class DatabaseManager:
    def __init__(self, db_path: str = None):
        self.db_path = str(db_path or settings.DATABASE_PATH)

    async def init_db(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(CREATE_TABLES_SQL)
            # Automatic schema migration for existing databases
            try:
                await db.execute("ALTER TABLE guild_settings ADD COLUMN tts_mode TEXT NOT NULL DEFAULT 'local'")
            except Exception:
                pass
            await db.commit()

    async def get_user_preference(self, user_id: str) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT voice_id, speed FROM user_preferences WHERE user_id = ?",
                (str(user_id),)
            )
            row = await cursor.fetchone()
            if row:
                return {"voice_id": row["voice_id"], "speed": row["speed"]}
            return {"voice_id": settings.DEFAULT_VOICE_ID, "speed": settings.DEFAULT_SPEED}

    async def set_user_preference(self, user_id: str, voice_id: str, speed: float = 1.0):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO user_preferences (user_id, voice_id, speed, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    voice_id = excluded.voice_id,
                    speed = excluded.speed,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(user_id), voice_id, speed)
            )
            await db.commit()

    async def get_guild_settings(self, guild_id: str) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT active_text_channel_id, active_voice_channel_id, is_active, max_chars, tts_mode FROM guild_settings WHERE guild_id = ?",
                (str(guild_id),)
            )
            row = await cursor.fetchone()
            if row:
                res = dict(row)
                if not res.get("tts_mode"):
                    res["tts_mode"] = settings.DEFAULT_TTS_MODE
                return res
            return {
                "active_text_channel_id": None,
                "active_voice_channel_id": None,
                "is_active": 0,
                "max_chars": settings.MAX_TEXT_LENGTH,
                "tts_mode": settings.DEFAULT_TTS_MODE
            }

    async def get_guild_mode(self, guild_id: str) -> str:
        settings_dict = await self.get_guild_settings(guild_id)
        return settings_dict.get("tts_mode", settings.DEFAULT_TTS_MODE)

    async def set_guild_mode(self, guild_id: str, mode: str):
        valid_mode = "wavespeed" if mode.lower() in ["wavespeed", "cloud"] else "local"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO guild_settings (guild_id, tts_mode, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(guild_id) DO UPDATE SET
                    tts_mode = excluded.tts_mode,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(guild_id), valid_mode)
            )
            await db.commit()

    async def set_guild_channel(self, guild_id: str, text_channel_id: Optional[str], voice_channel_id: Optional[str] = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO guild_settings (guild_id, active_text_channel_id, active_voice_channel_id, is_active, updated_at)
                VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
                ON CONFLICT(guild_id) DO UPDATE SET
                    active_text_channel_id = COALESCE(excluded.active_text_channel_id, guild_settings.active_text_channel_id),
                    active_voice_channel_id = COALESCE(excluded.active_voice_channel_id, guild_settings.active_voice_channel_id),
                    is_active = 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(guild_id), str(text_channel_id) if text_channel_id else None, str(voice_channel_id) if voice_channel_id else None)
            )
            await db.commit()

    async def deactivate_guild(self, guild_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE guild_settings SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ?",
                (str(guild_id),)
            )
            await db.commit()

    async def get_guild_pronunciations(self, guild_id: str) -> Dict[str, str]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT word, replacement FROM custom_pronunciation WHERE guild_id = ?",
                (str(guild_id),)
            )
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}

    async def set_pronunciation(self, guild_id: str, word: str, replacement: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO custom_pronunciation (guild_id, word, replacement)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, word) DO UPDATE SET replacement = excluded.replacement
                """,
                (str(guild_id), word, replacement)
            )
            await db.commit()


db_manager = DatabaseManager()
