"""Combine motion / player-density / pose signals into one candidate score
per window, then threshold + merge into CandidateWindows.

Intentionally simple (a weighted sum of min-max normalized signals) — this
is a high-recall triage filter, not a classifier. Stage 3 (Claude) does the
actual reasoning about what the motion means.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config import settings

WindowKey = tuple[float, float]


@dataclass
class CandidateWindow:
    start_seconds: float
    end_seconds: float
    score: float
    motion_score: float
    density_score: float
    pose_score: float
    peak_seconds: float | None = None  # centre of the highest-scoring window inside this span

    @property
    def anchor_seconds(self) -> float:
        """Where to centre a clip: the peak if known, else the midpoint."""
        if self.peak_seconds is not None:
            return self.peak_seconds
        return (self.start_seconds + self.end_seconds) / 2


DEFAULT_WEIGHTS = {"motion": 0.35, "density": 0.35, "pose": 0.30}


def _normalize(values: dict[WindowKey, float]) -> dict[WindowKey, float]:
    if not values:
        return {}
    max_value = max(values.values())
    if max_value <= 0:
        return {key: 0.0 for key in values}
    return {key: value / max_value for key, value in values.items()}


def score_windows(
    motion_scores: dict[WindowKey, float],
    density_scores: dict[WindowKey, float],
    pose_scores: dict[WindowKey, float],
    weights: dict[str, float] | None = None,
) -> list[CandidateWindow]:
    """Combine and normalize the three raw signal maps (must share the same
    window keys — produced with the same `window_seconds`/`duration_seconds`)
    into one CandidateWindow per window, sorted by start time."""
    weights = weights or DEFAULT_WEIGHTS
    norm_motion = _normalize(motion_scores)
    norm_density = _normalize(density_scores)
    norm_pose = _normalize(pose_scores)

    all_keys = sorted(set(norm_motion) | set(norm_density) | set(norm_pose))
    combined: list[CandidateWindow] = []
    for key in all_keys:
        m = norm_motion.get(key, 0.0)
        d = norm_density.get(key, 0.0)
        p = norm_pose.get(key, 0.0)
        score = weights["motion"] * m + weights["density"] * d + weights["pose"] * p
        combined.append(CandidateWindow(key[0], key[1], score, m, d, p, peak_seconds=(key[0] + key[1]) / 2))
    return combined


def threshold_and_merge(
    windows: list[CandidateWindow],
    score_threshold: float | None = None,
    merge_gap_seconds: float | None = None,
) -> list[CandidateWindow]:
    """Keep windows scoring above threshold, then merge windows that are
    adjacent or within `merge_gap_seconds` of each other into one candidate
    (taking the max score/components across the merged span)."""
    score_threshold = score_threshold if score_threshold is not None else settings.candidate_score_threshold
    merge_gap_seconds = (
        merge_gap_seconds if merge_gap_seconds is not None else settings.candidate_merge_gap_seconds
    )

    kept = sorted((w for w in windows if w.score >= score_threshold), key=lambda w: w.start_seconds)
    if not kept:
        return []

    merged: list[CandidateWindow] = [kept[0]]
    for window in kept[1:]:
        last = merged[-1]
        if window.start_seconds - last.end_seconds <= merge_gap_seconds:
            merged[-1] = CandidateWindow(
                start_seconds=last.start_seconds,
                end_seconds=max(last.end_seconds, window.end_seconds),
                score=max(last.score, window.score),
                motion_score=max(last.motion_score, window.motion_score),
                density_score=max(last.density_score, window.density_score),
                pose_score=max(last.pose_score, window.pose_score),
                peak_seconds=window.peak_seconds if window.score > last.score else last.peak_seconds,
            )
        else:
            merged.append(window)
    return merged
