"""
Benchmark and Validation Script for ThonburianTTS (Phase 1)
Tests model loading, CUDA inference, memory consumption, and Real-Time Factor (RTF).
"""

import os
import sys
import time
from pathlib import Path
import torch
import soundfile as sf

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Ensure FFmpeg is accessible
ffmpeg_path = r"C:\Users\shiraga\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-essentials_build\bin"
if os.path.exists(ffmpeg_path) and ffmpeg_path not in os.environ.get("PATH", ""):
    os.environ["PATH"] = ffmpeg_path + os.pathsep + os.environ.get("PATH", "")

from flowtts.inference import FlowTTSPipeline, ModelConfig, AudioConfig
from cached_path import cached_path


def check_gpu():
    print("=" * 60)
    print("HARDWARE & CUDA VERIFICATION")
    print("=" * 60)
    cuda_avail = torch.cuda.is_available()
    print(f"CUDA Available: {cuda_avail}")
    if not cuda_avail:
        print("ERROR: CUDA is not available. Check NVIDIA drivers / PyTorch install.")
        return False

    gpu_name = torch.cuda.get_device_name(0)
    capability = torch.cuda.get_device_capability(0)
    vram_total_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    vram_free_gb = torch.cuda.mem_get_info()[0] / (1024 ** 3)

    print(f"Device Name:        {gpu_name}")
    print(f"Compute Capability: {capability[0]}.{capability[1]}")
    print(f"Total VRAM:         {vram_total_gb:.2f} GB")
    print(f"Free VRAM:          {vram_free_gb:.2f} GB")
    print("=" * 60)
    return True


def run_benchmark():
    if not check_gpu():
        sys.exit(1)

    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    ref_voice = Path("data/voices/samples/default_female.wav")
    ref_text = "ใครเป็นผู้รับ"

    if not ref_voice.exists():
        print(f"Error: Reference voice not found at {ref_voice}")
        sys.exit(1)

    print("\n[1/4] Loading ThonburianTTS model...")
    t0 = time.time()

    model_config = ModelConfig(
        language="th",
        model_type="F5",
        checkpoint=str(cached_path("hf://biodatlab/ThonburianTTS/megaF5/mega_f5_last.safetensors")),
        vocab_file=str(cached_path("hf://biodatlab/ThonburianTTS/megaF5/mega_vocab.txt")),
        ode_method="euler",
        use_ema=True,
        vocoder="vocos",
        device="cuda" if torch.cuda.is_available() else "cpu",
    )

    audio_config = AudioConfig(
        silence_threshold=-45,
        max_audio_length=20000,
        cfg_strength=2.0,
        nfe_step=32,
        target_rms=0.1,
        cross_fade_duration=0.15,
        speed=1.0,
    )

    pipeline = FlowTTSPipeline(
        model_config=model_config,
        audio_config=audio_config,
        temp_dir="temp_f5",
    )
    load_time = time.time() - t0
    vram_loaded_mb = torch.cuda.memory_allocated() / (1024 ** 2)
    print(f"Model loaded successfully in {load_time:.2f}s! (Model VRAM allocated: {vram_loaded_mb:.1f} MB)")

    test_sentences = [
        ("Short", "สวัสดีครับ ยินดีต้อนรับสู่ดิสคอร์ด"),
        ("Gaming", "บอสเกิดแล้ว รวมตัวที่มิดด่วน ดรอปของระดับตำนาน"),
        ("Medium", "วันนี้อากาศดีมาก ขอให้ทุกคนเล่นเกมอย่างมีความสุขและสนุกสนานนะครับ"),
    ]

    print("\n[2/4] Running live speech synthesis benchmark...")
    results = []

    for idx, (label, text) in enumerate(test_sentences, 1):
        torch.cuda.reset_peak_memory_stats()
        out_file = output_dir / f"bench_{idx}_{label.lower()}.wav"

        t_start = time.time()
        output_path = pipeline(
            text=text,
            ref_voice=str(ref_voice),
            ref_text=ref_text,
            output_file=str(out_file),
            speed=1.0,
        )
        latency = time.time() - t_start

        # Read generated audio duration
        audio_data, sr = sf.read(output_path)
        audio_duration = len(audio_data) / sr
        rtf = latency / audio_duration if audio_duration > 0 else 0
        peak_vram_mb = torch.cuda.max_memory_allocated() / (1024 ** 2)

        results.append({
            "label": label,
            "text": text,
            "char_count": len(text),
            "latency_s": latency,
            "audio_duration_s": audio_duration,
            "rtf": rtf,
            "peak_vram_mb": peak_vram_mb,
            "file": str(out_file),
        })

        print(f"  Test {idx} ({label}): '{text}'")
        print(f"    -> Latency: {latency:.2f}s | Audio Duration: {audio_duration:.2f}s | RTF: {rtf:.2f} | Peak VRAM: {peak_vram_mb:.1f} MB")

    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY REPORT")
    print("=" * 60)
    print(f"{'Type':<10} | {'Chars':<6} | {'Latency (s)':<12} | {'Duration (s)':<13} | {'RTF':<6} | {'Peak VRAM (MB)':<14}")
    print("-" * 75)
    for r in results:
        print(f"{r['label']:<10} | {r['char_count']:<6} | {r['latency_s']:<12.2f} | {r['audio_duration_s']:<13.2f} | {r['rtf']:<6.2f} | {r['peak_vram_mb']:<14.1f}")
    print("=" * 60)

    avg_rtf = sum(r["rtf"] for r in results) / len(results)
    avg_latency = sum(r["latency_s"] for r in results) / len(results)
    print(f"Average Latency: {avg_latency:.2f}s")
    print(f"Average RTF:     {avg_rtf:.2f} (values < 1.0 mean faster than real-time)")
    print("=" * 60)
    print("All generated WAV audio samples verified and saved in outputs/ directory.")


if __name__ == "__main__":
    run_benchmark()
