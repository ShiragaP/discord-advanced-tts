"""
Voice selection slash commands: /voice, /voices
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging

from shared.database import db_manager
from apps.discord_bot.services.tts_client import tts_client

logger = logging.getLogger("voice_commands")


class VoiceCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="voices", description="ดูรายชื่อโปรไฟล์เสียงพูดทั้งหมดที่ได้รับอนุญาต")
    async def voices(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            voice_list = await tts_client.get_voices()
            if not voice_list:
                await interaction.followup.send("⚠️ ไม่พบโปรไฟล์เสียงในระบบ")
                return

            embed = discord.Embed(
                title="🎭 รายชื่อโปรไฟล์เสียงพูดภาษาไทย (Voice Profiles)",
                description="คุณสามารถเลือกใช้เสียงที่ต้องการด้วยคำสั่ง `/voice [voice_id]`",
                color=discord.Color.blue()
            )

            for v in voice_list:
                default_tag = " ⭐ (Default)" if v.get("is_default") else ""
                embed.add_field(
                    name=f"`{v['id']}` — {v['name']}{default_tag}",
                    value=f"**รายละเอียด:** {v.get('description', '-')}\n**ความเร็วเริ่มต้น:** {v.get('default_speed', 1.0)}x",
                    inline=False
                )

            guild_ws_voice = await db_manager.get_guild_wavespeed_voice(str(interaction.guild_id))
            embed.add_field(
                name="☁️ WaveSpeed AI (ElevenLabs)",
                value=f"• **Voice ID ปัจจุบัน:** `{guild_ws_voice}`\n• เปลี่ยนเสียงทั้งเซิร์ฟเวอร์ด้วย: `/wavespeed_voice [voice_id]`\n• หรือตั้งค่าเฉพาะตัวคุณด้วย: `/voice [voice_id]`",
                inline=False
            )

            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.exception("Failed to fetch voices")
            await interaction.followup.send(f"❌ ไม่สามารถดึงรายชื่อเสียงได้: {e}", ephemeral=True)

    @app_commands.command(name="voice", description="เลือกโปรไฟล์เสียงและความเร็วพูดส่วนตัวของคุณ")
    @app_commands.describe(
        voice_id="รหัสโปรไฟล์เสียง (ดูได้จาก /voices หรือระบุ ElevenLabs Voice ID เมื่อใช้ WaveSpeed)",
        speed="ความเร็วเสียงพูด (0.5 ถึง 2.0, ค่าเริ่มต้น 1.0)"
    )
    async def voice(self, interaction: discord.Interaction, voice_id: str, speed: float = 1.0):
        if speed < 0.5 or speed > 2.0:
            await interaction.response.send_message("❌ ความเร็วเสียงต้องอยู่ระหว่าง 0.5 ถึง 2.0", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        clean_voice_id = voice_id.strip()
        try:
            available_voices = await tts_client.get_voices()
            matched = any(v["id"].lower() == clean_voice_id.lower() for v in available_voices)
            is_custom_id = 3 <= len(clean_voice_id) <= 60 and all(c.isalnum() or c in "-_" for c in clean_voice_id)

            if not matched and not is_custom_id:
                voice_ids = ", ".join(f"`{v['id']}`" for v in available_voices)
                await interaction.followup.send(
                    f"❌ ไม่พบรหัสเสียง `{clean_voice_id}`\nเสียง Local ที่มี: {voice_ids}\nหรือใส่ ElevenLabs Voice ID เมื่อใช้ WaveSpeed",
                    ephemeral=True
                )
                return

            saved_voice_id = clean_voice_id if (is_custom_id and not matched) else clean_voice_id.lower()

            await db_manager.set_user_preference(
                user_id=str(interaction.user.id),
                voice_id=saved_voice_id,
                speed=speed
            )

            await interaction.followup.send(
                f"✅ บันทึกการตั้งค่าเสียงของคุณเรียบร้อยแล้ว!\n**เสียง:** `{saved_voice_id}` | **ความเร็ว:** `{speed}x`",
                ephemeral=True
            )
        except Exception as e:
            logger.exception("Failed to update user voice preference")
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาดในการบันทึก: {e}", ephemeral=True)
