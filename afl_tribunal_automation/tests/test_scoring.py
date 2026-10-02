from stage1_candidates.scoring import score_windows, threshold_and_merge


def test_score_windows_combines_and_normalizes():
    motion = {(0.0, 2.0): 10.0, (2.0, 4.0): 5.0}
    density = {(0.0, 2.0): 2.0, (2.0, 4.0): 4.0}
    pose = {(0.0, 2.0): 0.0, (2.0, 4.0): 1.0}

    windows = score_windows(motion, density, pose)
    assert len(windows) == 2

    first, second = windows
    assert first.start_seconds == 0.0
    # motion normalized to 1.0 (max), density normalized to 0.5
    assert first.motion_score == 1.0
    assert first.density_score == 0.5
    assert second.density_score == 1.0
    assert second.pose_score == 1.0


def test_score_windows_handles_all_zero_signal():
    motion = {(0.0, 2.0): 0.0}
    density = {(0.0, 2.0): 0.0}
    pose = {(0.0, 2.0): 0.0}
    windows = score_windows(motion, density, pose)
    assert windows[0].score == 0.0


def test_threshold_and_merge_drops_low_score_windows():
    from stage1_candidates.scoring import CandidateWindow

    windows = [
        CandidateWindow(0.0, 2.0, score=0.9, motion_score=0.9, density_score=0.9, pose_score=0.9),
        CandidateWindow(2.0, 4.0, score=0.1, motion_score=0.1, density_score=0.1, pose_score=0.1),
    ]
    kept = threshold_and_merge(windows, score_threshold=0.5, merge_gap_seconds=2, top_fraction=0)
    assert len(kept) == 1
    assert kept[0].start_seconds == 0.0


def test_threshold_and_merge_merges_adjacent_windows():
    from stage1_candidates.scoring import CandidateWindow

    windows = [
        CandidateWindow(0.0, 2.0, score=0.6, motion_score=0.6, density_score=0.0, pose_score=0.0),
        CandidateWindow(2.0, 4.0, score=0.7, motion_score=0.0, density_score=0.7, pose_score=0.0),
        CandidateWindow(10.0, 12.0, score=0.8, motion_score=0.0, density_score=0.0, pose_score=0.8),
    ]
    merged = threshold_and_merge(windows, score_threshold=0.5, merge_gap_seconds=2, top_fraction=0)
    assert len(merged) == 2
    assert merged[0].start_seconds == 0.0
    assert merged[0].end_seconds == 4.0
    assert merged[0].score == 0.7  # max of the merged windows
    assert merged[1].start_seconds == 10.0
