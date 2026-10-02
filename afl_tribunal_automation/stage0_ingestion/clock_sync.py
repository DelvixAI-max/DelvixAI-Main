"""Turn raw, noisy per-second OCR clock samples into a clean, stoppage-aware
broadcast-second <-> game-clock-second mapping.

An AFL quarter clock counts *up* from 0:00 in real broadcasts (elapsed time),
pausing whenever play is stopped (ball out of bounds, injury, goal review,
etc). So within a quarter the sequence of game-clock values is monotonic
non-decreasing in broadcast time, but not linear — the same game-clock value
can span many broadcast seconds during a stoppage, and OCR will occasionally
misread a frame. That's exactly what `ClockSyncTable` cleans up and indexes.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass


@dataclass
class ClockSample:
    """One raw OCR reading of the on-screen clock at a given broadcast
    second. Kept dependency-free (no cv2/OCR imports) so the pure sync-table
    logic below can be unit tested without the heavy vision stack installed."""

    broadcast_second: int
    game_clock_seconds: int | None  # None if OCR couldn't read this frame


@dataclass
class ClockSyncSegment:
    game_clock_seconds: int
    broadcast_start_seconds: float
    broadcast_end_seconds: float


def _denoise(
    samples: list[ClockSample], max_backward_jump: int = 3, forward_slack: int = 2
) -> list[ClockSample]:
    """Drop OCR misreads using the one fact we know for certain about an AFL
    game clock: it never runs faster than real time. So between two readings,
    the game-clock delta can never exceed the broadcast-second delta (plus a
    little slack for OCR/sampling noise) — and it can't run backwards beyond
    a small tolerance either (a stoppage pauses it, it never rewinds).

    A backward-only check isn't enough: a single spurious *forward* spike
    (OCR misreads "12" as "40") would otherwise become the new "last good"
    value and cause every subsequent correct reading to look like a bogus
    rewind. Bounding the forward delta too catches the spike itself instead.
    """
    cleaned: list[ClockSample] = []
    last_good_value: int | None = None
    last_good_broadcast: int | None = None
    for sample in samples:
        value = sample.game_clock_seconds
        if value is None:
            cleaned.append(sample)
            continue
        if last_good_value is not None:
            elapsed = sample.broadcast_second - last_good_broadcast
            delta = value - last_good_value
            max_forward = elapsed + forward_slack
            if delta > max_forward or delta < -max_backward_jump:
                cleaned.append(ClockSample(sample.broadcast_second, None))
                continue
        last_good_value = value
        last_good_broadcast = sample.broadcast_second
        cleaned.append(sample)
    return cleaned


def _fill_gaps(samples: list[ClockSample]) -> list[ClockSample]:
    """Forward-fill missed OCR reads with the last known good value, so
    every broadcast second gets a game-clock value."""
    filled: list[ClockSample] = []
    last_good: int | None = None
    for sample in samples:
        value = sample.game_clock_seconds if sample.game_clock_seconds is not None else last_good
        if value is not None:
            last_good = value
        filled.append(ClockSample(sample.broadcast_second, value))
    return filled


def build_segments(samples: list[ClockSample]) -> list[ClockSyncSegment]:
    """Collapse consecutive samples sharing the same game-clock value into
    contiguous [start, end] broadcast-second segments."""
    cleaned = _fill_gaps(_denoise(samples))
    cleaned = [s for s in cleaned if s.game_clock_seconds is not None]
    if not cleaned:
        return []

    segments: list[ClockSyncSegment] = []
    seg_value = cleaned[0].game_clock_seconds
    seg_start = cleaned[0].broadcast_second
    seg_end = cleaned[0].broadcast_second

    for sample in cleaned[1:]:
        if sample.game_clock_seconds == seg_value:
            seg_end = sample.broadcast_second
        else:
            segments.append(ClockSyncSegment(seg_value, seg_start, seg_end))
            seg_value = sample.game_clock_seconds
            seg_start = sample.broadcast_second
            seg_end = sample.broadcast_second

    segments.append(ClockSyncSegment(seg_value, seg_start, seg_end))
    return segments


class ClockSyncTable:
    """Bidirectional lookup between broadcast-seconds (position in the
    quarter's video file) and game-clock-seconds (elapsed match time)."""

    def __init__(self, segments: list[ClockSyncSegment]):
        self.segments = sorted(segments, key=lambda s: s.broadcast_start_seconds)
        self._starts = [s.broadcast_start_seconds for s in self.segments]

    @classmethod
    def from_samples(cls, samples: list[ClockSample]) -> "ClockSyncTable":
        return cls(build_segments(samples))

    @classmethod
    def linear(cls, duration_seconds: float, start_offset_seconds: float = 0.0) -> "ClockSyncTable":
        """Fallback for footage with no on-screen clock (e.g. a fixed-camera
        ground recording): game clock = video time - offset to first bounce.
        Correct whenever the recording runs continuously through stoppages,
        which is the usual case for a single-camera match recording."""
        segments = []
        second = 0
        while start_offset_seconds + second < duration_seconds:
            b = start_offset_seconds + second
            segments.append(ClockSyncSegment(second, b, b))
            second += 1
        return cls(segments)

    def broadcast_to_game(self, broadcast_second: float) -> int | None:
        """What did the on-screen clock read at this point in the video?"""
        if not self.segments:
            return None
        idx = bisect_right(self._starts, broadcast_second) - 1
        idx = max(0, min(idx, len(self.segments) - 1))
        segment = self.segments[idx]
        if segment.broadcast_start_seconds <= broadcast_second <= segment.broadcast_end_seconds + 1:
            return segment.game_clock_seconds
        # Between segments (shouldn't normally happen once gaps are filled) —
        # fall back to nearest segment's value.
        return segment.game_clock_seconds

    def game_to_broadcast(self, game_clock_seconds: int) -> float | None:
        """When (broadcast second) did the on-screen clock read this value?

        If the clock paused on this value (a stoppage), returns the midpoint
        of the paused range — a reasonable anchor for cutting a clip around
        an incident reported at this game-clock time.
        """
        matches = [s for s in self.segments if s.game_clock_seconds == game_clock_seconds]
        if not matches:
            return self._nearest_by_value(game_clock_seconds)
        segment = matches[0]
        return (segment.broadcast_start_seconds + segment.broadcast_end_seconds) / 2

    def _nearest_by_value(self, game_clock_seconds: int) -> float | None:
        if not self.segments:
            return None
        closest = min(self.segments, key=lambda s: abs(s.game_clock_seconds - game_clock_seconds))
        return (closest.broadcast_start_seconds + closest.broadcast_end_seconds) / 2
