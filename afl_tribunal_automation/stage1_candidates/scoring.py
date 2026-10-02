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
    audio_score: float = 0.0
    peak_seconds: float | None = None  # centre of the highest-scoring window inside this span

    @property
    def anchor_seconds(self) -> float:
        """Where to centre a clip: the peak if known, else the midpoint."""
        if self.peak_seconds is not None:
            return self.peak_seconds
        return (self.start_seconds + self.end_seconds) / 2


DEFAULT_WEIGHTS = {"motion": 0.30, "density": 0.25, "pose": 0.25, "audio": 0.20}


def _normalize(values: dict[WindowKey, float]) -> dict[WindowKey, float]:
    if not values:
        return {}
    max_value = max(values.values())
    if max_value <= 0:
        return {key: 0.0 for key in values}
    return {key: value / max_value for key, value in values.items()}


def align_reaction_backwards(signal: dict[WindowKey, float], lag_windows: int = 2) -> dict[WindowKey, float]:
    """A crowd reaction or whistle follows the event it responds to by a
    second or two. Credit each window with the loudest reaction in the next
    `lag_windows` windows as well as its own, so the reaction lands on the
    window that holds the action rather than the one after it."""
    keys = sorted(signal)
    values = [signal[k] for k in keys]
    aligned = {}
    for i, key in enumerate(keys):
        aligned[key] = max(values[i : i + lag_windows + 1])
    return aligned


def score_windows(
    motion_scores: dict[WindowKey, float],
    density_scores: dict[WindowKey, float],
    pose_scores: dict[WindowKey, float],
    audio_scores: dict[WindowKey, float] | None = None,
    weights: dict[str, float] | None = None,
) -> list[CandidateWindow]:
    """Combine and normalize the raw signal maps (must share the same window
    keys — produced with the same `window_seconds`/`duration_seconds`) into
    one CandidateWindow per window, sorted by start time.

    `audio_scores` is optional (footage with no usable audio track); when
    absent its weight is redistributed so scores stay comparable."""
    weights = dict(weights or DEFAULT_WEIGHTS)
    if audio_scores is None:
        audio_weight = weights.pop("audio", 0.0)
        total = sum(weights.values())
        weights = {k: v + audio_weight * (v / total) for k, v in weights.items()}
        weights["audio"] = 0.0

    norm_motion = _normalize(motion_scores)
    norm_density = _normalize(density_scores)
    norm_pose = _normalize(pose_scores)
    norm_audio = _normalize(align_reaction_backwards(audio_scores) if audio_scores else {})

    all_keys = sorted(set(norm_motion) | set(norm_density) | set(norm_pose) | set(norm_audio))
    combined: list[CandidateWindow] = []
    for key in all_keys:
        m = norm_motion.get(key, 0.0)
        d = norm_density.get(key, 0.0)
        p = norm_pose.get(key, 0.0)
        a = norm_audio.get(key, 0.0)
        # Density on its own is mostly post-goal regroups and ball-ups —
        # players bunched but nothing happening. Only let it count when
        # there's motion to go with it (a pack *and* a collision).
        gated_density = d * (m ** 0.5)
        score = (
            weights["motion"] * m
            + weights["density"] * gated_density
            + weights["pose"] * p
            + weights["audio"] * a
        )
        combined.append(
            CandidateWindow(key[0], key[1], score, m, d, p, audio_score=a, peak_seconds=(key[0] + key[1]) / 2)
        )
    return combined


def threshold_and_merge(
    windows: list[CandidateWindow],
    score_threshold: float | None = None,
    merge_gap_seconds: float | None = None,
    top_fraction: float | None = None,
) -> list[CandidateWindow]:
    """Keep the highest-scoring windows, then merge windows that are
    adjacent or within `merge_gap_seconds` of each other into one candidate
    (taking the max score/components across the merged span).

    Selection is relative by default: `top_fraction` keeps that share of all
    windows (e.g. 0.04 = the top 4% of a quarter), which stays stable no
    matter how many signals feed the score or how lively the game is. An
    absolute `score_threshold` is applied on top as a floor.
    """
    score_threshold = score_threshold if score_threshold is not None else settings.candidate_score_threshold
    merge_gap_seconds = (
        merge_gap_seconds if merge_gap_seconds is not None else settings.candidate_merge_gap_seconds
    )
    top_fraction = top_fraction if top_fraction is not None else settings.candidate_top_fraction

    cutoff = score_threshold
    if top_fraction and windows:
        scores = sorted((w.score for w in windows), reverse=True)
        keep_n = max(1, int(round(len(scores) * top_fraction)))
        cutoff = max(score_threshold, scores[keep_n - 1])

    kept = sorted((w for w in windows if w.score >= cutoff), key=lambda w: w.start_seconds)
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
                audio_score=max(last.audio_score, window.audio_score),
                peak_seconds=window.peak_seconds if window.score > last.score else last.peak_seconds,
            )
        else:
            merged.append(window)
    return merged
