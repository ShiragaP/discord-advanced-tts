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
async def prefix_join(ctx: commands.Context):
    """Fallback prefix command: !join"""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send("❌ คุณต้องอยู่ในห้องเสียงก่อนจึงจะเรียกบอทได้")
        return

    voice_channel = ctx.author.voice.channel
    try:
        await voice_player.connect_to_voice(voice_channel)
        await db_manager.set_guild_channel(
            guild_id=str(ctx.guild.id),
            text_channel_id=str(ctx.channel.id),
            voice_channel_id=str(voice_channel.id)
        )
        await ctx.send(
            f"🔊 บอทเข้าห้องเสียง **{voice_channel.name}** แล้ว!\n"
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
    if guild_mode in ["wavespeed", "cloud"]:
        user_str = f"{message.author.name} {message.author.display_name}".lower()
        if "peony" not in user_str and "shiraga" not in user_str:
            guild_mode = "local"

    for chunk in chunks:
        try:
            audio_path = await tts_client.synthesize(chunk, voice_id=voice_id, speed=speed, mode=guild_mode)
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
