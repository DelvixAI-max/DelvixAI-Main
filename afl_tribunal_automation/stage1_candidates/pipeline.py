"""Stage 1 entrypoint: run candidate detection for one quarter (broadcast or
coaches'-angle feed) and persist the resulting CandidateWindows as Candidate
rows."""

from __future__ import annotations

from common.ffmpeg_utils import probe_duration_seconds
from config import settings
from db.models import Candidate, ClipSource, SessionLocal
from stage0_ingestion.clock_sync import ClockSyncTable
from stage1_candidates.motion import compute_motion_scores
from stage1_candidates.pose import compute_pose_scores
from stage1_candidates.scoring import CandidateWindow, score_windows, threshold_and_merge
from stage1_candidates.tracking import compute_density_scores, track_players


def detect_candidates_for_video(
    video_path: str,
    window_seconds: float | None = None,
) -> list[CandidateWindow]:
    """Run the full stage-1 heuristic pipeline over a single quarter video
    and return the merged, thresholded candidate windows."""
    window_seconds = window_seconds or settings.candidate_window_seconds
    duration = probe_duration_seconds(video_path)

    frame_tracks = track_players(video_path)

    motion_scores = compute_motion_scores(video_path, window_seconds=window_seconds, duration_seconds=duration)
    density_scores = compute_density_scores(
        video_path, frame_tracks, window_seconds=window_seconds, duration_seconds=duration
    )
    pose_scores = compute_pose_scores(video_path, window_seconds=window_seconds, duration_seconds=duration)

    windows = score_windows(motion_scores, density_scores, pose_scores)
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
            )
            session.add(row)
            rows.append(row)

        session.commit()
        for row in rows:
            session.refresh(row)
        return rows
    finally:
        session.close()
