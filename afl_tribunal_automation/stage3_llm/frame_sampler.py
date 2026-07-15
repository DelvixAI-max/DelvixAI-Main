"""Extract a handful of representative frames from a clip and base64-encode
them for Claude's vision input."""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

from common.ffmpeg_utils import extract_frames_evenly


def sample_frames_base64(
    video_path: str,
    start_seconds: float,
    end_seconds: float,
    frame_count: int = 8,
) -> list[str]:
    """Return base64-encoded JPEG frames, evenly spaced through the window."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        frame_paths = extract_frames_evenly(video_path, start_seconds, end_seconds, frame_count, tmp_dir)
        encoded = []
        for path in frame_paths:
            data = Path(path).read_bytes()
            encoded.append(base64.b64encode(data).decode("ascii"))
        return encoded
