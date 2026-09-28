"""
Discord Advanced Thai TTS (DAT) — Discord Bot Service.
Connects to Discord Gateway, handles automatic channel listening, and queues speech playback.
"""

import asyncio
import logging
import os
import sys
import time
from collections import defaultdict
from typing import Dict

import discord
from discord.ext import commands

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from shared.config import settings
from shared.database import db_manager
from shared.thai_normalizer import normalizer
from apps.discord_bot.voice.player import VoicePlayer
from apps.discord_bot.voice.audio_queue import queue_manager, AudioQueueItem
from apps.discord_bot.services.tts_client import tts_client
from apps.discord_bot.commands.tts import TTSCommands
from apps.discord_bot.commands.voice import VoiceCommands
from apps.discord_bot.commands.admin import AdminCommands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("discord_bot")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(
    command_prefix=settings.DISCORD_COMMAND_PREFIX,
    intents=intents,
    help_command=None
)

voice_player = VoicePlayer(bot)
user_last_spoke: Dict[int, float] = defaultdict(float)


@bot.event
async def setup_hook():
    logger.info("Initializing database...")
    await db_manager.init_db()

    logger.info("Registering slash command cogs...")
    await bot.add_cog(TTSCommands(bot, voice_player))
    await bot.add_cog(VoiceCommands(bot))
    await bot.add_cog(AdminCommands(bot))

    logger.info("Syncing slash commands globally...")
    try:
        synced = await bot.tree.sync()
        logger.info("Successfully synced %d slash commands.", len(synced))
    except Exception as e:
        logger.error("Failed to sync slash commands: %s", e)


@bot.event
async def on_ready():
    logger.info("Logged in as %s (ID: %d)", bot.user.name, bot.user.id)
    activity = discord.Activity(
        type=discord.ActivityType.listening,
        name="ภาษาไทย | /join"
    )
    await bot.change_presence(status=discord.Status.online, activity=activity)

    # Instant sync to all guilds so slash commands appear immediately without Discord cache delay
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            logger.info("⚡ Instantly synced %d slash commands to guild '%s' (%d)", len(synced), guild.name, guild.id)
        except Exception as e:
            logger.warning("Could not sync to guild %s: %s", guild.name, e)


@bot.command(name="sync")
async def manual_sync(ctx: commands.Context):
    """Fallback manual sync command: !sync"""
    try:
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"⚡ ซิงค์คำสั่ง Slash Commands ({len(synced)} คำสั่ง) เข้าเซิร์ฟเวอร์นี้ทันทีเรียบร้อยแล้ว! ลองพิมพ์ `/join` ได้เลย")
    except Exception as e:
        await ctx.send(f"❌ ซิงค์ไม่สำเร็จ: {e}")


@bot.command(name="join")
async def prefix_join(ctx: commands.Context, *, channel: str = None):
    """Fallback prefix command: !join [optional channel name/id]"""
    target_channel = None
    if channel:
        clean_name = channel.strip("<#>").strip()
        target_channel = discord.utils.get(ctx.guild.voice_channels, name=clean_name)
        if not target_channel and clean_name.isdigit():
            target_channel = ctx.guild.get_channel(int(clean_name))

    if not target_channel and ctx.author.voice and ctx.author.voice.channel:
        target_channel = ctx.author.voice.channel

    if not target_channel:
        # Check active guild voice channel
        active_vc_id = (await db_manager.get_guild_settings(str(ctx.guild.id))).get("active_voice_channel_id")
        if active_vc_id:
            target_channel = ctx.guild.get_channel(int(active_vc_id))

    if not target_channel:
        await ctx.send("❌ กรุณาเข้าห้องเสียงก่อน หรือระบุชื่อห้องเสียง เช่น `!join General`")
        return

    try:
        await voice_player.connect_to_voice(target_channel)
        await db_manager.set_guild_channel(
            guild_id=str(ctx.guild.id),
            text_channel_id=str(ctx.channel.id),
            voice_channel_id=str(target_channel.id)
        )
        await ctx.send(
            f"🔊 บอทเข้าห้องเสียง **{target_channel.name}** แล้ว!\n"
            f"📖 กำลังอ่านข้อความจากห้อง {ctx.channel.mention} อัตโนมัติ (พิมพ์คุยได้เลย ไม่ต้องใช้คำสั่ง)"
        )
    except Exception as e:
        await ctx.send(f"❌ ไม่สามารถเข้าห้องเสียงได้: {e}")


