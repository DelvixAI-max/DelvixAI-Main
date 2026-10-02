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

## Open questions

- Need a quarter containing a known incident (reported or missed) to measure
  recall at all. Current tuning could be over-suppressing — unknown.
- Confirm how VAFA umpires record incident time (elapsed quarter time?) so
  the umpire-report → clip mapping (Stage 4) can be validated.
- Jersey-number identification is not implemented; the model's player
  attribution will be weak on 720p ground footage.
