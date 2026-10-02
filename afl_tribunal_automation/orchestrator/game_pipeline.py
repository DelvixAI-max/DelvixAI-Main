"""Stitches stages 0-3 together for a whole game: sync clocks, detect
candidates across all quarters (and the coaches'-angle feed if present),
cut clips, and rank with Claude — producing the shortlist the league's
review officer actually looks at."""

from __future__ import annotations

from dataclasses import dataclass

from db.models import Candidate, ClipSource, Game, LLMAssessment, SessionLocal
from stage0_ingestion.ingest import sync_game_clock
from stage1_candidates.pipeline import detect_and_persist_candidates
from stage2_clips.extractor import extract_clip_for_candidate
from stage3_llm.reasoner import assess_and_persist


@dataclass
class RankedClip:
    candidate_id: int
    clip_url: str
    quarter: int
    game_clock: int | None
    heuristic_score: float
    offence_category: str
    confidence: float
    needs_human_review: bool
    rationale: str


def run_candidate_detection(game_id: int) -> list[Candidate]:
    """Stage 0 + 1: sync clocks, then detect candidates for every quarter
    of both the broadcast feed and (if present) the coaches'-angle feed."""
    clock_tables = sync_game_clock(game_id)

    session = SessionLocal()
    try:
        game = session.get(Game, game_id)
        broadcast_paths = dict(game.broadcast_video_paths)
        coaches_paths = dict(game.coaches_angle_video_paths)
    finally:
        session.close()

    all_candidates: list[Candidate] = []
    for quarter_str, video_path in sorted(broadcast_paths.items()):
        quarter = int(quarter_str)
        candidates = detect_and_persist_candidates(
            game_id, quarter, video_path, clock_sync=clock_tables.get(quarter), source=ClipSource.BROADCAST
        )
        all_candidates.extend(candidates)

    for quarter_str, video_path in sorted(coaches_paths.items()):
        quarter = int(quarter_str)
        candidates = detect_and_persist_candidates(
            game_id, quarter, video_path, clock_sync=clock_tables.get(quarter), source=ClipSource.COACHES_ANGLE
        )
        all_candidates.extend(candidates)

    return all_candidates


def run_clip_extraction(candidates: list[Candidate]) -> dict[int, int]:
    """Stage 2: cut a clip for each candidate. Returns {candidate_id: clip_id}."""
    clip_ids: dict[int, int] = {}
    for candidate in candidates:
        clip = extract_clip_for_candidate(candidate.id)
        clip_ids[candidate.id] = clip.id
    return clip_ids


def run_llm_ranking(candidate_to_clip: dict[int, int]) -> list[LLMAssessment]:
    """Stage 3: assess every clip with Claude."""
    return [assess_and_persist(candidate_id, clip_id) for candidate_id, clip_id in candidate_to_clip.items()]


def run_full_pipeline(game_id: int) -> list[RankedClip]:
    """Run stages 0-3 end to end for a game and return a ranked shortlist,
    highest-confidence-and-needs-review first."""
    candidates = run_candidate_detection(game_id)
    candidate_to_clip = run_clip_extraction(candidates)
    assessments = run_llm_ranking(candidate_to_clip)

    session = SessionLocal()
    try:
        candidates_by_id = {c.id: session.get(Candidate, c.id) for c in candidates}
        ranked = []
        for assessment in assessments:
            candidate = candidates_by_id[assessment.candidate_id]
            clip = next(c for c in candidate.clips if c.id == assessment.clip_id)
            ranked.append(
                RankedClip(
                    candidate_id=candidate.id,
                    clip_url=clip.url,
                    quarter=candidate.quarter,
                    game_clock=candidate.game_clock_seconds,
                    heuristic_score=candidate.score,
                    offence_category=assessment.offence_category,
                    confidence=assessment.confidence,
                    needs_human_review=assessment.needs_human_review,
                    rationale=assessment.rationale,
                )
            )
    finally:
        session.close()

    ranked.sort(key=lambda r: (r.needs_human_review, r.confidence), reverse=True)
    return ranked


def build_game_review_reel(
    game_id: int,
    ranked: list[RankedClip],
    output_path: str,
    min_confidence: float = 0.0,
) -> str:
    """Build the condensed review video for the analyst.

    Order: umpire-reported incidents first (they're certain to need a look),
    then the LLM-ranked candidates, best first. `min_confidence` drops
    low-confidence candidates that Claude also cleared (needs_human_review
    False) to keep the reel tight.
    """
    from db.models import Clip, UmpireReport
    from stage2_clips.review_reel import ReelEntry, build_review_reel

    entries: list[ReelEntry] = []

    session = SessionLocal()
    try:
        reported = (
            session.query(Clip, UmpireReport)
            .join(UmpireReport, Clip.umpire_report_id == UmpireReport.id)
            .filter(Clip.game_id == game_id)
            .order_by(UmpireReport.quarter, UmpireReport.game_clock_seconds)
            .all()
        )
        for clip, report in reported:
            entries.append(
                ReelEntry(
                    clip_path=clip.url,
                    quarter=clip.quarter,
                    game_clock_seconds=clip.game_clock_seconds,
                    label=f"UMPIRE REPORT {report.incident_type} #{report.offender_jumper_number}",
                )
            )
    finally:
        session.close()

    for r in ranked:
        if not r.needs_human_review and r.confidence < min_confidence:
            continue
        entries.append(
            ReelEntry(
                clip_path=r.clip_url,
                quarter=r.quarter,
                game_clock_seconds=r.game_clock,
                label=f"{r.offence_category} {r.confidence:.2f}",
            )
        )

    return build_review_reel(entries, output_path)