@bot.command(name="leave")
async def prefix_leave(ctx: commands.Context):
    """Fallback prefix command: !leave"""
    try:
        await voice_player.disconnect_from_voice(ctx.guild)
        await db_manager.deactivate_guild(str(ctx.guild.id))
        await ctx.send("👋 ออกจากห้องเสียงเรียบร้อยแล้ว")
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาด: {e}")


@bot.command(name="mode")
async def prefix_mode(ctx: commands.Context, new_mode: str = None):
    """Fallback prefix command: !mode <local|wavespeed>"""
    if not new_mode:
        current_mode = await db_manager.get_guild_mode(str(ctx.guild.id))
        await ctx.send(f"🎛️ โหมดปัจจุบันของเซิร์ฟเวอร์คือ: `{current_mode}`\nพิมพ์ `!mode local` หรือ `!mode wavespeed` เพื่อเปลี่ยนโหมด")
        return

    mode_val = new_mode.lower().strip()
    if mode_val not in ["local", "wavespeed"]:
        await ctx.send("❌ โหมดไม่ถูกต้อง กรุณาเลือก `local` หรือ `wavespeed` เช่น `!mode wavespeed`")
        return

    await db_manager.set_guild_mode(str(ctx.guild.id), mode_val)
    if mode_val == "wavespeed":
        wavespeed_count = len(settings.wavespeed_keys_list)
        whitelist = await db_manager.get_guild_whitelist(str(ctx.guild.id))
        whitelist_str = ", ".join(f"'{k}'" for k in whitelist)
        guild_voice = await db_manager.get_guild_wavespeed_voice(str(ctx.guild.id))
        await ctx.send(
            f"☁️ เปลี่ยนโหมดเป็น **WaveSpeed (ElevenLabs v3)** เรียบร้อยแล้ว!\n"
            f"• Voice ID ปัจจุบัน: `{guild_voice}`\n"
            f"• สมาชิกใน Whitelist ({whitelist_str}) จะอ่านด้วย WaveSpeed ส่วนสมาชิกท่านอื่นจะอ่านด้วย Local TTS อัตโนมัติ"
        )
    else:
        if not settings.ENABLE_LOCAL_TTS:
            await ctx.send("⚠️ **Local TTS (GPU) ถูกปิดใช้งานอยู่ในระบบ** (ENABLE_LOCAL_TTS=false)\nบอทจะยังคงอ่านด้วยเสียง WaveSpeed Cloud AI ตามปกติ")
        else:
            await ctx.send("🖥️ เปลี่ยนโหมดเป็น **Local (ThonburianTTS F5-TTS)** เรียบร้อยแล้ว!")


