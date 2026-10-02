import numpy as np

from stage1_candidates.pose import grounded_run_scores, grounded_scores_from_samples, torso_angle_from_vertical
from stage1_candidates.scoring import score_windows


def _kpts(shoulders, hips):
    k = np.zeros((17, 2))
    k[5] = k[6] = shoulders
    k[11] = k[12] = hips
    return k


def _sample(t, lying):
    # (timestamp, max_angle, n>55, n>60)
    return (t, 80.0 if lying else 10.0, int(lying), int(lying))


def test_torso_angle_upright_and_lying():
    assert torso_angle_from_vertical(_kpts((100, 50), (100, 150))) < 1  # hips straight below shoulders
    assert torso_angle_from_vertical(_kpts((50, 100), (150, 100))) > 89  # hips beside shoulders
    assert 40 < torso_angle_from_vertical(_kpts((0, 0), (10, 10))) < 50


def test_isolated_reading_scores_zero():
    samples = [_sample(i / 5, i == 5) for i in range(20)]  # one reading at 1.0 s
    scores = grounded_scores_from_samples(samples, 4.0, 2.0)
    assert scores[(0.0, 2.0)] == 0.0
    assert scores[(2.0, 4.0)] == 0.0


def test_sustained_body_scores_by_count():
    samples = [_sample(i / 5, 10 <= i <= 14) for i in range(20)]  # lying 2.0-2.8 s
    scores = grounded_scores_from_samples(samples, 4.0, 2.0, pad_seconds=0.0)
    assert scores[(0.0, 2.0)] == 0.0
    assert scores[(2.0, 4.0)] == 4.0  # five readings, minus one


def test_flickering_body_still_counts():
    # intermittent detection: every other sample over 1.2 s — a run-based rule scores 0
    samples = [_sample(i / 5, i in (10, 12, 14, 16)) for i in range(20)]
    counted = grounded_scores_from_samples(samples, 4.0, 2.0, pad_seconds=0.0)
    runs = grounded_run_scores([(s[0], s[3]) for s in samples], 4.0, 2.0)
    assert counted[(2.0, 4.0)] == 3.0
    assert runs[(2.0, 4.0)] == 0.0


def test_padding_credits_event_straddling_a_boundary():
    # lying 1.6-2.4 s straddles the 2.0 s boundary: 3 readings before, 2 after
    samples = [_sample(i / 5, 8 <= i <= 12) for i in range(20)]
    unpadded = grounded_scores_from_samples(samples, 4.0, 2.0, pad_seconds=0.0)
    padded = grounded_scores_from_samples(samples, 4.0, 2.0, pad_seconds=0.6)
    # unpadded: 2 readings before the boundary (-> 1), 3 after (-> 2)
    assert unpadded[(0.0, 2.0)] == 1.0 and unpadded[(2.0, 4.0)] == 2.0
    # padded: both windows see all five readings
    assert padded[(0.0, 2.0)] == 4.0 and padded[(2.0, 4.0)] == 4.0


def test_score_windows_redistributes_when_grounded_absent():
    m = {(0.0, 2.0): 1.0}
    z = {(0.0, 2.0): 0.0}
    full = score_windows(m, z, z, audio_scores={(0.0, 2.0): 1.0}, grounded_scores={(0.0, 2.0): 1.0})
    no_grounded = score_windows(m, z, z, audio_scores={(0.0, 2.0): 1.0})
    neither = score_windows(m, z, z)
    assert abs(full[0].score - (0.25 + 0.15 + 0.20)) < 1e-9
    assert abs(no_grounded[0].score - (0.25 + 0.15) / 0.80) < 1e-9
    assert abs(neither[0].score - 0.25 / 0.65) < 1e-9
