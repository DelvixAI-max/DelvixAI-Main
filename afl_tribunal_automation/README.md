# AFL Umpiring Reporting & Tribunal Automation

Turns raw broadcast footage of an AFL match into two things the match review
process needs on a Saturday-night-to-Tuesday-tribunal turnaround:

1. **Reported-offence auto-routing** — the umpire's on-field report (player,
   victim, incident type, time) is matched against the broadcast clock and a
   clip is cut and sent to the tribunal team automatically.
2. **Candidate detection** — 2.5 hours of footage (4 quarters) is condensed
   into a ranked shortlist (~30-60 clips) of *other* potentially reportable
   incidents for the league's review officer to check, each with an
   AI-generated rationale.

## Architecture (4 stages)

```
Stage 0  Ingestion & clock sync    stage0_ingestion/
Stage 1  Candidate detection       stage1_candidates/
Stage 2  Clip extraction           stage2_clips/
Stage 3  LLM reasoning/re-ranking  stage3_llm/
Stage 4  Reported-offence routing  stage4_routing/
```

Everything is orchestrated by `orchestrator/game_pipeline.py` and driven from
`cli.py`. Shared plumbing (ffmpeg, object storage, time math) lives in
`common/`. Persistent state (games, clock sync, candidates, clips, LLM
assessments, umpire reports) lives in Postgres — see `db/models.py`.

### Stage 0 — Ingestion & clock sync

