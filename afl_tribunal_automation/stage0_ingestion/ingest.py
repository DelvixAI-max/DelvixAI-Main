"""Stage 0 entrypoint: build and persist the clock-sync table for every
quarter of a game."""

from __future__ import annotations

from db.models import ClockSyncSegment as ClockSyncSegmentRow
from db.models import Game, SessionLocal
from stage0_ingestion.clock_ocr import read_clock_track
from stage0_ingestion.clock_sync import ClockSyncTable


def sync_game_clock(game_id: int) -> dict[int, ClockSyncTable]:
    """Build a ClockSyncTable per quarter for `game_id`, persist the
    segments, and return {quarter: ClockSyncTable} for immediate use by
    stage 1/2/4 in the same run."""
    session = SessionLocal()
    try:
        game = session.get(Game, game_id)
        if game is None:
            raise ValueError(f"No game with id={game_id}")
        if not game.clock_crop_box:
            raise ValueError(
                f"Game {game_id} has no clock_crop_box configured — "
                "set games.clock_crop_box to the broadcast's on-screen clock region."
            )

        crop_box = (
            game.clock_crop_box["x"],
            game.clock_crop_box["y"],
            game.clock_crop_box["w"],
            game.clock_crop_box["h"],
        )

        # Clear any previous sync for this game so re-runs don't duplicate.
        for existing in list(game.clock_sync_segments):
            session.delete(existing)
        session.flush()

        tables: dict[int, ClockSyncTable] = {}
        for quarter_str, video_path in sorted(game.broadcast_video_paths.items()):
            quarter = int(quarter_str)
            samples = read_clock_track(video_path, crop_box)
            table = ClockSyncTable.from_samples(samples)
            tables[quarter] = table

            for segment in table.segments:
                session.add(
                    ClockSyncSegmentRow(
                        game_id=game_id,
                        quarter=quarter,
                        game_clock_seconds=segment.game_clock_seconds,
                        broadcast_start_seconds=segment.broadcast_start_seconds,
                        broadcast_end_seconds=segment.broadcast_end_seconds,
                    )
                )

        session.commit()
        return tables
    finally:
        session.close()


def load_clock_sync_table(game_id: int, quarter: int) -> ClockSyncTable:
    """Rebuild a ClockSyncTable from persisted segments (no OCR re-run)."""
    from stage0_ingestion.clock_sync import ClockSyncSegment

    session = SessionLocal()
    try:
        rows = (
            session.query(ClockSyncSegmentRow)
            .filter_by(game_id=game_id, quarter=quarter)
            .order_by(ClockSyncSegmentRow.broadcast_start_seconds)
            .all()
        )
        segments = [
            ClockSyncSegment(
                game_clock_seconds=r.game_clock_seconds,
                broadcast_start_seconds=r.broadcast_start_seconds,
                broadcast_end_seconds=r.broadcast_end_seconds,
            )
            for r in rows
        ]
        return ClockSyncTable(segments)
    finally:
        session.close()
