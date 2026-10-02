"""Crowd-reaction signal from the recording's audio track.

A crowd reacts to an incident whether or not the camera happens to be
pointing at it, so this is the one signal that can flag an off-the-ball
moment the visual signals can't see.

What's measured is a *sudden rise* in loudness relative to the preceding
few seconds, not absolute loudness — sustained crowd noise (end of a
quarter, a long passage near the fence) shouldn't register, a sharp
collective "ooh" should. Goals and big marks will register too; stage 3
sorts those out.
"""

from __future__ import annotations

import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from common.time_utils import windows

_SAMPLE_RATE = 16000


def _extract_mono_wav(video_path: str, wav_path: str) -> None:
    cmd = [
        "ffmpeg", "-nostdin", "-v", "error", "-y", "-i", video_path,
        "-vn", "-ac", "1", "-ar", str(_SAMPLE_RATE), "-f", "wav", wav_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def loudness_per_second(video_path: str) -> np.ndarray:
    """RMS loudness (dBFS) for every second of the audio track."""
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = str(Path(tmp) / "audio.wav")
        _extract_mono_wav(video_path, wav_path)
        with wave.open(wav_path, "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            width = wav.getsampwidth()
    dtype = {1: np.int8, 2: np.int16, 4: np.int32}[width]
    samples = np.frombuffer(frames, dtype=dtype).astype(np.float64)
    samples /= float(np.iinfo(dtype).max)

    n_seconds = len(samples) // _SAMPLE_RATE
    if n_seconds == 0:
        return np.zeros(0)
    chunks = samples[: n_seconds * _SAMPLE_RATE].reshape(n_seconds, _SAMPLE_RATE)
    rms = np.sqrt((chunks ** 2).mean(axis=1)) + 1e-9
    return 20 * np.log10(rms)


def crowd_rise_per_second(loudness_db: np.ndarray, baseline_seconds: int = 8) -> np.ndarray:
    """How much louder each second is than the median of the preceding
    `baseline_seconds` (in dB, floored at 0). A sharp collective reaction
    shows up as a few seconds well above the baseline."""
    rise = np.zeros_like(loudness_db)
    for i in range(len(loudness_db)):
        start = max(0, i - baseline_seconds)
        if i - start < 2:
            continue
        baseline = np.median(loudness_db[start:i])
        rise[i] = max(0.0, loudness_db[i] - baseline)
    return rise


def compute_audio_scores(
    video_path: str,
    window_seconds: float = 2.0,
    duration_seconds: float | None = None,
) -> dict[tuple[float, float], float]:
    """Return {(window_start, window_end): max_crowd_rise_db_in_window}.

    Raw dB values, not yet normalized — `scoring.py` normalizes across the game.
    """
    loudness = loudness_per_second(video_path)
    rise = crowd_rise_per_second(loudness)
    if duration_seconds is None:
        duration_seconds = float(len(rise))

    scores: dict[tuple[float, float], float] = {}
    for start, end in windows(duration_seconds, window_seconds):
        lo, hi = int(start), min(int(np.ceil(end)), len(rise))
        scores[(start, end)] = float(rise[lo:hi].max()) if hi > lo else 0.0
    return scores
