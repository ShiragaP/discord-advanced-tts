"""
Per-Guild Audio Playback Queue Manager.
Ensures messages in each Discord server play sequentially without overlapping audio.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Callable, Awaitable
import discord

logger = logging.getLogger("audio_queue")


@dataclass
class AudioQueueItem:
    audio_path: Path
    text: str
    author_name: str
    channel_id: int


class GuildAudioQueue:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
        self.queue: asyncio.Queue[AudioQueueItem] = asyncio.Queue()
        self.current_item: Optional[AudioQueueItem] = None
        self.worker_task: Optional[asyncio.Task] = None
        self.is_playing = False

    async def put(self, item: AudioQueueItem):
        await self.queue.put(item)

    def clear(self):
        """Clears all queued items."""
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except (asyncio.QueueEmpty, ValueError):
                break
        self.current_item = None

    def size(self) -> int:
        return self.queue.qsize()


class QueueManager:
    def __init__(self):
        self.guild_queues: Dict[int, GuildAudioQueue] = {}

    def get_queue(self, guild_id: int) -> GuildAudioQueue:
        if guild_id not in self.guild_queues:
            self.guild_queues[guild_id] = GuildAudioQueue(guild_id)
        return self.guild_queues[guild_id]

    def remove_queue(self, guild_id: int):
        if guild_id in self.guild_queues:
            q = self.guild_queues.pop(guild_id)
            q.clear()
            if q.worker_task and not q.worker_task.done():
                q.worker_task.cancel()


queue_manager = QueueManager()
