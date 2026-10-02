"""Pose-based signals via YOLOv8-pose (+ ByteTrack), one pass over the video.

Two signals come out of the same model run:

* **pose** — sudden change in a tracked player's torso velocity (a player
  collected at speed, snapping backwards). Dominated in practice by sprinters
  changing direction, so it's a weak incident signal on its own.
* **grounded** — a body lying horizontal for a sustained run of samples.
  Every pack-over-a-downed-player incident in the VAFA test footage shows
  this (several consecutive readings of torso angle 57-89° from vertical),
  while ordinary play only produces isolated single readings just over 55°.
  Requiring a run of >= 2 consecutive samples suppresses that noise.

Runs on the whole frame at native resolution (see tracking.py).
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from common.time_utils import windows
from stage1_candidates.tracking import video_fps

_pose_model = None

# COCO keypoint indices used by YOLO-pose
_L_SHOULDER, _R_SHOULDER, _L_HIP, _R_HIP = 5, 6, 11, 12
_TORSO = [_L_SHOULDER, _R_SHOULDER, _L_HIP, _R_HIP]

HORIZONTAL_DEGREES = 60.0  # torso angle from vertical above which a body counts as lying down
MIN_KEYPOINT_CONF = 0.3


def _get_pose_model(weights: str = "yolov8n-pose.pt"):
    global _pose_model
    if _pose_model is None:
        from ultralytics import YOLO

        _pose_model = YOLO(weights)
    return _pose_model


def torso_angle_from_vertical(kpts_xy: np.ndarray) -> float:
    """Degrees between the shoulder-midpoint -> hip-midpoint vector and the
    image vertical: ~0 for an upright player, ~90 for one lying down."""
    shoulders = kpts_xy[[_L_SHOULDER, _R_SHOULDER]].mean(axis=0)
    hips = kpts_xy[[_L_HIP, _R_HIP]].mean(axis=0)
    v = hips - shoulders
    return float(np.degrees(np.arctan2(abs(v[0]), abs(v[1]) + 1e-6)))


GroundedSample = tuple[float, float, int, int]  # (timestamp, max_torso_angle, n_bodies>55deg, n_bodies>60deg)


def grounded_scores_from_samples(
    samples: list[GroundedSample],
    duration_seconds: float,
    window_seconds: float,
    threshold_degrees: float = HORIZONTAL_DEGREES,
    pad_seconds: float = 0.6,
) -> dict[tuple[float, float], float]:
    """Score each window by how many samples in [start-pad, end+pad) had at
    least one body lying past `threshold_degrees`, minus one so an isolated
    single reading scores 0.

    A count (rather than a run of consecutive samples) survives the flicker
    of a partly-occluded body in a pack dropping in and out of detection,
    and the padding stops an event straddling a window boundary being split
    into two sub-threshold halves.
    """
    idx = 3 if threshold_degrees >= 60 else 2
    scores: dict[tuple[float, float], float] = {}
    for start, end in windows(duration_seconds, window_seconds):
        count = sum(1 for s in samples if start - pad_seconds <= s[0] < end + pad_seconds and s[idx] > 0)
        scores[(start, end)] = float(max(0, count - 1))
    return scores


def grounded_run_scores(
    samples: list[tuple[float, int]],
    duration_seconds: float,
    window_seconds: float,
) -> dict[tuple[float, float], float]:
    """Earlier, stricter aggregation kept for comparison: longest run of
    consecutive samples with a horizontal body, minus one."""
    scores: dict[tuple[float, float], float] = {}
    for start, end in windows(duration_seconds, window_seconds):
        best = run = 0
        for ts, n in samples:
            if ts < start or ts >= end:
                continue
            run = run + 1 if n > 0 else 0
            best = max(best, run)
        scores[(start, end)] = float(max(0, best - 1))
    return scores


def compute_pose_signals(
    video_path: str,
    window_seconds: float = 2.0,
    duration_seconds: float | None = None,
    sample_fps: float = 5.0,
    weights: str = "yolov8n-pose.pt",
) -> dict[str, dict[tuple[float, float], float]]:
    """Return {"pose": {...}, "grounded": {...}}, each keyed by window.

    Raw magnitudes, not yet normalized — `scoring.py` normalizes across the game.
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
        imgsz=1280,  # see tracking.py — 640 misses most players on 720p footage
    )

    # track_id -> list of (timestamp, torso_center) for the acceleration signal
    track_history: dict[int, list[tuple[float, np.ndarray]]] = defaultdict(list)
    # Raw per-sample torso-orientation readings for the grounded signal
    grounded_samples: list[GroundedSample] = []
    last_timestamp = 0.0

    for sample_idx, result in enumerate(results):
        timestamp = sample_idx * stride / fps
        last_timestamp = timestamp
        kpts = result.keypoints
        if kpts is None or kpts.conf is None or len(kpts) == 0:
            grounded_samples.append((timestamp, 0.0, 0, 0))
            continue
        xy = kpts.xy.cpu().numpy()
        conf = kpts.conf.cpu().numpy()
        ids = result.boxes.id.int().tolist() if result.boxes is not None and result.boxes.id is not None else None

        max_angle, n55, n60 = 0.0, 0, 0
        for i in range(len(xy)):
            if conf[i][_TORSO].min() < MIN_KEYPOINT_CONF:
                continue
            angle = torso_angle_from_vertical(xy[i])
            max_angle = max(max_angle, angle)
            n55 += angle > 55.0
            n60 += angle > 60.0
            if ids is not None and i < len(ids):
                center = xy[i][_TORSO].mean(axis=0)
                track_history[ids[i]].append((timestamp, center))
        grounded_samples.append((timestamp, round(max_angle, 1), n55, n60))

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

    pose_scores: dict[tuple[float, float], float] = {}
    for start, end in windows(duration_seconds, window_seconds):
        values = [a for ts, a in accel_events if start <= ts < end]
        pose_scores[(start, end)] = max(values) if values else 0.0

    return {
        "pose": pose_scores,
        "grounded": grounded_scores_from_samples(grounded_samples, duration_seconds, window_seconds),
        "grounded_samples": grounded_samples,  # raw, so aggregation can be re-tuned from cache
    }


def compute_pose_scores(video_path: str, **kwargs) -> dict[tuple[float, float], float]:
    """Backwards-compatible wrapper returning only the acceleration signal."""
    return compute_pose_signals(video_path, **kwargs)["pose"]
