"""Cheap, CPU-friendly motion-spike scoring via Farneback dense optical flow.

A sudden, spatially-concentrated jump in flow magnitude is a decent proxy for
"a collision happened here" — not proof of anything, just a triage signal
that feeds into `scoring.py` alongside player-density and pose signals.
"""

from __future__ import annotations

import cv2
import numpy as np

from common.time_utils import windows


def compute_motion_scores(
    video_path: str,
    window_seconds: float = 2.0,
    sample_fps: float = 5.0,
    downscale_width: int = 480,
    duration_seconds: float | None = None,
) -> dict[tuple[float, float], float]:
    """Return {(window_start, window_end): raw_motion_magnitude} for the
    whole video. Scores are NOT yet normalized to 0-1 — `scoring.py` does
    that once all signals are computed, so relative magnitude across the
    whole game is preserved.

    Frames are read sequentially (grab + retrieve every Nth frame) rather
    than seeked, which is an order of magnitude faster on long h264 files.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = duration_seconds if duration_seconds is not None else (frame_count / fps if fps else 0.0)
    stride = max(1, int(round(fps / sample_fps)))

    prev_gray = None
    per_sample: list[tuple[float, float]] = []  # (timestamp, magnitude)

    frame_index = 0
    while True:
        if not cap.grab():
            break
        if frame_index % stride == 0:
            ok, frame = cap.retrieve()
            if ok:
                scale = downscale_width / frame.shape[1] if frame.shape[1] > downscale_width else 1.0
                if scale != 1.0:
                    frame = cv2.resize(frame, None, fx=scale, fy=scale)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                if prev_gray is not None:
                    flow = cv2.calcOpticalFlowFarneback(prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                    magnitude = float(np.linalg.norm(flow, axis=2).mean())
                    per_sample.append((frame_index / fps, magnitude))
                prev_gray = gray
        frame_index += 1

    cap.release()

    scores: dict[tuple[float, float], float] = {}
    for start, end in windows(duration, window_seconds):
        values = [m for ts, m in per_sample if start <= ts < end]
        scores[(start, end)] = max(values) if values else 0.0
    return scores
