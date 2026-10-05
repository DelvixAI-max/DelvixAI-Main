# First real-footage run — VAFA 2026 R16 Prem B, Old Camberwell v AJAX, Q1

Single-camera ground recording (VAFA TV), 1280x720 @ 25 fps, 29:47. No
on-screen clock; linear clock mode used (video start ≈ opening bounce).
Ground scoreboard visible at 38 s (reads 0:36) and 1310 s (reads 21:44),
so linear mapping holds to within ~6 s across the quarter.

## Ground truth

Every candidate was reviewed by eye. **No reportable act occurred in Q1.**
The quarter is useful only for measuring false positives; it says nothing
about recall.

## Baseline heuristic (weighted sum, raw optical flow)

- 53 candidates, 202 s flagged (11.3% of the quarter), median 2 s.
- Everything flagged was ordinary play. Two false-positive classes dominated:
  - **camera panning**: whole-frame optical flow spikes when the operator
    swings to follow the ball;
  - **post-goal regroups / ball-ups**: high player density with nothing
    happening (both of the two top density windows were teams walking back
    to the centre after a goal).

## Tuned heuristic

- Motion: subtract the median flow vector (pan estimate), take the 95th
  percentile of the residual instead of the mean.
- Density: weight by sqrt(normalised motion) so a static pack doesn't score.

Result on the same quarter: **19 candidates, 52 s flagged (2.9%)**. Two of
the four regroup/stoppage windows dropped out; the one with real jostling
(≈ Q1 19:00) still ranks first, which is the right outcome.

## Audio signal and relative threshold

Adding crowd/whistle loudness *rise* as a fourth signal exposed that the
fixed 0.5 threshold was fragile: diluting each window's weighted sum
collapsed the quarter to 2 candidates. Selection is now the top 4% of
windows (absolute threshold kept only as a floor), and raw per-window
signals are cached so re-scoring takes seconds.

The loudest audio rise of the quarter (+17.7 dB at 1170 s) was a pack
contest with players on the ground that the visual signals had under-
scored — but the reaction landed 6 s before the visual peak, in a
different window. Aligning audio backwards by up to two windows fixed it.

Final Q1 result (all four signals, top 4%): **26 candidates, 78 s (4.4%)**.
The pack contest ranks #2; the one jostling regroup is still in; the
post-goal walk-back, the goal and the static set shot are out.

| version | candidates | seconds |
|---|---|---|
| baseline (3 signals, fixed 0.5) | 53 | 202 |
| pan-compensated + gated density | 19 | 52 |
| + audio, fixed 0.5 (broken) | 2 | 4 |
| + audio, top 4%, lag-aligned | 26 | 78 |

## Open questions

- Need a quarter containing a known incident (reported or missed) to measure
  recall at all. Current tuning could be over-suppressing — unknown.
- Confirm how VAFA umpires record incident time (elapsed quarter time?) so
  the umpire-report → clip mapping (Stage 4) can be validated.
- Jersey-number identification is not implemented; the model's player
  attribution will be weak on 720p ground footage.

## Corrected re-run (after Q3 findings)

Q1 was re-run with every correction from Q3 applied: native 1280 px
detection, grounded-body signal, 6% cut, audio lag alignment, and review
at 5 fps around each candidate's peak.

| | original | corrected |
|---|---|---|
| candidates | 26 | 38 |
| seconds flagged | 78 | 116 |
| clips to reviewer | 1 | 6 |

The original Q1 verdict ("nothing reportable, one borderline regroup") was
reached at 1 fps and is withdrawn. At 5 fps, five more candidates show a
player on the ground with opponents over him (20:02, 24:18, 23:54, 5:36,
19:48). None is as clear as the Q3 incidents, and all may be fair tackles —
but that is the reviewer's call, not the tool's. All six were in the
detector's list; the correction was entirely in the review stage.
