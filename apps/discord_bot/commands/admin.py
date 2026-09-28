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

    # Whitelist command group for WaveSpeed access management
    whitelist_group = app_commands.Group(
        name="whitelist",
        description="[Admin] จัดการรายชื่อคำที่ได้รับอนุญาตให้ใช้เสียง WaveSpeed",
        default_permissions=discord.Permissions(manage_guild=True)
    )

    @whitelist_group.command(name="add", description="เพิ่มคำค้นหาในชื่อที่อนุญาตให้ใช้ WaveSpeed")
    @app_commands.describe(keyword="คำหรือชื่อที่ต้องการให้อนุญาต เช่น misu")
    async def whitelist_add(self, interaction: discord.Interaction, keyword: str):
        clean_kw = keyword.strip()
        if not clean_kw:
            await interaction.response.send_message("❌ กรุณาระบุคำที่ต้องการเพิ่ม", ephemeral=True)
            return
        updated_list = await db_manager.add_guild_whitelist(str(interaction.guild_id), clean_kw)
        list_str = ", ".join(f"`{k}`" for k in updated_list)
        await interaction.response.send_message(
            f"✅ เพิ่ม `{clean_kw.lower()}` เข้า WaveSpeed Whitelist สำเร็จ!\n"
            f"📋 รายชื่อ Whitelist ปัจจุบัน: {list_str}",
            ephemeral=True
        )

    @whitelist_group.command(name="remove", description="ลบคำค้นหาในชื่อออกจาก WaveSpeed Whitelist")
    @app_commands.describe(keyword="คำหรือชื่อที่ต้องการลบ เช่น misu")
    async def whitelist_remove(self, interaction: discord.Interaction, keyword: str):
        clean_kw = keyword.strip()
        if not clean_kw:
            await interaction.response.send_message("❌ กรุณาระบุคำที่ต้องการลบ", ephemeral=True)
            return
        deleted, updated_list = await db_manager.remove_guild_whitelist(str(interaction.guild_id), clean_kw)
        list_str = ", ".join(f"`{k}`" for k in updated_list) if updated_list else "*(ว่างเปล่า)*"
        if deleted:
            await interaction.response.send_message(
                f"🗑️ ลบ `{clean_kw.lower()}` ออกจาก Whitelist สำเร็จ!\n"
                f"📋 รายชื่อ Whitelist ปัจจุบัน: {list_str}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"⚠️ ไม่พบ `{clean_kw.lower()}` ใน Whitelist ของเซิร์ฟเวอร์\n"
                f"📋 รายชื่อ Whitelist ปัจจุบัน: {list_str}",
                ephemeral=True
            )

    @whitelist_group.command(name="list", description="ดูรายชื่อคำทั้งหมดที่ได้รับสิทธิ์ใช้ WaveSpeed ในเซิร์ฟเวอร์")
    async def whitelist_list(self, interaction: discord.Interaction):
        current_list = await db_manager.get_guild_whitelist(str(interaction.guild_id))
        list_str = ", ".join(f"`{k}`" for k in current_list) if current_list else "*(ว่างเปล่า)*"
        embed = discord.Embed(
            title="📋 WaveSpeed Whitelist (ผู้มีสิทธิ์ใช้เสียง WaveSpeed)",
            description=(
                f"สมาชิกที่มีคำเหล่านี้ใน Username หรือ Display name จะได้รับสิทธิ์สังเคราะห์เสียงด้วย WaveSpeed AI:\n\n"
                f"{list_str}\n\n"
                f"💡 เพิ่มคำ: `/whitelist add <keyword>` | ลบคำ: `/whitelist remove <keyword>`"
            ),
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

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
