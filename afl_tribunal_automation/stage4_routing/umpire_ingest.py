"""Stage 4: turn an incoming umpire report into a clip in the tribunal
team's hands, with no human in the loop.

Report (game-clock time) -> ClockSyncTable -> broadcast timestamp ->
Stage 2 clip extraction -> Stage 4 notifier.
"""

from __future__ import annotations

from db.models import Game, SessionLocal, UmpireReport, UmpireReportStatus
from stage0_ingestion.ingest import load_clock_sync_table
from stage2_clips.extractor import extract_clip
from stage4_routing.notifier import send_clip_to_tribunal
from stage4_routing.schemas import IncomingUmpireReport


def _mark_status(report_id: int, status: UmpireReportStatus) -> None:
    session = SessionLocal()
    try:
        report = session.get(UmpireReport, report_id)
        report.status = status
        session.commit()
    finally:
        session.close()


def process_incoming_report(payload: IncomingUmpireReport) -> UmpireReport:
    session = SessionLocal()
    try:
        report = UmpireReport(
            game_id=payload.game_id,
            reporting_umpire=payload.reporting_umpire,
            offender_jumper_number=payload.offender_jumper_number,
            offender_team=payload.offender_team,
            victim_jumper_number=payload.victim_jumper_number,
            victim_team=payload.victim_team,
            incident_type=payload.incident_type,
            expected_damage=payload.expected_damage,
            ground_zone=payload.ground_zone,
            quarter=payload.quarter,
            game_clock_seconds=payload.game_clock_seconds,
            raw_payload=payload.model_dump(),
            status=UmpireReportStatus.RECEIVED,
        )
        session.add(report)
        session.commit()
        session.refresh(report)
        report_id = report.id

        game = session.get(Game, payload.game_id)
        video_path = game.broadcast_video_paths[str(payload.quarter)]
    finally:
        session.close()

    try:
        clock_sync = load_clock_sync_table(payload.game_id, payload.quarter)
        broadcast_seconds = clock_sync.game_to_broadcast(payload.game_clock_seconds)
        if broadcast_seconds is None:
            raise ValueError(
                "Could not map game-clock time to a broadcast timestamp — "
                "has stage 0 clock sync run for this quarter?"
            )

        clip = extract_clip(
            game_id=payload.game_id,
            quarter=payload.quarter,
            video_path=video_path,
            broadcast_center_seconds=broadcast_seconds,
            game_clock_seconds=payload.game_clock_seconds,
            umpire_report_id=report_id,
        )
        _mark_status(report_id, UmpireReportStatus.CLIP_READY)

        session = SessionLocal()
        try:
            report = session.get(UmpireReport, report_id)
            send_clip_to_tribunal(report, clip)
        finally:
            session.close()

        _mark_status(report_id, UmpireReportStatus.SENT_TO_TRIBUNAL)
    except Exception:
        _mark_status(report_id, UmpireReportStatus.FAILED)
        raise

    session = SessionLocal()
    try:
        return session.get(UmpireReport, report_id)
    finally:
        session.close()
