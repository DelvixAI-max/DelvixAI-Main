"""Thin wrappers around the ffmpeg/ffprobe CLI. All video I/O funnels
through here so every stage cuts/reads clips the same way."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


def probe_duration_seconds(video_path: str) -> float:
    """Return a video's duration in seconds via ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def cut_clip(
    video_path: str,
    start_seconds: float,
    end_seconds: float,
    output_path: str,
    reencode: bool = True,
) -> str:
    """Cut [start_seconds, end_seconds) out of video_path into output_path.

    reencode=True re-encodes (accurate frame-level cut, slower); False uses
    stream copy (fast, but snaps to the nearest keyframe — fine for rough
    scrubbing, not for a tribunal-ready clip).
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    duration = max(end_seconds - start_seconds, 0.1)

    cmd = ["ffmpeg", "-y", "-ss", f"{start_seconds:.3f}", "-i", video_path, "-t", f"{duration:.3f}"]
    if reencode:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac"]
    else:
        cmd += ["-c", "copy"]
    cmd += [output_path]

    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def extract_frame_at(video_path: str, timestamp_seconds: float, output_path: str) -> str:
    """Extract a single frame at timestamp_seconds as a JPEG."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{timestamp_seconds:.3f}",
        "-i",
        video_path,
        "-frames:v",
        "1",
        "-q:v",
        "2",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    return output_path


def extract_frames_evenly(video_path: str, start_seconds: float, end_seconds: float, count: int, output_dir: str) -> list[str]:
    """Extract `count` frames evenly spaced across [start_seconds, end_seconds]."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    if count < 1:
        return []
    span = max(end_seconds - start_seconds, 0.0)
    step = span / count if count > 1 else 0.0
    paths = []
    for i in range(count):
        ts = start_seconds + i * step
        out = str(Path(output_dir) / f"frame_{i:03d}.jpg")
        extract_frame_at(video_path, ts, out)
        paths.append(out)
    return paths
