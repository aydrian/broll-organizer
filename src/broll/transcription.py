"""
Audio transcription using whisper.cpp (cross-platform).

Supports Metal GPU acceleration on Apple Silicon, CPU-only on Linux/ARM64.
Provides platform-optimized defaults for MacBook Pro M3 and Raspberry Pi 5.

All transcription is local via whisper.cpp - no cloud API calls.
This preserves Fireworks AI quota for vision analysis tasks.
"""
from __future__ import annotations

import json
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from .config import get_default_whisper_model, IS_MACOS_SILICON, WHISPER_CPP_PATH, WHISPER_LANGUAGE

if TYPE_CHECKING:
    pass


def is_whisper_available() -> bool:
    """
    Check if whisper.cpp CLI is installed and available.

    Returns:
        True if whisper-cli is in PATH or WHISPER_CPP_PATH is set.
    """
    # Check explicit path first
    if WHISPER_CPP_PATH and Path(WHISPER_CPP_PATH).exists():
        return True

    # Check PATH
    return shutil.which("whisper-cli") is not None


def get_whisper_cli_path() -> str | None:
    """
    Get the path to the whisper-cli executable.

    Returns:
        Path to whisper-cli or None if not found.
    """
    if WHISPER_CPP_PATH:
        path = Path(WHISPER_CPP_PATH)
        if path.exists():
            return str(path)

    # Search in PATH
    whisper_path = shutil.which("whisper-cli")
    return whisper_path


