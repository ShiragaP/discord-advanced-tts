"""
Inference engine wrapper for ThonburianTTS.
Provides sequential GPU execution with threading/async locks, memory monitoring, and error handling.
"""

import asyncio
import io
import logging
import os
import time
from pathlib import Path
from typing import Tuple, Optional
import torch
import soundfile as sf

from flowtts.inference import FlowTTSPipeline, ModelConfig, AudioConfig
from cached_path import cached_path
from shared.config import settings
from apps.tts_server.voice_manager import voice_manager

logger = logging.getLogger("tts_inference")


class TTSInferenceEngine:
    def __init__(self):
        self.pipeline: Optional[FlowTTSPipeline] = None
        self._lock = asyncio.Lock()
        self.is_ready = False

    def load_model(self):
        logger.info("Initializing ThonburianTTS model...")
        checkpoint_path = str(cached_path(settings.TTS_CHECKPOINT))
        vocab_path = str(cached_path(settings.TTS_VOCAB_FILE))

        model_config = ModelConfig(
            language=settings.TTS_LANGUAGE,
            model_type=settings.TTS_MODEL_TYPE,
            checkpoint=checkpoint_path,
            vocab_file=vocab_path,
            ode_method=settings.TTS_ODE_METHOD,
            use_ema=True,
            vocoder=settings.TTS_VOCODER,
            device=settings.TTS_DEVICE if torch.cuda.is_available() else "cpu",
        )

        audio_config = AudioConfig(
            silence_threshold=-45,
            max_audio_length=20000,
            cfg_strength=settings.TTS_CFG_STRENGTH,
            nfe_step=settings.TTS_NFE_STEP,
            target_rms=0.1,
            cross_fade_duration=0.15,
            speed=settings.DEFAULT_SPEED,
        )

        temp_dir = settings.VOICES_DIR / "temp"
        temp_dir.mkdir(parents=True, exist_ok=True)

        self.pipeline = FlowTTSPipeline(
            model_config=model_config,
            audio_config=audio_config,
            temp_dir=str(temp_dir),
        )
        self.is_ready = True
        logger.info("ThonburianTTS model loaded successfully and ready on %s", model_config.device)

    async def synthesize(
        self,
        text: str,
        voice_id: str = "female_default",
        speed: float = 1.0
    ) -> Tuple[bytes, float, float]:
        """
        Synthesize speech asynchronously with a sequential GPU lock.
        Returns: (wav_bytes, duration_seconds, generation_seconds)
        """
        if not self.is_ready or not self.pipeline:
            raise RuntimeError("TTS model is not loaded or not ready.")

        profile = voice_manager.get_voice(voice_id)
        if not profile:
            raise ValueError(f"Voice profile '{voice_id}' not found.")

        ref_audio_file = Path(profile.ref_audio_path)
        if not ref_audio_file.is_absolute():
            ref_audio_file = Path(__file__).resolve().parent.parent.parent / profile.ref_audio_path

        if not ref_audio_file.exists():
            raise FileNotFoundError(f"Reference voice audio file not found: {ref_audio_file}")

        effective_speed = speed if speed > 0 else profile.default_speed

        async with self._lock:
            loop = asyncio.get_running_loop()
            t_start = time.perf_counter()

            # Run GPU inference in threadpool so event loop is not blocked
            wav_bytes, audio_dur = await loop.run_in_executor(
                None,
                self._run_inference_sync,
                text,
                str(ref_audio_file),
                profile.ref_text,
                effective_speed
            )
            generation_time = time.perf_counter() - t_start
            return wav_bytes, audio_dur, generation_time

    def _run_inference_sync(
        self,
        text: str,
        ref_voice_path: str,
        ref_text: str,
        speed: float
    ) -> Tuple[bytes, float]:
        temp_out = settings.VOICES_DIR / "temp" / f"synth_{time.time_ns()}.wav"
        try:
            output_path = self.pipeline(
                text=text,
                ref_voice=ref_voice_path,
                ref_text=ref_text,
                output_file=str(temp_out),
                speed=speed,
            )

            # Read back generated audio
            data, sr = sf.read(output_path, dtype="float32")
            duration = len(data) / sr

            # Normalize audio amplitude to 0.95 for loud, clear speech without clipping
            max_amp = float(np.max(np.abs(data)))
            if max_amp > 0.01:
                data = (data / max_amp) * 0.95

            # Convert to standard 16-bit PCM WAV bytes in memory
            buffer = io.BytesIO()
            sf.write(buffer, data, sr, format="WAV", subtype="PCM_16")
            wav_bytes = buffer.getvalue()
            return wav_bytes, duration
        finally:
            if temp_out.exists():
                try:
                    temp_out.unlink()
                except Exception:
                    pass


engine = TTSInferenceEngine()
