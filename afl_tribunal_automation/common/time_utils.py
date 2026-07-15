"""Pure time-math helpers shared across stages. No I/O, so these are cheap
to unit test without ffmpeg/OpenCV/etc installed."""

from __future__ import annotations

import re

_CLOCK_RE = re.compile(r"^(\d{1,2}):([0-5]\d)$")


def parse_clock_string(text: str) -> int | None:
    """Parse an on-screen 'MM:SS' clock string into total seconds.

    Returns None if the text doesn't look like a plausible AFL quarter clock
    (0-59 minutes, 0-59 seconds) — used to reject OCR garbage.
    """
    match = _CLOCK_RE.match(text.strip())
    if not match:
        return None
    minutes, seconds = int(match.group(1)), int(match.group(2))
    if minutes > 59:
        return None
    return minutes * 60 + seconds


def format_clock_string(total_seconds: int) -> str:
    minutes, seconds = divmod(max(total_seconds, 0), 60)
    return f"{minutes:02d}:{seconds:02d}"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def windows(total_seconds: float, window_seconds: float):
    """Yield (start, end) tuples covering [0, total_seconds) in fixed-size
    windows. Final window is truncated to total_seconds."""
    start = 0.0
    while start < total_seconds:
        end = min(start + window_seconds, total_seconds)
        yield start, end
        start = end
