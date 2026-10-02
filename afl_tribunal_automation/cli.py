"""Command-line entrypoints for every stage.

    python cli.py add-game --season 2026 --round R18 --home-team Richmond --away-team Carlton \\
        --q1 /videos/q1.mp4 --q2 /videos/q2.mp4 --q3 /videos/q3.mp4 --q4 /videos/q4.mp4 \\
        --clock-box 1700,40,160,50
    python cli.py preview-frame --video /videos/q1.mp4 --timestamp 10 --output frame.jpg
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

from db.models import Candidate, Clip, Game, SessionLocal


def cmd_add_game(args: argparse.Namespace) -> None:
    if args.clock_mode == "ocr" and not args.clock_box:
        raise SystemExit("--clock-box is required with --clock-mode ocr (or use --clock-mode linear)")
    clock_box = {}
    if args.clock_box:
        x, y, w, h = (int(v) for v in args.clock_box.split(","))
        clock_box = {"x": x, "y": y, "w": w, "h": h}

    start_offsets = {}
    for item in args.quarter_start_offset or []:
        q, secs = item.split("=")
        start_offsets[q] = float(secs)

    broadcast_paths = {}
    for quarter, path in ((1, args.q1), (2, args.q2), (3, args.q3), (4, args.q4)):
        if path:
            broadcast_paths[str(quarter)] = path

    coaches_paths = {}
    for quarter, path in ((1, args.coaches_q1), (2, args.coaches_q2), (3, args.coaches_q3), (4, args.coaches_q4)):
        if path:
            coaches_paths[str(quarter)] = path

    session = SessionLocal()
    try:
        game = Game(
            season=args.season,
            round=args.round,
            home_team=args.home_team,
            away_team=args.away_team,
            ground=args.ground or "",
            broadcast_video_paths=broadcast_paths,
            coaches_angle_video_paths=coaches_paths,
            clock_mode=args.clock_mode,
            clock_crop_box=clock_box,
            quarter_start_offsets=start_offsets,
        )
        session.add(game)
        session.commit()
        session.refresh(game)
        print(f"Created game {game.id}: {game.home_team} vs {game.away_team} ({len(broadcast_paths)} quarters)")
    finally:
        session.close()


def cmd_preview_frame(args: argparse.Namespace) -> None:
    """Pull a single frame so you can find the clock's crop box (x,y,w,h)
    by eye before running sync-clock — open the frame in any image viewer,
    note the pixel rectangle around the on-screen clock, and pass it as
    --clock-box to add-game."""
    from common.ffmpeg_utils import extract_frame_at

    path = extract_frame_at(args.video, args.timestamp, args.output)
    print(f"Wrote {path} — open it and measure the clock's pixel box (x,y,w,h).")


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

    if args.reel:
        from orchestrator.game_pipeline import build_game_review_reel

        path = build_game_review_reel(args.game_id, ranked, args.reel, min_confidence=args.reel_min_confidence)
        print(f"Review reel written to {path}")


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

    p = subparsers.add_parser("add-game", help="Register a game and its quarter video paths")
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--round", type=str, required=True)
    p.add_argument("--home-team", type=str, required=True)
    p.add_argument("--away-team", type=str, required=True)
    p.add_argument("--ground", type=str, default="")
    p.add_argument("--q1", type=str, default=None)
    p.add_argument("--q2", type=str, default=None)
    p.add_argument("--q3", type=str, default=None)
    p.add_argument("--q4", type=str, default=None)
    p.add_argument("--coaches-q1", type=str, default=None)
    p.add_argument("--coaches-q2", type=str, default=None)
    p.add_argument("--coaches-q3", type=str, default=None)
    p.add_argument("--coaches-q4", type=str, default=None)
    p.add_argument("--clock-mode", choices=["ocr", "linear"], default="ocr",
                   help="ocr: read the on-screen clock; linear: no on-screen clock, use video time minus quarter start")
    p.add_argument("--clock-box", type=str, default=None, help="x,y,w,h pixel crop box for the on-screen clock (ocr mode)")
    p.add_argument("--quarter-start-offset", action="append", metavar="Q=SECONDS",
                   help="linear mode: seconds into the quarter video when play starts, e.g. 1=14.5 (repeatable)")
    p.set_defaults(func=cmd_add_game)

    p = subparsers.add_parser("preview-frame", help="Extract one frame to help find the clock's crop box")
    p.add_argument("--video", type=str, required=True)
    p.add_argument("--timestamp", type=float, required=True)
    p.add_argument("--output", type=str, required=True)
    p.set_defaults(func=cmd_preview_frame)

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
    p.add_argument("--reel", type=str, default=None, help="Write the condensed review video to this path")
    p.add_argument(
        "--reel-min-confidence", type=float, default=0.3,
        help="Drop candidates below this confidence that Claude also cleared (default 0.3)",
    )
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