Each quarter's video is a separate ~30 min file. `stage0_ingestion/clock_ocr.py`
crops the broadcast's fixed on-screen clock region once per second and OCRs it
(EasyOCR by default). `stage0_ingestion/clock_sync.py` turns the raw OCR
samples into a `ClockSyncTable`: a monotonic, stoppage-aware mapping between
*broadcast seconds* (position in the video file) and *game clock seconds*
(what's actually happening in the match), in both directions. This table is
the join key between the umpire's report (which speaks in game-clock time)
and the video file (which only understands broadcast-seconds).

### Stage 1 — Candidate detection (2.5h → ~10min)

Deliberately simple/high-recall in v1:

- `scene_detect.py` — PySceneDetect segments each quarter into shots so
  replays aren't scored as live action.
- `motion.py` — Farneback optical flow motion-spike score per 2s window.
- `tracking.py` — YOLO + ByteTrack player detections, used to score
  player-cluster density (multiple players converging).
- `pose.py` — MediaPipe Pose, used to score sudden deceleration/falling.
- `scoring.py` — combines the three signals into one weighted score per
  window and thresholds + merges into `CandidateWindow`s. Tuned generous
  on purpose; stage 3 does the real filtering.

Off-ball incidents are the hard case for a ball-following broadcast feed.
`stage1_candidates/pipeline.py` accepts an optional second "coaches' angle"
wide-shot video per quarter (`source="coaches_angle"` on `Candidate` rows) and
scores it the same way — ingest it alongside the broadcast feed if the club
or league makes it available.

### Stage 2 — Clip extraction

`stage2_clips/extractor.py` cuts a `-3s/+5s` (configurable) buffered clip
around each candidate window or umpire-reported timestamp with ffmpeg,
uploads it to S3/GCS-compatible object storage, and indexes it in Postgres
(`clips` table) tagged with game, quarter, broadcast window and mapped
game-clock time.

### Stage 3 — LLM reasoning / re-ranking

`stage3_llm/reasoner.py` samples a handful of frames per candidate clip
(`frame_sampler.py`), and sends them to Claude along with the AFL
reportable-offence categories (`rules.md`) via a forced tool call so the
response comes back as clean structured JSON (`schemas.py`:
`OffenceAssessment` — category, confidence, rationale, players involved,
`needs_human_review`). This is what actually shrinks the reviewer's job to a
ranked, annotated shortlist instead of a blind 2.5-hour watch.

### Stage 4 — Reported-offence auto-routing

`stage4_routing/webhook_app.py` exposes a small FastAPI endpoint the umpiring
platform can call (or a scheduled import job can post to) with the
structured umpire report. `umpire_ingest.py` maps the report's game-clock
time to a broadcast timestamp via the `ClockSyncTable`, extracts a clip
(stage 2), and `notifier.py` pushes the clip + report straight to the
tribunal team (webhook/Slack/email — whichever the tribunal system exposes).

## Setup

```bash
cd afl_tribunal_automation
pip install -r requirements.txt
cp .env.example .env    # fill in DB / storage / Anthropic / notification config
docker compose up -d    # local Postgres (+ MinIO for local S3-compatible storage)
python -m db.init_db     # create tables
```

If using the bundled MinIO for local dev, create the bucket once (matching
`S3_BUCKET` in `.env`) — via the console at `http://localhost:9001`
(user/pass `minioadmin`/`minioadmin`), or the `mc` CLI.

## Running it end to end

```bash
# 0. Find the on-screen clock's pixel box by eye: pull a frame, open it, measure it.
python cli.py preview-frame --video /videos/q1.mp4 --timestamp 10 --output frame.jpg

# 1. Register the game and its 4 quarter videos.
python cli.py add-game --season 2026 --round R18 --home-team Richmond --away-team Carlton \
    --q1 /videos/q1.mp4 --q2 /videos/q2.mp4 --q3 /videos/q3.mp4 --q4 /videos/q4.mp4 \
    --clock-box 1700,40,160,50
# -> prints the new game's id, e.g. "Created game 1: ..."

# 2. Stage 0: build the clock sync table for that game.
python cli.py sync-clock --game-id 1

# 3. Stages 1-3: detect candidates, cut clips, rank with Claude, for the whole game.
python cli.py run-game --game-id 1

# 4. Stage 4: serve the umpire-report webhook (separate process, runs continuously).
python cli.py serve-webhook
```

Each stage can also be run independently (`detect-candidates`,
`extract-clips`, `rank-candidates`, `ingest-umpire-report`) — see `cli.py --help`.

### Testing stage 4 without a real umpiring-platform integration

```bash
cat > report.json <<'EOF'
{
  "game_id": 1,
  "offender_jumper_number": 4,
  "offender_team": "Richmond",
  "victim_jumper_number": 17,
  "victim_team": "Carlton",
  "incident_type": "striking",
  "quarter": 2,
  "game_clock_seconds": 754
}
EOF
python cli.py ingest-umpire-report --json-file report.json
```

This bypasses the webhook and calls the same processing function directly —
useful for testing the clock-sync -> clip -> notify path before the real
platform integration exists. Once you have webhook access, POST the same
JSON shape to `http://localhost:8000/webhooks/umpire-report` instead (with
an `X-Webhook-Secret` header matching `UMPIRE_WEBHOOK_SHARED_SECRET`).

### What you need before any of this works

- **ffmpeg/ffprobe** on `PATH` (not a pip package — install via your OS
  package manager, e.g. `apt install ffmpeg` / `brew install ffmpeg`).
- **`ANTHROPIC_API_KEY`** in `.env` for stage 3.
- The **clock crop box** is broadcast-specific — re-measure it (via
  `preview-frame`) for each different broadcaster/graphics package, since
  the on-screen clock moves depending on who produced the feed.
- Stage 1's model weights (`yolov8n.pt`) download automatically on first
  run via `ultralytics` — that first `run-game`/`detect-candidates` call
  will be slower and needs outbound internet access once.

## Notes / what's intentionally out of scope for v1

- Jersey-number OCR/detection is stubbed as a hook point in `stage3_llm` —
  wire in a fine-tuned classifier when available; general OCR is unreliable
  on jerseys in motion.
- The umpiring platform integration in stage 4 assumes either webhook push or
  a scheduled export/import; the actual API contract depends on whichever
  platform the league uses and needs the real schema once known.
- YOLO/pose/OCR models are used out-of-the-box (not fine-tuned on AFL
  footage). Expect stage 1 recall/precision to improve significantly with a
  small labelled set of past tribunal incidents.
