"""Stitch the ranked candidate clips into one condensed "review reel" the
analyst can watch start to finish, instead of opening clips one by one.

Each clip gets a caption burned in (quarter, game clock, offence category,
confidence) so the analyst always knows where in the match they are, and a
short title card at the start of the reel says how many clips it holds.
"""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from common.time_utils import format_clock_string


@dataclass
class ReelEntry:
    clip_path: str  # local path or http(s) URL ffmpeg can read
    quarter: int
    game_clock_seconds: int | None
    label: str  # e.g. "rough_conduct 0.82" or "UMPIRE REPORT: striking"


def _caption(entry: ReelEntry) -> str:
    clock = format_clock_string(entry.game_clock_seconds) if entry.game_clock_seconds is not None else "--:--"
    text = f"Q{entry.quarter} {clock}  {entry.label}"
    # drawtext treats these as special characters
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _render_captioned(entry: ReelEntry, output_path: str) -> None:
    drawtext = (
        f"drawtext=text='{_caption(entry)}':fontcolor=white:fontsize=28:"
        "box=1:boxcolor=black@0.6:boxborderw=8:x=20:y=h-th-20"
    )
    cmd = [
        "ffmpeg", "-y", "-i", entry.clip_path,
        "-vf", drawtext,
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "48000", "-ac", "2",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def build_review_reel(entries: list[ReelEntry], output_path: str) -> str:
    """Concatenate `entries` (in the order given — pass them ranked) into a
    single mp4 with per-clip captions. Returns output_path."""
    if not entries:
        raise ValueError("No clips to build a reel from")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        parts = []
        for i, entry in enumerate(entries):
            part = str(Path(tmp) / f"part_{i:03d}.mp4")
            _render_captioned(entry, part)
            parts.append(part)

        concat_list = Path(tmp) / "concat.txt"
        concat_list.write_text("".join(f"file '{p}'\n" for p in parts))
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy", output_path,
        ]
        subprocess.run(cmd, capture_output=True, check=True)
    return output_path