def extract_audio_to_wav(
    video_path: Path | str,
    output_wav: Path | str,
    sample_rate: int = 16000,
    timeout: int = 120
) -> bool:
    """
    Extract audio track from video to WAV format suitable for whisper.

    Uses FFmpeg to convert to 16kHz mono WAV (whisper's required format).

    Args:
        video_path: Path to the video file
        output_wav: Path for the output WAV file
        sample_rate: Sample rate in Hz (default 16000 for whisper)
        timeout: Maximum seconds to wait for FFmpeg

    Returns:
        True if extraction successful, False otherwise
    """
    cmd = [
        "ffmpeg",
        "-i", str(video_path),
        "-vn",  # No video
        "-acodec", "pcm_s16le",  # 16-bit PCM
        "-ar", str(sample_rate),  # Sample rate
        "-ac", "1",  # Mono
        "-y",  # Overwrite output
        "-loglevel", "warning",  # Reduce noise
        str(output_wav),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except FileNotFoundError:
        # FFmpeg not installed
        return False


def transcribe_audio(
    audio_path: Path | str,
    model: str | None = None,
    language: str | None = None,
    use_gpu: bool | None = None,
    timeout: int = 600,
) -> dict | None:
    """
    Transcribe audio using whisper.cpp CLI.

    Args:
        audio_path: Path to audio file (WAV recommended)
        model: Model size (tiny, base, small, medium, large).
               Defaults to platform-optimized model.
        language: Language code (e.g., "en", "ja") or "auto" for auto-detect.
                  Defaults to config WHISPER_LANGUAGE.
        use_gpu: Force GPU usage (None = auto-detect for platform)
        timeout: Maximum seconds to wait for transcription

    Returns:
        Dict with transcription data or None on failure.
        Structure: {"transcription": [{"text": "...", "timestamp": [...]}, ...]}
    """
    whisper_path = get_whisper_cli_path()
    if not whisper_path:
        return None

    # Use platform-optimized defaults
    model = model or get_default_whisper_model()
    language = language or WHISPER_LANGUAGE

    # Auto-detect GPU for Apple Silicon
    if use_gpu is None:
        use_gpu = IS_MACOS_SILICON

    # Build command
    cmd = [
        whisper_path,
        "--model", model,
        "--output-json",
        "--file", str(audio_path),
    ]

    # Add language (skip if auto)
    if language and language != "auto":
        cmd.extend(["--language", language])

    # Add Metal GPU flag for Apple Silicon
    if use_gpu and IS_MACOS_SILICON:
        cmd.append("--gpu")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            # Check for common errors
            stderr = result.stderr.lower()
            if "model" in stderr and "not found" in stderr:
                raise RuntimeError(
                    f"Whisper model '{model}' not found. "
                    f"Download with: whisper-cli --model {model} --download-model"
                )
            return None

        # Parse JSON output
        return json.loads(result.stdout)

    except subprocess.TimeoutExpired:
        return None
    except json.JSONDecodeError:
        return None
    except FileNotFoundError:
        # whisper-cli not found
        return None


def extract_transcript_text(transcript_json: dict | None) -> str:
    """
    Extract plain text from whisper.cpp JSON output.

    Args:
        transcript_json: Output from transcribe_audio()

    Returns:
        Concatenated transcript text or empty string if None.
    """
    if not transcript_json:
        return ""

    segments = transcript_json.get("transcription", [])
    texts = []

    for segment in segments:
        text = segment.get("text", "").strip()
        if text:
            texts.append(text)

    return " ".join(texts)


def transcribe_video(
    video_path: Path | str,
    model: str | None = None,
    language: str | None = None,
    keep_audio: bool = False,
    audio_output_path: Path | str | None = None,
) -> dict | None:
    """
    Extract audio from video and transcribe in one step.

    This is the main entry point for transcription. It:
    1. Extracts audio to a temporary WAV file
    2. Runs whisper.cpp transcription
    3. Cleans up the temporary file (unless keep_audio=True)

    Args:
        video_path: Path to the video file
        model: Whisper model size (auto-detects platform-optimal if None)
        language: Language code or "auto" (default from config)
        keep_audio: If True, don't delete the extracted audio file
        audio_output_path: If set, save audio to this path (implies keep_audio=True)

    Returns:
        Dict with:
            - transcript: Full text string
            - raw: Full whisper JSON output
            - model: Model used
            - duration_seconds: Estimated duration (from segments)
        Or None on failure.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        return None

    # Create temporary audio file if no output path specified
    if audio_output_path:
        audio_path = Path(audio_output_path)
        keep_audio = True
    else:
        audio_fd, audio_path_str = tempfile.mkstemp(suffix=".wav")
        audio_path = Path(audio_path_str)

    try:
        # Step 1: Extract audio
        success = extract_audio_to_wav(video_path, audio_path)
        if not success:
            return None

        # Step 2: Transcribe
        transcript_json = transcribe_audio(
            audio_path,
            model=model,
            language=language,
        )

        if not transcript_json:
            return None

        # Step 3: Extract text
        transcript_text = extract_transcript_text(transcript_json)

        # Calculate duration from segments if available
        duration = 0.0
        segments = transcript_json.get("transcription", [])
        if segments:
            last_segment = segments[-1]
            timestamps = last_segment.get("timestamp", [])
            if len(timestamps) >= 2:
                # timestamps are [start, end] in seconds
                duration = timestamps[1]

        return {
            "transcript": transcript_text,
            "raw": transcript_json,
            "model": model or get_default_whisper_model(),
            "duration_seconds": duration,
        }

    finally:
        # Cleanup temporary file unless keeping
        if not keep_audio and audio_path.exists():
            try:
                audio_path.unlink()
            except OSError:
                pass


async def transcribe_video_async(
    video_path: Path | str,
    model: str | None = None,
    language: str | None = None,
) -> dict | None:
    """
    Async wrapper for transcribe_video using asyncio.to_thread.

    Args:
        video_path: Path to the video file
        model: Whisper model size
        language: Language code or "auto"

    Returns:
        Same as transcribe_video()
    """
    import asyncio

    return await asyncio.to_thread(
        transcribe_video,
        video_path,
        model=model,
        language=language,
    )


def get_transcription_info() -> dict:
    """
    Get information about transcription capabilities and configuration.

    Returns:
        Dict with:
            - available: Whether whisper.cpp is installed
            - whisper_path: Path to whisper-cli or None
            - default_model: Platform-optimized default model
            - platform_type: Detected platform type
            - macos_metal: Whether Metal GPU is available
    """
    whisper_path = get_whisper_cli_path()

    return {
        "available": is_whisper_available(),
        "whisper_path": whisper_path,
        "default_model": get_default_whisper_model(),
        "platform_type": platform.system() + " " + platform.machine(),
        "macos_metal": IS_MACOS_SILICON,
    }
