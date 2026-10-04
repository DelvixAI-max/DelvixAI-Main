# Q3 run — VAFA 2026 R16 Prem B, Old Camberwell v AJAX

Same single-camera 720p recording as Q1. 30:48. Quarter clock = video time − 4 s
(checked against the ground scoreboard at 681 s = Q3 11:14).

## Ground truth (league-confirmed and reviewed by eye)

| Q3 time | Video s | Incident |
|---|---|---|
| **10:52** | 656 | **Sling tackle** — ball carrier tackled from behind, rotated and driven to ground on his back, pinned. League identified this one. |
| 10:57 | 661 | Second player down on the same spot, pack forms |
| 17:28 | 1052 | Tackle near goal square, 5–6 player pack over the grounded player, shoving, player down ~5 s |
| 20:02 | 1206 | Tackle, 8–10 player pack, player stays down several seconds |
| 20:20 | 1224 | Second player down, pack re-forms |
| 24:52 | 1496 | Player grabbed and swung to ground in open play |
| 26:22 | 1586 | Player to ground, several players grappling over him ~3 s |

## Detector results per version

| Version | Cands | Secs | 10:52 sling | 17:28 | 20:02 | 20:20 | 24:52 | 26:22 |
|---|---|---|---|---|---|---|---|---|
| 4 signals, imgsz 640 | 26 | 76 | ✗ (rank 694/925) | ✗ | ✓ #1 | ✓ | ✓ #3 | ✗ |
| + imgsz 1280 | 25 | 78 | ✗ (rank 578/925) | ✗ | ✓ #1 | ✓ | ✓ | ✗ |
| + grounded (run-based) | 26 | 78 | ✗ (rank 429) | ✗ (rank 75, g=0) | ✓ #1 | ✓ | ✓ | **✓ #7, g=1.0** |
| + grounded (count, padded, cached samples) | 24 | 78 | ✗ (rank 232) | ✗ (rank 51) | ✓ #2 | ✓ | ✓ | ✓ | + 14:08 ✓ |

At the top-4% cut: **5 of 8** incidents (the 7 listed plus 14:08). 17:28 sits
just outside (rank 51 of 925): its horizontal-body readings are real but
sparse (1–4 per window) because the downed player is mostly hidden by the pack.

Cut sweep from cached signals:

| cut | cands | secs | caught |
|---|---|---|---|
| 4% | 24 | 78 | 5/7 |
| 5% | 30 | 96 | 5/7 |
| **6%** | **35** | **120** | **6/7** (adds 17:28) |
| 8% | 44 | 164 | 6/7 |

Default moved to **6%**: ~2 min of candidate clips per quarter, ~8 min per
game before stage-3 filtering. The sling tackle and its immediate aftermath
remain out of reach for the reasons in §3 below.

The grounded signal also surfaced a moment nobody had listed: **14:08 (852 s)** —
a player tackled, landing flat on his side, taking 4–5 s to get up while
play moves on. Added to the reel for the reviewer. 474 s (a tackle pile) also
fired; ordinary football, but the right class for a triage filter.

## What went wrong, in order of importance

### 1. Detection resolution (fixed)

YOLO was run at `imgsz=640` on 1280-wide footage. Around the sling tackle it
detected **2–3 of ~10 visible players** per frame, and did not detect the
slung player at all while he was horizontal under the tackler. At `imgsz=1280`
the same nano model sees 8–10 players at no extra cost (117 ms/frame vs 357).

Larger models at 1280 (s: 10–11/frame, m: 9–12/frame) gain little over nano
and cost 2–4×. Resolution was the lever, not model size.

### 2. The pose signal measures the wrong thing (partly fixed)

"Torso-centre acceleration" is dominated by sprinters changing direction. A
sling tackle rotates a torso in place; a pack over a downed player has almost
no motion at all. Neither registers.

Torso **orientation** (shoulder→hip angle from vertical) does: every
pack-over-player incident shows a body at 57–89° for 2–5 consecutive samples,
while ordinary play produces only isolated single readings just over 55°
(sprinters leaning).

First version scored the longest *run* of consecutive horizontal samples.
That caught the dense events (26:22: 9 of 10 samples) but scored 17:28 at 0:
a body inside a pack flickers in and out of detection (1–3 readings per
window, non-consecutive), and the result also depended on where the 2 s
window boundary fell. Now: *count* of samples with a horizontal body over a
0.6 s-padded window, minus one. Raw per-sample readings are cached so this
can be re-tuned in seconds.

### 3. The sling moment itself is occluded (not fixable from this footage)

During the 0.6 s of the sling (656.2–656.8) the pose model detects only the
upright tackler. The slung player is under him and gets no keypoints, so no
signal — orientation, acceleration or anything else — can fire on the moment
itself. The `grounded` signal picks up the aftermath (658–662, bodies at
75–82°) but it's weak. Catching the sling *action* needs either a
higher-resolution feed or a second camera angle.

### 4. The 2-second manual scan missed it too

A frame every 2 s skipped the 0.6 s sling entirely; it looked like an ordinary
tackle. Recorded here as a warning about how brief this class of incident is.

### 5. The review stage can throw away a correct detection

**Q3 2:21 (145 s)**: black #13 kicks; an opponent runs through him after
disposal and takes him to ground. The detector ranked this window **#2 in
the quarter** (motion 0.84, audio 0.68). It was then dismissed at review as
an ordinary tackle, because the review used 8 frames at 1 fps across 8 s —
at that density "late bump after a kick" and "tackle" look identical.

Stage 3 was sending Claude the same 8 evenly spaced frames. Now: context
frames across the clip **plus a 12-frame burst at ~4 fps centred on the
detector's peak moment**. Fixing the detector would have done nothing here;
the pipeline's weakest link was the stage that decides what the detector's
output means.

| Q3 time | Video s | Incident |
|---|---|---|
| 2:21 | 145 | Late contact: kicker bumped to ground after disposal (league-identified; detector #2, review miss) |

## Still open

- Confirm with the re-run whether `grounded` lifts 17:28 and 26:22 into the
  top 4% without flooding the list with ordinary tackles-to-ground.
- An explicit "player detected then lost next to another player" signal might
  catch occlusion-type events like the sling; untested.
- Stage 3 (Claude) still unexercised — API key not yet configured.
