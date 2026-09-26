"""
Voice Player and Connection Manager for Discord.
Integrates discord.VoiceClient with GuildAudioQueue for gapless, sequential playback.
"""

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Optional
import discord

from shared.config import settings
from apps.discord_bot.voice.audio_queue import queue_manager, AudioQueueItem

logger = logging.getLogger("voice_player")


class VoicePlayer:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self._ensure_ffmpeg_path()

    def _ensure_ffmpeg_path(self):
        # Check if ffmpeg is in PATH or known location
        if shutil.which("ffmpeg") is None:
            winget_ffmpeg = r"C:\Users\shiraga\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-essentials_build\bin"
            if os.path.exists(winget_ffmpeg) and winget_ffmpeg not in os.environ.get("PATH", ""):
                os.environ["PATH"] = winget_ffmpeg + os.pathsep + os.environ.get("PATH", "")

    async def connect_to_voice(self, channel: discord.VoiceChannel) -> discord.VoiceClient:
        guild = channel.guild
        voice_client: Optional[discord.VoiceClient] = guild.voice_client

        if voice_client is not None:
            if voice_client.channel.id != channel.id:
                await voice_client.move_to(channel)
            return voice_client

        voice_client = await channel.connect(reconnect=True, timeout=20.0)
        # Start queue worker for this guild
        self.start_worker(guild.id)
        return voice_client

    async def disconnect_from_voice(self, guild: discord.Guild):
        queue = queue_manager.get_queue(guild.id)
        queue.clear()

        voice_client: Optional[discord.VoiceClient] = guild.voice_client
        if voice_client and voice_client.is_connected():
            if voice_client.is_playing():
                voice_client.stop()
            await voice_client.disconnect(force=True)

        queue_manager.remove_queue(guild.id)

    def start_worker(self, guild_id: int):
        queue = queue_manager.get_queue(guild_id)
        if queue.worker_task is None or queue.worker_task.done():
            queue.worker_task = asyncio.create_task(self._process_guild_queue(guild_id))

    async def _process_guild_queue(self, guild_id: int):
        queue = queue_manager.get_queue(guild_id)
        logger.info("Started playback queue worker for guild %d", guild_id)

        while True:
            try:
                item: AudioQueueItem = await queue.queue.get()
                queue.current_item = item

                guild = self.bot.get_guild(guild_id)
                if not guild:
                    queue.queue.task_done()
                    break

                voice_client: Optional[discord.VoiceClient] = guild.voice_client
                if not voice_client or not voice_client.is_connected():
                    logger.warning("Voice client disconnected while processing queue for guild %d", guild_id)
                    queue.queue.task_done()
                    continue

                if not item.audio_path.exists():
                    logger.error("Audio file does not exist: %s", item.audio_path)
                    queue.queue.task_done()
                    continue

                # Play audio using FFmpeg with volume transformer
                file_size = item.audio_path.stat().st_size if item.audio_path.exists() else 0
                logger.info(
                    "▶️ Playing audio for '%s' (%d bytes, path: %s)",
                    item.text[:40], file_size, item.audio_path.name
                )

                finished_event = asyncio.Event()

                def after_playback(error):
                    if error:
                        logger.error("Playback error in guild %d: %s", guild_id, error)
                    finished_event.set()

                ffmpeg_audio = discord.FFmpegPCMAudio(
                    str(item.audio_path),
                    options="-loglevel warning"
                )
                audio_source = discord.PCMVolumeTransformer(ffmpeg_audio, volume=1.2)

                queue.is_playing = True
                voice_client.play(audio_source, after=after_playback)

                # Wait until audio finishes playing
                await finished_event.wait()
                queue.is_playing = False
                queue.current_item = None
                queue.queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Error in guild audio worker for %d: %s", guild_id, e)
                await asyncio.sleep(0.5)

    def stop_playback(self, guild: discord.Guild):
        queue = queue_manager.get_queue(guild.id)
        queue.clear()
        voice_client: Optional[discord.VoiceClient] = guild.voice_client
        if voice_client and voice_client.is_playing():
            voice_client.stop()
