"""
TTS Core Slash Commands: /join, /leave, /listen, /stop, /say, /status
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging

from shared.database import db_manager
from shared.config import settings
from shared.thai_normalizer import normalizer
from apps.discord_bot.voice.player import VoicePlayer
from apps.discord_bot.voice.audio_queue import queue_manager, AudioQueueItem
from apps.discord_bot.services.tts_client import tts_client

logger = logging.getLogger("tts_commands")


class TTSCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, player: VoicePlayer):
        self.bot = bot
        self.player = player

    @app_commands.command(name="join", description="ให้บอทเข้าห้องเสียงที่คุณกำลังอยู่")
    async def join(self, interaction: discord.Interaction):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ คุณต้องอยู่ในห้องเสียงก่อนจึงจะเรียกบอทได้", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        await interaction.response.defer()

        try:
            await self.player.connect_to_voice(voice_channel)
            await db_manager.set_guild_channel(
                guild_id=str(interaction.guild_id),
                text_channel_id=str(interaction.channel_id),
                voice_channel_id=str(voice_channel.id)
            )
            await interaction.followup.send(
                f"🔊 บอทเข้าห้องเสียง **{voice_channel.name}** แล้ว!\n"
                f"📖 กำลังอ่านข้อความจากห้อง {interaction.channel.mention} อัตโนมัติ (พิมพ์ข้อความคุยได้ทันที ไม่ต้องใช้คำสั่ง)"
            )
        except Exception as e:
            logger.exception("Failed to connect to voice")
            await interaction.followup.send(f"❌ ไม่สามารถเข้าห้องเสียงได้: {e}", ephemeral=True)

    @app_commands.command(name="leave", description="ให้บอทออกจากห้องเสียง")
    async def leave(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            await self.player.disconnect_from_voice(interaction.guild)
            await db_manager.deactivate_guild(str(interaction.guild_id))
            await interaction.followup.send("👋 ออกจากห้องเสียงเรียบร้อยแล้ว")
        except Exception as e:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

    @app_commands.command(name="listen", description="กำหนดห้องข้อความที่ต้องการให้อ่านออกเสียงอัตโนมัติ")
    @app_commands.describe(channel="ห้องข้อความที่ต้องการให้อ่าน (ค่าเริ่มต้นคือห้องปัจจุบัน)")
    async def listen(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target_channel = channel or interaction.channel
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ คุณต้องอยู่ในห้องเสียงก่อนจึงจะเปิดระบบอ่านได้", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        await interaction.response.defer()

        try:
            await self.player.connect_to_voice(voice_channel)
            await db_manager.set_guild_channel(
                guild_id=str(interaction.guild_id),
                text_channel_id=str(target_channel.id),
                voice_channel_id=str(voice_channel.id)
            )
            await interaction.followup.send(
                f"✅ ตั้งค่าให้อ่านข้อความจากห้อง {target_channel.mention} ในห้องเสียง **{voice_channel.name}** เรียบร้อยแล้ว!"
            )
        except Exception as e:
            await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

    @app_commands.command(name="stop", description="หยุดเสียงที่กำลังเล่นและล้างคิวทั้งหมด")
    async def stop(self, interaction: discord.Interaction):
        self.player.stop_playback(interaction.guild)
        await interaction.response.send_message("⏹️ หยุดเล่นเสียงและล้างคิวเรียบร้อยแล้ว")

    @app_commands.command(name="say", description="พิมพ์ข้อความให้อ่านออกเสียงทันที")
    @app_commands.describe(text="ข้อความภาษาไทยที่ต้องการให้อ่าน")
    async def say(self, interaction: discord.Interaction, text: str):
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_connected():
            if interaction.user.voice and interaction.user.voice.channel:
                await self.player.connect_to_voice(interaction.user.voice.channel)
            else:
                await interaction.response.send_message("❌ บอทไม่ได้อยู่ในห้องเสียง และคุณไม่ได้อยู่ในห้องเสียง", ephemeral=True)
                return

        await interaction.response.defer()

        # Get user preference
        user_pref = await db_manager.get_user_preference(str(interaction.user.id))
        voice_id = user_pref["voice_id"]
        speed = user_pref["speed"]

        clean_text = normalizer.normalize(text)
        if not clean_text:
            await interaction.followup.send("❌ ข้อความว่างเปล่าหรือมีแต่อักขระที่ไม่รองรับ", ephemeral=True)
            return

        try:
            audio_path = await tts_client.synthesize(clean_text, voice_id=voice_id, speed=speed)
            queue = queue_manager.get_queue(interaction.guild_id)
            await queue.put(AudioQueueItem(
                audio_path=audio_path,
                text=clean_text,
                author_name=interaction.user.display_name,
                channel_id=interaction.channel_id
            ))
            await interaction.followup.send(f"🗣️ **{interaction.user.display_name}**: {clean_text}")
        except Exception as e:
            logger.exception("Synthesis error during /say")
            await interaction.followup.send(f"❌ ไม่สามารถสร้างเสียงได้: {e}", ephemeral=True)

    @app_commands.command(name="status", description="ตรวจสอบสถานะการทำงานของบอทและ TTS GPU Engine")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild_settings = await db_manager.get_guild_settings(str(interaction.guild_id))
        queue = queue_manager.get_queue(interaction.guild_id)

        try:
            health = await tts_client.get_health()
            gpu_status = f"🟢 Online ({health['device']})"
            vram_info = f"Allocated: {health['vram_allocated_mb']:.1f} MB | Free: {health['vram_free_gb']:.2f} GB"
        except Exception:
            gpu_status = "🔴 Offline / Unreachable"
            vram_info = "N/A"

        embed = discord.Embed(
            title="⚡ Discord Advanced Thai TTS — System Status",
            color=discord.Color.green() if "Online" in gpu_status else discord.Color.red()
        )
        embed.add_field(name="TTS Engine", value=gpu_status, inline=True)
        embed.add_field(name="VRAM Status", value=vram_info, inline=False)
        embed.add_field(
            name="Guild Voice Channel",
            value=f"<#{guild_settings.get('active_voice_channel_id')}>" if guild_settings.get('active_voice_channel_id') else "None",
            inline=True
        )
        embed.add_field(
            name="Active Text Channel",
            value=f"<#{guild_settings.get('active_text_channel_id')}>" if guild_settings.get('active_text_channel_id') else "None",
            inline=True
        )
        embed.add_field(name="Queue Length", value=str(queue.size()), inline=True)
        embed.add_field(name="Currently Playing", value="Yes" if queue.is_playing else "No", inline=True)
        embed.set_footer(text=f"Port: {settings.TTS_PORT} | Model: {settings.TTS_MODEL_TYPE}")

        await interaction.followup.send(embed=embed)
