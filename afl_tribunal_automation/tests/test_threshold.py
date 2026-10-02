from stage1_candidates.scoring import CandidateWindow, threshold_and_merge


def _w(i, score):
    return CandidateWindow(i * 2.0, i * 2.0 + 2.0, score, score, score, score)


def test_top_fraction_keeps_relative_share():
    windows = [_w(i, i / 100.0) for i in range(100)]  # scores 0.00 .. 0.99, far apart
    kept = threshold_and_merge(windows, score_threshold=0.0, merge_gap_seconds=0, top_fraction=0.05)
    # top 5% of 100 windows = 5 windows; adjacent ones merge, so check span not count
    assert kept[-1].end_seconds == 200.0
    assert kept[0].start_seconds == 190.0


def test_score_floor_still_applies_under_top_fraction():
    windows = [_w(i, 0.1) for i in range(50)]  # everything is weak
    kept = threshold_and_merge(windows, score_threshold=0.3, merge_gap_seconds=0, top_fraction=0.5)
    assert kept == []


def test_top_fraction_none_falls_back_to_absolute_threshold():
    windows = [_w(0, 0.9), _w(1, 0.2)]
    kept = threshold_and_merge(windows, score_threshold=0.5, merge_gap_seconds=0, top_fraction=0.0)
    assert len(kept) == 1 and kept[0].start_seconds == 0.0
