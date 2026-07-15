"""Player detection + tracking via Ultralytics YOLO + ByteTrack.

Gives frame-by-frame player positions, which `scoring.py` turns into a
"player-cluster density" signal (multiple players converging is a decent
proxy for a contest/collision — tackles, hip-and-shoulders, off-the-ball
incidents where several players bunch up).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from common.time_utils import windows

_model = None


def _get_model(weights: str = "yolov8n.pt"):
    global _model
    if _model is None:
        from ultralytics import YOLO

        _model = YOLO(weights)
    return _model


@dataclass
class Detection:
    track_id: int
    bbox_xyxy: tuple[float, float, float, float]


@dataclass
class FrameTracks:
    timestamp: float
    detections: list[Detection]


def track_players(video_path: str, sample_fps: float = 5.0, weights: str = "yolov8n.pt") -> list[FrameTracks]:
    """Run YOLO+ByteTrack over the video, sampled at `sample_fps`, keeping
    only the 'person' class (COCO class 0)."""
    model = _get_model(weights)

    results = model.track(
        source=video_path,
        classes=[0],
        tracker="bytetrack.yaml",
        stream=True,
        verbose=False,
        vid_stride=1,
    )

    frame_tracks: list[FrameTracks] = []
    fps_guess = None
    for frame_idx, result in enumerate(results):
        if fps_guess is None:
            fps_guess = getattr(result, "speed", {}).get("fps", None) or 25.0
        timestamp = frame_idx / fps_guess if fps_guess else float(frame_idx)

        detections: list[Detection] = []
        boxes = result.boxes
        if boxes is not None and boxes.id is not None:
            ids = boxes.id.int().tolist()
            xyxy = boxes.xyxy.tolist()
            for track_id, box in zip(ids, xyxy):
                detections.append(Detection(track_id=track_id, bbox_xyxy=tuple(box)))

        frame_tracks.append(FrameTracks(timestamp=timestamp, detections=detections))

    return frame_tracks


def _centroid(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return (x1 + x2) / 2, (y1 + y2) / 2


def _max_cluster_size(detections: list[Detection], cluster_radius_px: float) -> int:
    """Largest set of players all mutually within cluster_radius_px of at
    least one other player in the set (simple greedy density estimate, not
    a true clustering algorithm — good enough as a triage signal)."""
    if not detections:
        return 0
    points = np.array([_centroid(d.bbox_xyxy) for d in detections])
    best = 1
    for i in range(len(points)):
        dists = np.linalg.norm(points - points[i], axis=1)
        count = int((dists <= cluster_radius_px).sum())
        best = max(best, count)
    return best


def compute_density_scores(
    video_path: str,
    frame_tracks: list[FrameTracks],
    window_seconds: float = 2.0,
    duration_seconds: float | None = None,
    cluster_radius_px: float = 120.0,
) -> dict[tuple[float, float], float]:
    """Return {(window_start, window_end): max_cluster_size_in_window}.

    Raw counts, not yet normalized — `scoring.py` normalizes across the game.
    """
    if duration_seconds is None:
        duration_seconds = frame_tracks[-1].timestamp if frame_tracks else 0.0

    scores: dict[tuple[float, float], float] = {}
    for start, end in windows(duration_seconds, window_seconds):
        in_window = [ft for ft in frame_tracks if start <= ft.timestamp < end]
        max_cluster = max((_max_cluster_size(ft.detections, cluster_radius_px) for ft in in_window), default=0)
        scores[(start, end)] = float(max_cluster)
    return scores
