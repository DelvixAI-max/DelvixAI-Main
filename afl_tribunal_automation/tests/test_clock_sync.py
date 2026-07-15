from stage0_ingestion.clock_sync import ClockSample, ClockSyncTable, build_segments


def test_build_segments_collapses_repeated_values():
    # Clock reads 0,1,2 then pauses on 2 for a stoppage (broadcast seconds 2-4), then continues.
    samples = [
        ClockSample(0, 0),
        ClockSample(1, 1),
        ClockSample(2, 2),
        ClockSample(3, 2),
        ClockSample(4, 2),
        ClockSample(5, 3),
    ]
    segments = build_segments(samples)
    values = [(s.game_clock_seconds, s.broadcast_start_seconds, s.broadcast_end_seconds) for s in segments]
    assert values == [(0, 0, 0), (1, 1, 1), (2, 2, 4), (3, 5, 5)]


def test_build_segments_drops_ocr_misreads():
    # A single bad OCR frame (backward jump of 50s) should be dropped, not
    # treated as a real clock rewind.
    samples = [ClockSample(0, 10), ClockSample(1, 11), ClockSample(2, 40), ClockSample(3, 12)]
    segments = build_segments(samples)
    values = [s.game_clock_seconds for s in segments]
    assert 40 not in values


def test_build_segments_fills_missed_ocr_reads():
    samples = [ClockSample(0, 5), ClockSample(1, None), ClockSample(2, None), ClockSample(3, 6)]
    segments = build_segments(samples)
    assert [s.game_clock_seconds for s in segments] == [5, 6]
    assert segments[0].broadcast_end_seconds == 2  # 0,1,2 all filled to value 5


def test_broadcast_to_game_lookup():
    table = ClockSyncTable.from_samples(
        [ClockSample(0, 0), ClockSample(1, 1), ClockSample(2, 2), ClockSample(3, 3)]
    )
    assert table.broadcast_to_game(0) == 0
    assert table.broadcast_to_game(2) == 2
    assert table.broadcast_to_game(3) == 3


def test_game_to_broadcast_returns_stoppage_midpoint():
    # Clock counts normally 0..49, then pauses on game-clock=50 for a
    # stoppage spanning broadcast seconds 50-60, then resumes counting.
    samples = (
        [ClockSample(t, t) for t in range(0, 50)]
        + [ClockSample(t, 50) for t in range(50, 61)]
        + [ClockSample(t, t - 60 + 51) for t in range(61, 70)]
    )
    table = ClockSyncTable.from_samples(samples)
    broadcast_seconds = table.game_to_broadcast(50)
    assert broadcast_seconds == 55.0  # midpoint of the 50-60 stoppage


def test_game_to_broadcast_missing_value_falls_back_to_nearest():
    table = ClockSyncTable.from_samples([ClockSample(0, 0), ClockSample(1, 1), ClockSample(2, 2)])
    # game-clock=1 doesn't exist as an isolated value once merged with neighbours in this
    # tiny example, but an out-of-range request should still resolve to the closest segment.
    result = table.game_to_broadcast(999)
    assert result is not None


def test_empty_table_returns_none():
    table = ClockSyncTable([])
    assert table.broadcast_to_game(10) is None
    assert table.game_to_broadcast(10) is None
