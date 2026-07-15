"""Command-line entrypoints for every stage.

    python cli.py sync-clock --game-id 1
    python cli.py detect-candidates --game-id 1
    python cli.py extract-clips --game-id 1
    python cli.py rank-candidates --game-id 1
    python cli.py run-game --game-id 1
    python cli.py serve-webhook [--host 0.0.0.0] [--port 8000]
    python cli.py ingest-umpire-report --json-file report.json
"""

from __future__ import annotations

import argparse
import json
import sys

from db.models import Candidate, Clip, SessionLocal


def cmd_sync_clock(args: argparse.Namespace) -> None:
    from stage0_ingestion.ingest import sync_game_clock

    tables = sync_game_clock(args.game_id)
    for quarter, table in sorted(tables.items()):
        print(f"Q{quarter}: {len(table.segments)} clock segments")


def cmd_detect_candidates(args: argparse.Namespace) -> None:
    from orchestrator.game_pipeline import run_candidate_detection

    candidates = run_candidate_detection(args.game_id)
    print(f"{len(candidates)} candidates detected for game {args.game_id}")
    for c in sorted(candidates, key=lambda c: c.score, reverse=True)[:20]:
        print(f"  Q{c.quarter} [{c.broadcast_start_seconds:.1f}-{c.broadcast_end_seconds:.1f}s] score={c.score:.2f}")


def cmd_extract_clips(args: argparse.Namespace) -> None:
    from orchestrator.game_pipeline import run_clip_extraction

    session = SessionLocal()
    try:
        candidates = (
            session.query(Candidate)
            .filter(Candidate.game_id == args.game_id)
            .filter(~Candidate.clips.any())
            .all()
        )
    finally:
        session.close()

    clip_ids = run_clip_extraction(candidates)
    print(f"Extracted {len(clip_ids)} clips for game {args.game_id}")


def cmd_rank_candidates(args: argparse.Namespace) -> None:
    from orchestrator.game_pipeline import run_llm_ranking

    session = SessionLocal()
    try:
        clips = (
            session.query(Clip)
            .filter(Clip.game_id == args.game_id, Clip.candidate_id.isnot(None))
            .filter(~Clip.llm_assessments.any())
            .all()
        )
        candidate_to_clip = {clip.candidate_id: clip.id for clip in clips}
    finally:
        session.close()

    assessments = run_llm_ranking(candidate_to_clip)
    for a in assessments:
        flag = "REVIEW" if a.needs_human_review else "auto-clear"
        print(f"  [{flag}] {a.offence_category} (confidence={a.confidence:.2f}) — {a.rationale[:100]}")


def cmd_run_game(args: argparse.Namespace) -> None:
    from orchestrator.game_pipeline import run_full_pipeline

    ranked = run_full_pipeline(args.game_id)
    print(f"\n{len(ranked)} ranked candidate clips for game {args.game_id}:\n")
    for r in ranked:
        flag = "REVIEW" if r.needs_human_review else "auto-clear"
        clock = f"{r.game_clock}s" if r.game_clock is not None else "?"
        print(
            f"[{flag}] Q{r.quarter} @ {clock} — {r.offence_category} "
            f"(confidence={r.confidence:.2f}, heuristic={r.heuristic_score:.2f})\n"
            f"  {r.clip_url}\n  {r.rationale}\n"
        )

    if args.output_json:
        with open(args.output_json, "w") as f:
            json.dump([r.__dict__ for r in ranked], f, indent=2)
        print(f"Wrote {args.output_json}")


def cmd_serve_webhook(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("stage4_routing.webhook_app:app", host=args.host, port=args.port)


def cmd_ingest_umpire_report(args: argparse.Namespace) -> None:
    from stage4_routing.schemas import IncomingUmpireReport
    from stage4_routing.umpire_ingest import process_incoming_report

    with open(args.json_file) as f:
        payload = IncomingUmpireReport.model_validate(json.load(f))

    report = process_incoming_report(payload)
    print(f"Umpire report {report.id}: status={report.status.value}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser("sync-clock", help="Stage 0: build clock sync table for a game")
    p.add_argument("--game-id", type=int, required=True)
    p.set_defaults(func=cmd_sync_clock)

    p = subparsers.add_parser("detect-candidates", help="Stage 1: detect candidate incident windows")
    p.add_argument("--game-id", type=int, required=True)
    p.set_defaults(func=cmd_detect_candidates)

    p = subparsers.add_parser("extract-clips", help="Stage 2: cut clips for candidates without one yet")
    p.add_argument("--game-id", type=int, required=True)
    p.set_defaults(func=cmd_extract_clips)

    p = subparsers.add_parser("rank-candidates", help="Stage 3: run Claude assessment on unranked clips")
    p.add_argument("--game-id", type=int, required=True)
    p.set_defaults(func=cmd_rank_candidates)

    p = subparsers.add_parser("run-game", help="Stages 0-3 end to end for a game")
    p.add_argument("--game-id", type=int, required=True)
    p.add_argument("--output-json", type=str, default=None)
    p.set_defaults(func=cmd_run_game)

    p = subparsers.add_parser("serve-webhook", help="Stage 4: serve the umpire-report intake webhook")
    p.add_argument("--host", type=str, default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve_webhook)

    p = subparsers.add_parser("ingest-umpire-report", help="Stage 4: process one umpire report from a JSON file")
    p.add_argument("--json-file", type=str, required=True)
    p.set_defaults(func=cmd_ingest_umpire_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
