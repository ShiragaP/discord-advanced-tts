"""
Administrator Slash Commands: /pronounce, /clear_cache
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging

from shared.database import db_manager
from apps.discord_bot.services.audio_cache import audio_cache

logger = logging.getLogger("admin_commands")


class AdminCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="pronounce", description="[Admin] ตั้งค่าคำอ่านเฉพาะสำหรับเซิร์ฟเวอร์นี้")
    @app_commands.describe(word="คำต้นฉบับ เช่น GG", replacement="คำอ่านที่ต้องการ เช่น จีจี")
    @app_commands.default_permissions(manage_guild=True)
    async def pronounce(self, interaction: discord.Interaction, word: str, replacement: str):
        await db_manager.set_pronunciation(
            guild_id=str(interaction.guild_id),
            word=word.strip(),
            replacement=replacement.strip()
        )
        await interaction.response.send_message(
            f"✅ เพิ่มคำอ่านเฉพาะสำหรับเซิร์ฟเวอร์แล้ว:\n**{word.strip()}** ➔ **{replacement.strip()}**",
            ephemeral=True
        )

    @app_commands.command(name="clear_cache", description="[Admin] ล้างแคชไฟล์เสียงสังเคราะห์ทั้งหมดในระบบ")
    @app_commands.default_permissions(administrator=True)
    async def clear_cache(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = 0
        for f in audio_cache.cache_dir.glob("*.wav"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
        await interaction.followup.send(f"🧹 ล้างแคชเสียงเรียบร้อยแล้ว (ลบไป {count} ไฟล์)", ephemeral=True)
