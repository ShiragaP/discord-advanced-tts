"""
TTS Core Slash Commands: /join, /leave, /listen, /stop, /say, /status
"""

import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional

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

    @app_commands.command(name="join", description="ให้บอทเข้าห้องเสียง")
    @app_commands.describe(channel="ห้องเสียงที่ต้องการให้บอทเข้า (เว้นว่างไว้เพื่อเข้าห้องที่คุณกำลังอยู่)")
    async def join(self, interaction: discord.Interaction, channel: Optional[discord.VoiceChannel] = None):
        target_channel = channel or (interaction.user.voice.channel if interaction.user.voice else None)
        if not target_channel:
            # Check if there is an active guild voice channel
            active_vc_id = (await db_manager.get_guild_settings(str(interaction.guild_id))).get("active_voice_channel_id")
            if active_vc_id:
                target_channel = interaction.guild.get_channel(int(active_vc_id))
            # Or first voice channel with members
            if not target_channel:
                for vc in interaction.guild.voice_channels:
                    if len([m for m in vc.members if not m.bot]) > 0:
                        target_channel = vc
                        break

        if not target_channel:
            await interaction.response.send_message("❌ กรุณาเข้าห้องเสียงก่อน หรือระบุห้องเสียง เช่น `/join channel:#ห้องเสียง`", ephemeral=True)
            return

        await interaction.response.defer()

        try:
            await self.player.connect_to_voice(target_channel)
            await db_manager.set_guild_channel(
                guild_id=str(interaction.guild_id),
                text_channel_id=str(interaction.channel_id),
                voice_channel_id=str(target_channel.id)
            )
            await interaction.followup.send(
                f"🔊 บอทเข้าห้องเสียง **{target_channel.name}** แล้ว!\n"
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
        voice_channel = interaction.user.voice.channel if interaction.user.voice else None
        if not voice_channel:
            active_vc_id = (await db_manager.get_guild_settings(str(interaction.guild_id))).get("active_voice_channel_id")
            if active_vc_id:
                voice_channel = interaction.guild.get_channel(int(active_vc_id))

        if not voice_channel:
            await interaction.response.send_message("❌ กรุณาเข้าห้องเสียงก่อนเพื่อเปิดระบบอ่านข้อความ", ephemeral=True)
            return

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
        guild_settings = await db_manager.get_guild_settings(str(interaction.guild_id))
        guild_mode = guild_settings.get("tts_mode", settings.DEFAULT_TTS_MODE)
        if not settings.ENABLE_LOCAL_TTS:
            guild_mode = "wavespeed"
            local_presets = {"female_default", "female_fast", "male_default", "vachana_female", "vachana_male", "pythaitts_default"}
            if not voice_id or voice_id in local_presets:
                voice_id = await db_manager.get_guild_wavespeed_voice(str(interaction.guild_id))
        elif guild_mode in ["wavespeed", "cloud"]:
            if not await db_manager.is_user_allowed_wavespeed(str(interaction.guild_id), interaction.user.name, interaction.user.display_name):
                guild_mode = "local"
            else:
                local_presets = {"female_default", "female_fast", "male_default", "vachana_female", "vachana_male", "pythaitts_default"}
                if not voice_id or voice_id in local_presets:
                    voice_id = await db_manager.get_guild_wavespeed_voice(str(interaction.guild_id))

        clean_text = normalizer.normalize(text)
        if not clean_text:
            await interaction.followup.send("❌ ข้อความว่างเปล่าหรือมีแต่อักขระที่ไม่รองรับ", ephemeral=True)
            return

        try:
            audio_path = await tts_client.synthesize(clean_text, voice_id=voice_id, speed=speed, mode=guild_mode)
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

    @app_commands.command(name="mode", description="เลือกระบบสังเคราะห์เสียง: local (ThonburianTTS) หรือ wavespeed (ElevenLabs)")
    @app_commands.describe(engine="เลือกโหมดสังเคราะห์เสียง")
    @app_commands.choices(engine=[
        app_commands.Choice(name="local - ThonburianTTS (GPU ภายในเครื่อง)", value="local"),
        app_commands.Choice(name="wavespeed - ElevenLabs (WaveSpeed Cloud AI)", value="wavespeed"),
    ])
    async def mode(self, interaction: discord.Interaction, engine: app_commands.Choice[str]):
        await interaction.response.defer()
        new_mode = engine.value

        await db_manager.set_guild_mode(str(interaction.guild_id), new_mode)

        if new_mode == "wavespeed":
            wavespeed_count = len(settings.wavespeed_keys_list)
            whitelist = await db_manager.get_guild_whitelist(str(interaction.guild_id))
            whitelist_str = ", ".join(f"'{k}'" for k in whitelist)
            guild_voice = await db_manager.get_guild_wavespeed_voice(str(interaction.guild_id))
            desc = (
                f"☁️ เปลี่ยนโหมดเป็น **WaveSpeed AI ({settings.WAVESPEED_MODEL})** เรียบร้อยแล้ว!\n"
                f"• โมเดล: `{settings.WAVESPEED_MODEL}`\n"
                f"• Active API Keys: `{wavespeed_count}` keys (สุ่มคีย์อัตโนมัติทุกครั้ง)\n"
                f"• Voice ID ปัจจุบัน: `{guild_voice}` (เปลี่ยนได้ด้วย `/wavespeed_voice`)\n"
                f"• สมาชิกใน Whitelist ({whitelist_str}) จะอ่านด้วย WaveSpeed ส่วนสมาชิกท่านอื่นจะอ่านด้วย Local TTS อัตโนมัติ"
            )
        else:
            if not settings.ENABLE_LOCAL_TTS:
                desc = (
                    f"⚠️ **Local TTS (GPU) ถูกปิดใช้งานอยู่ในระบบ** (ENABLE_LOCAL_TTS=false)\n"
                    f"• ระบบยังคงสังเคราะห์เสียงด้วย **WaveSpeed Cloud AI** เพื่อความต่อเนื่อง\n"
                    f"• หากต้องการเปิดใช้งาน Local TTS ให้ตั้งค่า `ENABLE_LOCAL_TTS=true` ใน Environment"
                )
            else:
                desc = (
                    f"🖥️ เปลี่ยนโหมดเป็น **Local (ThonburianTTS F5-TTS)** เรียบร้อยแล้ว!\n"
                    f"• ทำงานบน GPU ภายในเซิร์ฟเวอร์\n"
                    f"• ไม่จำกัดโควต้า / ไม่มีค่าใช้จ่ายภายนอก"
                )

        embed = discord.Embed(
            title="🎛️ ตั้งค่าโหมดสังเคราะห์เสียง (TTS Mode)",
            description=desc,
            color=discord.Color.blue() if new_mode == "wavespeed" else discord.Color.green()
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(
        name="wavespeed_voice",
        description="เปลี่ยนหรือดูรหัสเสียง WaveSpeed (ElevenLabs Voice ID) ของเซิร์ฟเวอร์แบบทันที"
    )
    @app_commands.describe(
        voice_id="ElevenLabs Voice ID ที่ต้องการ (ปล่อยว่างเพื่อดู Voice ID ปัจจุบัน)"
    )
    async def wavespeed_voice(self, interaction: discord.Interaction, voice_id: Optional[str] = None):
        await interaction.response.defer()
        current_voice = await db_manager.get_guild_wavespeed_voice(str(interaction.guild_id))

        if not voice_id:
            embed = discord.Embed(
                title="🎙️ การตั้งค่าเสียง WaveSpeed (ElevenLabs Voice ID)",
                description=(
                    f"• **Voice ID ปัจจุบัน:** `{current_voice}`\n"
                    f"• **โมเดล:** `{settings.WAVESPEED_MODEL}`\n"
                    f"• **ความเร็วเริ่มต้น:** `{settings.WAVESPEED_DEFAULT_SPEED}x`\n\n"
                    f"💡 หากต้องการเปลี่ยนเสียง ให้พิมพ์: `/wavespeed_voice [voice_id]`\n"
                    f"💡 ตัวอย่าง Voice ID ภาษาไทยเริ่มต้น: `{settings.WAVESPEED_VOICE_ID}`"
                ),
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed)
            return

        clean_voice_id = voice_id.strip()
        if len(clean_voice_id) < 3 or len(clean_voice_id) > 60:
            await interaction.followup.send("❌ Voice ID ต้องมีความยาวระหว่าง 3 ถึง 60 ตัวอักษร", ephemeral=True)
            return

        await db_manager.set_guild_wavespeed_voice(str(interaction.guild_id), clean_voice_id)

        embed = discord.Embed(
            title="✅ อัปเดตเสียง WaveSpeed เรียบร้อยแล้ว!",
            description=(
                f"• **Voice ID ใหม่:** `{clean_voice_id}`\n"
                f"• มีผลกับการสังเคราะห์เสียง WaveSpeed ทันที\n"
                f"• สมาชิกทุกคนในโหมด WaveSpeed จะใช้เสียงนี้โดยอัตโนมัติ"
            ),
            color=discord.Color.green()
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="status", description="ตรวจสอบสถานะการทำงานของบอทและ TTS GPU Engine")
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild_settings = await db_manager.get_guild_settings(str(interaction.guild_id))
        queue = queue_manager.get_queue(interaction.guild_id)
        guild_ws_voice = await db_manager.get_guild_wavespeed_voice(str(interaction.guild_id))

        if not settings.ENABLE_LOCAL_TTS:
            gpu_status = "☁️ WaveSpeed Cloud (Local TTS Disabled)"
            vram_info = "N/A (Running in Cloud-only mode)"
        else:
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
        embed.add_field(
            name="Active Mode",
            value=f"`{guild_settings.get('tts_mode', settings.DEFAULT_TTS_MODE).upper()}`",
            inline=True
        )
        embed.add_field(name="WaveSpeed Voice", value=f"`{guild_ws_voice}`", inline=True)
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
        embed.set_footer(text=f"Port: {settings.TTS_PORT} | Local: {settings.TTS_MODEL_TYPE} | Cloud: {settings.WAVESPEED_MODEL}")

        await interaction.followup.send(embed=embed)
