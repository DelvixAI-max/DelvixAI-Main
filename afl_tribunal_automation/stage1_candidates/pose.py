"""Pose-based "sudden impact" signal via MediaPipe Pose.

Runs pose estimation on each tracked player's bounding-box crop (from
`tracking.py`) and flags rapid hip/shoulder displacement between consecutive
sampled frames for the same track — a cheap proxy for a player being
collected at speed, falling, or snapping backwards, all of which are
suggestive of a reportable-act moment worth a human/LLM look.
"""

from __future__ import annotations

from collections import defaultdict

import cv2
import numpy as np

from common.time_utils import windows
from stage1_candidates.tracking import FrameTracks

_pose = None


def _get_pose():
    global _pose
    if _pose is None:
        import mediapipe as mp

        _pose = mp.solutions.pose.Pose(static_image_mode=True, model_complexity=0)
    return _pose


# MediaPipe Pose landmark indices for hips/shoulders (midpoint used as torso anchor)
_LEFT_SHOULDER, _RIGHT_SHOULDER = 11, 12
_LEFT_HIP, _RIGHT_HIP = 23, 24


def _torso_center(landmarks) -> np.ndarray | None:
    try:
        pts = [landmarks[i] for i in (_LEFT_SHOULDER, _RIGHT_SHOULDER, _LEFT_HIP, _RIGHT_HIP)]
    except IndexError:
        return None
    return np.array([[p.x, p.y] for p in pts]).mean(axis=0)


def compute_pose_scores(
    video_path: str,
    frame_tracks: list[FrameTracks],
    window_seconds: float = 2.0,
    duration_seconds: float | None = None,
) -> dict[tuple[float, float], float]:
    """Return {(window_start, window_end): max_torso_acceleration_in_window}.

    For each tracked player, computes torso-center displacement between
    consecutive sampled frames (velocity), then the change in that velocity
    (acceleration). A spike in acceleration = a sudden deceleration/fall/hit.
    Raw magnitudes, not yet normalized — `scoring.py` normalizes across the game.
    """
    pose = _get_pose()
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Could not open video: {video_path}")

    # track_id -> list of (timestamp, torso_center)
    track_history: dict[int, list[tuple[float, np.ndarray]]] = defaultdict(list)

    for ft in frame_tracks:
        if not ft.detections:
            continue
        cap.set(cv2.CAP_PROP_POS_MSEC, ft.timestamp * 1000.0)
        ok, frame = cap.read()
        if not ok:
            continue

        for det in ft.detections:
            x1, y1, x2, y2 = [max(0, int(v)) for v in det.bbox_xyxy]
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                continue
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            result = pose.process(rgb)
            if not result.pose_landmarks:
                continue
            center = _torso_center(result.pose_landmarks.landmark)
            if center is not None:
                track_history[det.track_id].append((ft.timestamp, center))

    cap.release()

    # Per-track acceleration events: (timestamp, acceleration_magnitude)
    accel_events: list[tuple[float, float]] = []
    for history in track_history.values():
        history.sort(key=lambda h: h[0])
        velocities = []
        for (t0, c0), (t1, c1) in zip(history, history[1:]):
            dt = max(t1 - t0, 1e-3)
            velocities.append((t1, (c1 - c0) / dt))
        for (t0, v0), (t1, v1) in zip(velocities, velocities[1:]):
            dt = max(t1 - t0, 1e-3)
            accel = np.linalg.norm((v1 - v0) / dt)
            accel_events.append((t1, float(accel)))

    if duration_seconds is None:
        duration_seconds = frame_tracks[-1].timestamp if frame_tracks else 0.0

    scores: dict[tuple[float, float], float] = {}
    for start, end in windows(duration_seconds, window_seconds):
        values = [a for ts, a in accel_events if start <= ts < end]
        scores[(start, end)] = max(values) if values else 0.0
    return scores