@bot.command(name="whitelist")
async def prefix_whitelist(ctx: commands.Context, action: str = "list", *, keyword: str = ""):
    """Fallback prefix command: !whitelist <add|remove|list> [keyword]"""
    if not (ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะ Admin หรือผู้ที่มีสิทธิ์จัดการเซิร์ฟเวอร์ (Manage Server) เท่านั้น")
        return

    act = action.lower().strip()
    if act == "add":
        clean_kw = keyword.strip()
        if not clean_kw:
            await ctx.send("❌ กรุณาระบุคำที่ต้องการเพิ่ม เช่น `!whitelist add misu`")
            return
        updated = await db_manager.add_guild_whitelist(str(ctx.guild.id), clean_kw)
        list_str = ", ".join(f"`{k}`" for k in updated)
        await ctx.send(f"✅ เพิ่ม `{clean_kw.lower()}` เข้า WaveSpeed Whitelist เรียบร้อยแล้ว!\n📋 Whitelist ปัจจุบัน: {list_str}")

    elif act in ["remove", "del", "delete"]:
        clean_kw = keyword.strip()
        if not clean_kw:
            await ctx.send("❌ กรุณาระบุคำที่ต้องการลบ เช่น `!whitelist remove misu`")
            return
        deleted, updated = await db_manager.remove_guild_whitelist(str(ctx.guild.id), clean_kw)
        list_str = ", ".join(f"`{k}`" for k in updated) if updated else "*(ว่างเปล่า)*"
        if deleted:
            await ctx.send(f"🗑️ ลบ `{clean_kw.lower()}` ออกจาก Whitelist เรียบร้อยแล้ว!\n📋 Whitelist ปัจจุบัน: {list_str}")
        else:
            await ctx.send(f"⚠️ ไม่พบ `{clean_kw.lower()}` ใน Whitelist\n📋 Whitelist ปัจจุบัน: {list_str}")

    elif act == "list":
        current = await db_manager.get_guild_whitelist(str(ctx.guild.id))
        list_str = ", ".join(f"`{k}`" for k in current) if current else "*(ว่างเปล่า)*"
        await ctx.send(f"📋 **WaveSpeed Whitelist ของเซิร์ฟเวอร์:**\n{list_str}\n\n💡 สมาชิกที่มีคำเหล่านี้ในชื่อจะได้รับสิทธิ์ใช้ WaveSpeed")
    else:
        await ctx.send("❌ รูปแบบคำสั่งไม่ถูกต้อง:\n• `!whitelist list`\n• `!whitelist add <คำ>`\n• `!whitelist remove <คำ>`")


@bot.command(name="wavespeed_voice")
async def prefix_wavespeed_voice(ctx: commands.Context, voice_id: str = None):
    """Fallback prefix command: !wavespeed_voice [voice_id]"""
    if not voice_id:
        current_voice = await db_manager.get_guild_wavespeed_voice(str(ctx.guild.id))
        await ctx.send(f"🎙️ WaveSpeed Voice ID ปัจจุบันคือ: `{current_voice}`\nพิมพ์ `!wavespeed_voice <voice_id>` เพื่อเปลี่ยนเสียง")
        return

    clean_id = voice_id.strip()
    if len(clean_id) < 3 or len(clean_id) > 60:
        await ctx.send("❌ Voice ID ต้องมีความยาวระหว่าง 3 ถึง 60 ตัวอักษร")
        return

    await db_manager.set_guild_wavespeed_voice(str(ctx.guild.id), clean_id)
    await ctx.send(f"✅ อัปเดต WaveSpeed Voice ID สำหรับเซิร์ฟเวอร์นี้เป็น `{clean_id}` เรียบร้อยแล้ว!")


@bot.command(name="wavespeed_model")
async def prefix_wavespeed_model(ctx: commands.Context, model_id: str = None):
    """Fallback prefix command: !wavespeed_model [model_id]"""
    if not model_id:
        current_model = await db_manager.get_guild_wavespeed_model(str(ctx.guild.id))
        await ctx.send(
            f"🧠 **WaveSpeed Model ปัจจุบัน:** `{current_model}`\n\n"
            f"โมเดลที่แนะนำ:\n"
            f"• `!wavespeed_model elevenlabs/turbo-v2.5` (⚡ เร็วที่สุด ~1.4s, Latency ต่ำ)\n"
            f"• `!wavespeed_model elevenlabs/multilingual-v2` (🌐 เสถียร มาตรฐาน ~1.8s)\n"
            f"• `!wavespeed_model elevenlabs/eleven-v3` (🎙️ คุณภาพสตูดิโอสูงสุด ~2.5s)"
        )
        return

    clean_model = model_id.strip()
    aliases = {
        "turbo": "elevenlabs/turbo-v2.5",
        "turbo-v2.5": "elevenlabs/turbo-v2.5",
        "turbo2.5": "elevenlabs/turbo-v2.5",
        "v2.5": "elevenlabs/turbo-v2.5",
        "multilingual": "elevenlabs/multilingual-v2",
        "v2": "elevenlabs/multilingual-v2",
        "multilingual-v2": "elevenlabs/multilingual-v2",
        "v3": "elevenlabs/eleven-v3",
        "eleven-v3": "elevenlabs/eleven-v3",
    }
    resolved_model = aliases.get(clean_model.lower(), clean_model)

    await db_manager.set_guild_wavespeed_model(str(ctx.guild.id), resolved_model)
    await ctx.send(f"✅ อัปเดต WaveSpeed Model เป็น `{resolved_model}` เรียบร้อยแล้ว! (มีผลกับการอ่านข้อความทันที)")


@bot.command(name="status")
async def prefix_status(ctx: commands.Context):
    """Fallback prefix command: !status"""
    guild_settings = await db_manager.get_guild_settings(str(ctx.guild.id))
    current_mode = guild_settings.get("tts_mode", settings.DEFAULT_TTS_MODE)
    guild_ws_voice = await db_manager.get_guild_wavespeed_voice(str(ctx.guild.id))
    guild_ws_model = await db_manager.get_guild_wavespeed_model(str(ctx.guild.id))
    await ctx.send(
        f"⚡ **DAT System Status**\n"
        f"• โหมดปัจจุบัน: `{current_mode.upper()}`\n"
        f"• WaveSpeed Voice: `{guild_ws_voice}`\n"
        f"• WaveSpeed Model: `{guild_ws_model}`\n"
        f"• กำลังเชื่อมต่อ: {'Yes' if ctx.guild.voice_client and ctx.guild.voice_client.is_connected() else 'No'}"
    )


@bot.command(name="voice")
async def prefix_voice(ctx: commands.Context, *, args: str = None):
    """Fallback prefix command: !voice [voice_id] [speed]"""
    if not args:
        user_pref = await db_manager.get_user_preference(str(ctx.author.id))
        await ctx.send(
            f"🎭 **การตั้งค่าเสียงของคุณ ({ctx.author.display_name})**\n"
            f"• Voice ID: `{user_pref['voice_id']}`\n"
            f"• Speed: `{user_pref['speed']}x`\n\n"
            f"💡 เปลี่ยนเสียง: `!voice <voice_id> [speed]` เช่น `!voice 6UZ6Y6OSl14UA2aOxuMM 0.8`\n"
            f"💡 ดูรายชื่อเสียง Local: `!voices`"
        )
        return

    raw = args.strip()
    voice_id = None
    speed = 1.0
    target_user = ctx.author

    # Check if a member was mentioned to set voice for (Admin only)
    if ctx.message.mentions:
        target_user = ctx.message.mentions[0]
        if target_user.id != ctx.author.id:
            if not (ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild):
                await ctx.send("❌ คุณไม่มีสิทธิ์ตั้งค่าเสียงให้สมาชิกท่านอื่น (ต้องมีสิทธิ์ Admin หรือ Manage Server)")
                return
        import re
        raw = re.sub(r"<@!?[0-9]+>", "", raw).strip()

    # Support named parameters: voice_id: xxx speed: yyy
    if "voice_id:" in raw or "speed:" in raw:
        import re
        m_voice = re.search(r"voice_id:\s*([^\s]+)", raw)
        m_speed = re.search(r"speed:\s*([0-9\.]+)", raw)
        if m_voice:
            voice_id = m_voice.group(1).strip()
        if m_speed:
            try:
                speed = float(m_speed.group(1))
            except ValueError:
                pass
    else:
        parts = raw.split()
        if len(parts) >= 1:
            voice_id = parts[0].strip()
        if len(parts) >= 2:
            try:
                speed = float(parts[1].strip())
            except ValueError:
                speed = 1.0

    if not voice_id:
        await ctx.send("❌ กรุณาระบุ Voice ID เช่น `!voice 6UZ6Y6OSl14UA2aOxuMM 0.8`")
        return

    if speed < 0.5 or speed > 2.0:
        await ctx.send("❌ ความเร็วเสียงต้องอยู่ระหว่าง 0.5 ถึง 2.0")
        return

    try:
        available_voices = await tts_client.get_voices()
        matched = any(v["id"].lower() == voice_id.lower() for v in available_voices)
        is_custom_id = 3 <= len(voice_id) <= 60 and all(c.isalnum() or c in "-_" for c in voice_id)

        if not matched and not is_custom_id:
            voice_ids = ", ".join(f"`{v['id']}`" for v in available_voices)
            await ctx.send(f"❌ ไม่พบรหัสเสียง `{voice_id}`\nเสียงที่มีให้เลือก: {voice_ids}\nหรือใส่ ElevenLabs Voice ID สำหรับโหมด WaveSpeed")
            return

        saved_voice_id = voice_id if (is_custom_id and not matched) else voice_id.lower()
        await db_manager.set_user_preference(
            user_id=str(target_user.id),
            voice_id=saved_voice_id,
            speed=speed
        )
        target_name = f"สมาชิก {target_user.mention}" if target_user.id != ctx.author.id else "ของคุณ"
        await ctx.send(f"✅ บันทึกการตั้งค่าเสียง{target_name}เรียบร้อยแล้ว!\n**เสียง:** `{saved_voice_id}` | **ความเร็ว:** `{speed}x`")
    except Exception as e:
        await ctx.send(f"❌ เกิดข้อผิดพลาดในการบันทึก: {e}")


@bot.command(name="setvoice")
async def prefix_setvoice(ctx: commands.Context, member: discord.Member = None, voice_id: str = None, speed: float = 1.0):
    """Fallback admin prefix command: !setvoice @member <voice_id> [speed]"""
    if not (ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild):
        await ctx.send("❌ คำสั่งนี้ใช้ได้เฉพาะ Admin หรือผู้ที่มีสิทธิ์จัดการเซิร์ฟเวอร์ (Manage Server) เท่านั้น")
        return

    if not member or not voice_id:
        await ctx.send("❌ กรุณาระบุสมาชิกและ Voice ID เช่น `!setvoice @User 6UZ6Y6OSl14UA2aOxuMM 0.8`")
        return

    if speed < 0.5 or speed > 2.0:
        await ctx.send("❌ ความเร็วเสียงต้องอยู่ระหว่าง 0.5 ถึง 2.0")
        return

    clean_voice_id = voice_id.strip()
    is_custom_id = 3 <= len(clean_voice_id) <= 60 and all(c.isalnum() or c in "-_" for c in clean_voice_id)
    available_voices = await tts_client.get_voices()
    matched = any(v["id"].lower() == clean_voice_id.lower() for v in available_voices)

    if not matched and not is_custom_id:
        await ctx.send(f"❌ Voice ID `{clean_voice_id}` ไม่ถูกต้อง (ความยาว 3-60 ตัวอักษร)")
        return

    saved_voice_id = clean_voice_id if (is_custom_id and not matched) else clean_voice_id.lower()
    await db_manager.set_user_preference(
        user_id=str(member.id),
        voice_id=saved_voice_id,
        speed=speed
    )
    await ctx.send(
        f"✅ กำหนดเสียงให้สมาชิก {member.mention} เรียบร้อยแล้ว!\n"
        f"**Voice ID:** `{saved_voice_id}` | **ความเร็ว:** `{speed}x`"
    )


@bot.command(name="voices")
async def prefix_voices(ctx: commands.Context):
    """Fallback prefix command: !voices"""
    try:
        voice_list = await tts_client.get_voices()
        lines = ["🎭 **รายชื่อโปรไฟล์เสียงพูด (Voice Profiles)**"]
        for v in voice_list:
            default_tag = " ⭐ (Default)" if v.get("is_default") else ""
            lines.append(f"• `{v['id']}` — {v['name']}{default_tag} ({v.get('description', '-')})")

        guild_ws_voice = await db_manager.get_guild_wavespeed_voice(str(ctx.guild.id))
        lines.append(f"\n☁️ **WaveSpeed AI (ElevenLabs)**")
        lines.append(f"• Voice ID ปัจจุบันของเซิร์ฟเวอร์: `{guild_ws_voice}`")
        lines.append(f"• เปลี่ยนเสียงส่วนตัว: `!voice <voice_id> [speed]`")
        lines.append(f"• เปลี่ยนเสียงทั้งเซิร์ฟเวอร์: `!wavespeed_voice <voice_id>`")

        await ctx.send("\n".join(lines))
    except Exception as e:
        await ctx.send(f"❌ ไม่สามารถดึงรายชื่อเสียงได้: {e}")


@bot.command(name="stop")
async def prefix_stop(ctx: commands.Context):
    """Fallback prefix command: !stop"""
    voice_player.stop_playback(ctx.guild)
    await ctx.send("⏹️ หยุดเล่นเสียงและล้างคิวเรียบร้อยแล้ว")


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    # If the bot is left alone in a voice channel, auto-disconnect after delay
    if member.id == bot.user.id:
        return

    guild = member.guild
    voice_client: discord.VoiceClient = guild.voice_client

    if voice_client and voice_client.channel:
        non_bot_members = [m for m in voice_client.channel.members if not m.bot]
        if len(non_bot_members) == 0:
            logger.info("Voice channel is empty. Disconnecting from guild %s (%d)...", guild.name, guild.id)
            await voice_player.disconnect_from_voice(guild)
            await db_manager.deactivate_guild(str(guild.id))


@bot.event
async def on_message(message: discord.Message):
    # Ignore messages from bots or outside guilds
    if message.author.bot or not message.guild:
        return

    # Process traditional prefix commands if any
    await bot.process_commands(message)

    # If message was a command prefix, do not process as TTS text
    if message.content.startswith(settings.DISCORD_COMMAND_PREFIX):
        return

    # Check if voice client is connected
    voice_client: discord.VoiceClient = message.guild.voice_client
    if not voice_client or not voice_client.is_connected():
        return

    # Check if channel is configured for auto-reading
    guild_settings = await db_manager.get_guild_settings(str(message.guild.id))
    active_text_channel = guild_settings.get("active_text_channel_id")
    is_active = guild_settings.get("is_active", 0)

    # Read automatically if message is in the bound text channel OR inside the voice channel's text chat
    is_bound_channel = is_active and (str(message.channel.id) == str(active_text_channel))
    is_voice_chat = voice_client.channel and (message.channel.id == voice_client.channel.id)

    if not (is_bound_channel or is_voice_chat):
        return

    # Rate limiting per user
    now = time.time()
    last_time = user_last_spoke[message.author.id]
    if now - last_time < settings.USER_RATE_LIMIT_SECONDS:
        return
    user_last_spoke[message.author.id] = now

    # Retrieve user voice settings
    user_pref = await db_manager.get_user_preference(str(message.author.id))
    voice_id = user_pref["voice_id"]
    speed = user_pref["speed"]

    # Normalize text
    raw_text = message.clean_content
    # Apply guild custom pronunciations first
    pronunciations = await db_manager.get_guild_pronunciations(str(message.guild.id))
    for word, replacement in pronunciations.items():
        raw_text = raw_text.replace(word, replacement)

    clean_text = normalizer.normalize(raw_text)
    if not clean_text:
        return

    chunks = normalizer.split_sentences(clean_text, max_chars=guild_settings.get("max_chars", settings.MAX_TEXT_LENGTH))
    queue = queue_manager.get_queue(message.guild.id)
    guild_mode = guild_settings.get("tts_mode", settings.DEFAULT_TTS_MODE)
    wavespeed_model = guild_settings.get("wavespeed_model") or settings.WAVESPEED_MODEL
    if not settings.ENABLE_LOCAL_TTS:
        guild_mode = "wavespeed"
        local_presets = {"female_default", "female_fast", "male_default", "vachana_female", "vachana_male", "pythaitts_default"}
        if not voice_id or voice_id in local_presets:
            voice_id = await db_manager.get_guild_wavespeed_voice(str(message.guild.id))
    elif guild_mode in ["wavespeed", "cloud"]:
        if not await db_manager.is_user_allowed_wavespeed(str(message.guild.id), message.author.name, message.author.display_name):
            guild_mode = "local"
        else:
            local_presets = {"female_default", "female_fast", "male_default", "vachana_female", "vachana_male", "pythaitts_default"}
            if not voice_id or voice_id in local_presets:
                voice_id = await db_manager.get_guild_wavespeed_voice(str(message.guild.id))

    for chunk in chunks:
        try:
            audio_path = await tts_client.synthesize(chunk, voice_id=voice_id, speed=speed, mode=guild_mode, model=wavespeed_model)
            await queue.put(AudioQueueItem(
                audio_path=audio_path,
                text=chunk,
                author_name=message.author.display_name,
                channel_id=message.channel.id
            ))
        except Exception as e:
            logger.error("Failed to synthesize speech for message from %s: %s", message.author.name, e)
            break


def main():
    if not settings.DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN is not set in environment or .env file!")
        print("Please set DISCORD_TOKEN in .env file before launching the bot.")
        sys.exit(1)

    bot.run(settings.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
