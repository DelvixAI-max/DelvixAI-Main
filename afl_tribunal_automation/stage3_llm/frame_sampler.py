"""Extract representative frames from a clip and base64-encode them for
Claude's vision input.

Density matters more than coverage: a late bump after a kick and an
ordinary tackle look the same at one frame per second (VAFA Q3 2:21 was
flagged #2 by the detector and then wrongly dismissed at review for exactly
that reason). So the sample is two-tier: a dense burst (4 fps) across the
~3 s around the clip's peak moment, plus a few wide context frames across
the whole clip so the model can see the build-up and aftermath.
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path

from common.ffmpeg_utils import extract_frames_evenly


def _encode(paths: list[str]) -> list[str]:
    return [base64.b64encode(Path(p).read_bytes()).decode("ascii") for p in paths]


def sample_frames_base64(
    video_path: str,
    start_seconds: float,
    end_seconds: float,
    frame_count: int = 8,
    focus_center_seconds: float | None = None,
    focus_span_seconds: float = 3.0,
    focus_frame_count: int = 12,
) -> list[str]:
    """Return base64-encoded JPEG frames in time order.

    Without `focus_center_seconds`: `frame_count` frames evenly through the
    window. With it: `frame_count` context frames across the whole window
    plus `focus_frame_count` frames packed into the `focus_span_seconds`
    around the focus point (~4 fps for the defaults).
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        context = extract_frames_evenly(video_path, start_seconds, end_seconds, frame_count, f"{tmp_dir}/ctx")
        if focus_center_seconds is None:
            return _encode(context)

        half = focus_span_seconds / 2
        f_start = max(start_seconds, focus_center_seconds - half)
        f_end = min(end_seconds, focus_center_seconds + half)
        focus = extract_frames_evenly(video_path, f_start, f_end, focus_frame_count, f"{tmp_dir}/focus")

        # Merge in time order so the sequence reads naturally to the model
        step = (end_seconds - start_seconds) / max(frame_count, 1)
        timed = [(start_seconds + i * step, p) for i, p in enumerate(context)]
        f_step = (f_end - f_start) / max(focus_frame_count, 1)
        timed += [(f_start + i * f_step, p) for i, p in enumerate(focus)]
        timed.sort(key=lambda x: x[0])
        return _encode([p for _, p in timed])
