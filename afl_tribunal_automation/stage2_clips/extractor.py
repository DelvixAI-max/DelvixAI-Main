"""Stage 2: cut a buffered clip around a candidate window or a reported
timestamp, upload it, and index it in Postgres."""

from __future__ import annotations

import tempfile
from pathlib import Path

from common.ffmpeg_utils import cut_clip
from common.storage import clip_storage_key, upload_clip
from common.time_utils import clamp
from config import settings
from db.models import Clip, Game, SessionLocal


def extract_clip(
    game_id: int,
    quarter: int,
    video_path: str,
    broadcast_center_seconds: float,
    game_clock_seconds: int | None = None,
    candidate_id: int | None = None,
    umpire_report_id: int | None = None,
    buffer_before: float | None = None,
    buffer_after: float | None = None,
) -> Clip:
    """Cut [-buffer_before, +buffer_after] around broadcast_center_seconds,
    upload to object storage, and persist a Clip row."""
    buffer_before = buffer_before if buffer_before is not None else settings.clip_buffer_before_seconds
    buffer_after = buffer_after if buffer_after is not None else settings.clip_buffer_after_seconds

    start = clamp(broadcast_center_seconds - buffer_before, 0, float("inf"))
    end = broadcast_center_seconds + buffer_after

    with tempfile.TemporaryDirectory() as tmp_dir:
        local_path = str(Path(tmp_dir) / "clip.mp4")
        cut_clip(video_path, start, end, local_path)

        storage_key = clip_storage_key(game_id, quarter, start)
        url = upload_clip(local_path, storage_key)

    session = SessionLocal()
    try:
        clip = Clip(
            game_id=game_id,
            candidate_id=candidate_id,
            umpire_report_id=umpire_report_id,
            quarter=quarter,
            broadcast_start_seconds=start,
            broadcast_end_seconds=end,
            game_clock_seconds=game_clock_seconds,
            storage_key=storage_key,
            url=url,
        )
        session.add(clip)
        session.commit()
        session.refresh(clip)
        return clip
    finally:
        session.close()


def extract_clip_for_candidate(candidate_id: int) -> Clip:
    """Convenience wrapper: look up a Candidate row, resolve its quarter's
    video path from the parent Game, and cut its clip."""
    session = SessionLocal()
    try:
        from db.models import Candidate

        candidate = session.get(Candidate, candidate_id)
        if candidate is None:
            raise ValueError(f"No candidate with id={candidate_id}")

        game = session.get(Game, candidate.game_id)
        video_paths = (
            game.coaches_angle_video_paths
            if candidate.source.value == "coaches_angle"
            else game.broadcast_video_paths
        )
        video_path = video_paths[str(candidate.quarter)]
        midpoint = candidate.peak_broadcast_seconds
        if midpoint is None:
            midpoint = (candidate.broadcast_start_seconds + candidate.broadcast_end_seconds) / 2
    finally:
        session.close()

    return extract_clip(
        game_id=candidate.game_id,
        quarter=candidate.quarter,
        video_path=video_path,
        broadcast_center_seconds=midpoint,
        game_clock_seconds=candidate.game_clock_seconds,
        candidate_id=candidate.id,
    )
