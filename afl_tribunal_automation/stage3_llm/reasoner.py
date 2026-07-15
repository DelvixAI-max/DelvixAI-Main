"""Stage 3: ask Claude to reason about a candidate clip against the AFL
reportable-offence categories, and return structured JSON — this is the
layer that turns a pile of motion-triggered clips into a ranked, annotated
shortlist for the league's review officer."""

from __future__ import annotations

from pathlib import Path

from common.time_utils import format_clock_string
from config import settings
from db.models import Candidate, Clip, LLMAssessment, SessionLocal
from stage3_llm.frame_sampler import sample_frames_base64
from stage3_llm.schemas import OFFENCE_ASSESSMENT_TOOL_SCHEMA, OffenceAssessment

_RULES_TEXT = (Path(__file__).parent / "rules.md").read_text()

_SYSTEM_PROMPT = f"""You are assisting an AFL league's match review officer by triaging \
candidate incident clips flagged by an automated motion/player-density heuristic. \
The heuristic is deliberately high-recall and low-precision, so most clips you see \
will NOT contain a genuine reportable act — your job is to filter and rank, not to \
assume every clip is an incident.

{_RULES_TEXT}

You will be shown a short sequence of frames sampled through the candidate window. \
Call the `record_offence_assessment` tool exactly once with your assessment."""


def _client():
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def assess_clip(
    video_path: str,
    start_seconds: float,
    end_seconds: float,
    context: dict | None = None,
    frame_count: int = 8,
) -> OffenceAssessment:
    """Sample frames from the clip window and ask Claude for a structured
    OffenceAssessment. `context` is free-form metadata (game, quarter,
    game-clock time, heuristic scores) included as text alongside the frames."""
    frames_b64 = sample_frames_base64(video_path, start_seconds, end_seconds, frame_count)

    context = context or {}
    context_lines = [f"- {key}: {value}" for key, value in context.items()]
    context_text = "Candidate metadata:\n" + "\n".join(context_lines) if context_lines else ""

    content: list[dict] = []
    for b64 in frames_b64:
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}})
    content.append({"type": "text", "text": context_text or "No additional metadata available."})

    client = _client()
    response = client.messages.create(
        model=settings.claude_model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        tools=[OFFENCE_ASSESSMENT_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": "record_offence_assessment"},
        messages=[{"role": "user", "content": content}],
    )

    tool_use = next(block for block in response.content if block.type == "tool_use")
    return OffenceAssessment.model_validate(tool_use.input)


def assess_and_persist(candidate_id: int, clip_id: int) -> LLMAssessment:
    """Look up the Candidate/Clip, run assess_clip, and persist an
    LLMAssessment row."""
    session = SessionLocal()
    try:
        candidate = session.get(Candidate, candidate_id)
        clip = session.get(Clip, clip_id)
        if candidate is None or clip is None:
            raise ValueError(f"Candidate/Clip not found: candidate_id={candidate_id}, clip_id={clip_id}")

        context = {
            "quarter": candidate.quarter,
            "game_clock": format_clock_string(candidate.game_clock_seconds) if candidate.game_clock_seconds else "unknown",
            "heuristic_score": round(candidate.score, 3),
            "motion_score": round(candidate.motion_score, 3),
            "player_density_score": round(candidate.density_score, 3),
            "pose_score": round(candidate.pose_score, 3),
            "source": candidate.source.value,
        }

        # ffmpeg reads http(s) URLs natively, so this works as long as
        # S3_PUBLIC_BASE_URL points at something ffmpeg can stream from
        # (a public/presigned URL, or local MinIO). For a private bucket
        # with no public URL, swap this for a download-to-tempfile step.
        assessment = assess_clip(
            video_path=clip.url,
            start_seconds=0.0,
            end_seconds=clip.broadcast_end_seconds - clip.broadcast_start_seconds,
            context=context,
        )

        row = LLMAssessment(
            candidate_id=candidate_id,
            clip_id=clip_id,
            offence_category=assessment.offence_category,
            confidence=assessment.confidence,
            rationale=assessment.rationale,
            players_involved=[p.model_dump() for p in assessment.players_involved],
            needs_human_review=assessment.needs_human_review,
            raw_response=assessment.model_dump(),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row
    finally:
        session.close()
