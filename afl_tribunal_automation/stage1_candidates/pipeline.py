"""Stage 1 entrypoint: run candidate detection for one quarter (broadcast or
coaches'-angle feed) and persist the resulting CandidateWindows as Candidate
rows."""

from __future__ import annotations

import json
from pathlib import Path

from common.ffmpeg_utils import probe_duration_seconds
from config import settings
from db.models import Candidate, ClipSource, SessionLocal
from stage0_ingestion.clock_sync import ClockSyncTable
from stage1_candidates.audio import compute_audio_scores
from stage1_candidates.motion import compute_motion_scores
from stage1_candidates.pose import compute_pose_signals
from stage1_candidates.scoring import CandidateWindow, score_windows, threshold_and_merge
from stage1_candidates.tracking import compute_density_scores, track_players


SignalMap = dict[tuple[float, float], float]

# Bump whenever a signal extractor changes in a way that alters its output
# (model, resolution, sampling), so stale cached signals aren't reused.
SIGNAL_VERSION = "v3-grounded"


def _signal_cache_path(video_path: str, window_seconds: float) -> Path:
    stat = Path(video_path).stat()
    key = f"{Path(video_path).stem}_{stat.st_size}_{int(stat.st_mtime)}_w{window_seconds:g}_{SIGNAL_VERSION}.json"
    return Path(settings.local_storage_dir) / "signals" / key


def _dump(signal: SignalMap | None) -> list | None:
    return None if signal is None else [[s, e, v] for (s, e), v in signal.items()]


def _load(items: list | None) -> SignalMap | None:
    return None if items is None else {(s, e): v for s, e, v in items}


def compute_signals(video_path: str, window_seconds: float, use_cache: bool = True) -> dict[str, SignalMap | None]:
    """Run the four raw signal extractors (the expensive part — minutes of
    YOLO/pose/flow per quarter) and cache the per-window results, so
    scoring and thresholds can be re-tuned in seconds without re-running
    the models."""
    cache = _signal_cache_path(video_path, window_seconds)
    if use_cache and cache.exists():
        data = json.loads(cache.read_text())
        return {name: _load(data.get(name)) for name in ("motion", "density", "pose", "grounded", "audio")}

    duration = probe_duration_seconds(video_path)
    frame_tracks = track_players(video_path)
    pose_signals = compute_pose_signals(video_path, window_seconds=window_seconds, duration_seconds=duration)
    signals: dict[str, SignalMap | None] = {
        "motion": compute_motion_scores(video_path, window_seconds=window_seconds, duration_seconds=duration),
        "density": compute_density_scores(
            video_path, frame_tracks, window_seconds=window_seconds, duration_seconds=duration
        ),
        "pose": pose_signals["pose"],
        "grounded": pose_signals["grounded"],
    }
    try:
        signals["audio"] = compute_audio_scores(
            video_path, window_seconds=window_seconds, duration_seconds=duration
        )
    except Exception:  # noqa: BLE001 - no/unreadable audio track: score on visuals alone
        signals["audio"] = None

    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({name: _dump(sig) for name, sig in signals.items()}))
    return signals


def detect_candidates_for_video(
    video_path: str,
    window_seconds: float | None = None,
) -> list[CandidateWindow]:
    """Run the full stage-1 heuristic pipeline over a single quarter video
    and return the merged, thresholded candidate windows."""
    window_seconds = window_seconds or settings.candidate_window_seconds
    sig = compute_signals(video_path, window_seconds)
    windows = score_windows(
        sig["motion"], sig["density"], sig["pose"], sig["audio"], grounded_scores=sig.get("grounded")
    )
    return threshold_and_merge(windows)


def detect_and_persist_candidates(
    game_id: int,
    quarter: int,
    video_path: str,
    clock_sync: ClockSyncTable | None = None,
    source: ClipSource = ClipSource.BROADCAST,
) -> list[Candidate]:
    """Run detection for one quarter and persist Candidate rows, tagged with
    the mapped game-clock time if a ClockSyncTable is supplied."""
    candidate_windows = detect_candidates_for_video(video_path)

    session = SessionLocal()
    try:
        rows: list[Candidate] = []
        for window in candidate_windows:
            game_clock = None
            if clock_sync is not None:
                game_clock = clock_sync.broadcast_to_game(window.anchor_seconds)

            row = Candidate(
                game_id=game_id,
                quarter=quarter,
                source=source,
                broadcast_start_seconds=window.start_seconds,
                broadcast_end_seconds=window.end_seconds,
                peak_broadcast_seconds=window.peak_seconds,
                game_clock_seconds=game_clock,
                score=window.score,
                motion_score=window.motion_score,
                density_score=window.density_score,
                pose_score=window.pose_score,
                audio_score=window.audio_score,
                grounded_score=window.grounded_score,
            )
            session.add(row)
            rows.append(row)

        session.commit()
        for row in rows:
            session.refresh(row)
        return rows
    finally:
        session.close()
