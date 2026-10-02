"""Pose-based "sudden impact" signal via YOLOv8-pose (+ ByteTrack).

Tracks every player's torso centre (midpoint of shoulders and hips) across
sampled frames and flags sudden changes in its velocity — a cheap proxy for
a player being collected at speed, falling, or snapping backwards, all of
which are suggestive of a reportable-act moment worth a human/LLM look.

Runs on the whole frame, so it needs no per-player crops and no dependency
on the detection tracker's output.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from common.time_utils import windows
from stage1_candidates.tracking import video_fps

_pose_model = None

# COCO keypoint indices used by YOLO-pose
_L_SHOULDER, _R_SHOULDER, _L_HIP, _R_HIP = 5, 6, 11, 12


def _get_pose_model(weights: str = "yolov8n-pose.pt"):
    global _pose_model
    if _pose_model is None:
        from ultralytics import YOLO

        _pose_model = YOLO(weights)
    return _pose_model


def _torso_center(kpts_xy: np.ndarray, kpts_conf: np.ndarray | None, min_conf: float = 0.3) -> np.ndarray | None:
    idx = [_L_SHOULDER, _R_SHOULDER, _L_HIP, _R_HIP]
    pts = kpts_xy[idx]
    if kpts_conf is not None:
        ok = kpts_conf[idx] >= min_conf
        if ok.sum() < 2:
            return None
        pts = pts[ok]
    return pts.mean(axis=0)


def compute_pose_scores(
    video_path: str,
    window_seconds: float = 2.0,
    duration_seconds: float | None = None,
    sample_fps: float = 5.0,
    weights: str = "yolov8n-pose.pt",
) -> dict[tuple[float, float], float]:
    """Return {(window_start, window_end): max_torso_acceleration_in_window}.

    Per tracked player: torso-centre displacement between consecutive
    samples (velocity, px/s), then the change in that velocity
    (acceleration). A spike = a sudden deceleration/fall/hit. Raw magnitudes,
    not yet normalized — `scoring.py` normalizes across the game.
    """
    model = _get_pose_model(weights)
    fps = video_fps(video_path)
    stride = max(1, int(round(fps / sample_fps)))

    results = model.track(
        source=video_path,
        tracker="bytetrack.yaml",
        stream=True,
        verbose=False,
        vid_stride=stride,
        imgsz=640,
    )

    # track_id -> list of (timestamp, torso_center)
    track_history: dict[int, list[tuple[float, np.ndarray]]] = defaultdict(list)
    last_timestamp = 0.0

    for sample_idx, result in enumerate(results):
        timestamp = sample_idx * stride / fps
        last_timestamp = timestamp
        boxes, kpts = result.boxes, result.keypoints
        if boxes is None or boxes.id is None or kpts is None:
            continue
        ids = boxes.id.int().tolist()
        xy = kpts.xy.cpu().numpy()
        conf = kpts.conf.cpu().numpy() if kpts.conf is not None else None
        for i, track_id in enumerate(ids):
            center = _torso_center(xy[i], conf[i] if conf is not None else None)
            if center is not None:
                track_history[track_id].append((timestamp, center))

    # Per-track acceleration events: (timestamp, acceleration_magnitude)
    accel_events: list[tuple[float, float]] = []
    for history in track_history.values():
        history.sort(key=lambda h: h[0])
        velocities = []
        for (t0, c0), (t1, c1) in zip(history, history[1:]):
            dt = t1 - t0
            if dt <= 0 or dt > 3 * stride / fps:  # skip gaps where the track was lost
                continue
            velocities.append((t1, (c1 - c0) / dt))
        for (t0, v0), (t1, v1) in zip(velocities, velocities[1:]):
            dt = t1 - t0
            if dt <= 0:
                continue
            accel_events.append((t1, float(np.linalg.norm((v1 - v0) / dt))))

    if duration_seconds is None:
        duration_seconds = last_timestamp

    scores: dict[tuple[float, float], float] = {}
    for start, end in windows(duration_seconds, window_seconds):
        values = [a for ts, a in accel_events if start <= ts < end]
        scores[(start, end)] = max(values) if values else 0.0
    return scores
