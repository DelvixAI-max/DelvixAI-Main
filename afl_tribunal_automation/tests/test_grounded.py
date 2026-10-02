import numpy as np

from stage1_candidates.pose import grounded_run_scores, torso_angle_from_vertical
from stage1_candidates.scoring import score_windows


def _kpts(shoulders, hips):
    k = np.zeros((17, 2))
    k[5] = k[6] = shoulders
    k[11] = k[12] = hips
    return k


def test_torso_angle_upright_and_lying():
    assert torso_angle_from_vertical(_kpts((100, 50), (100, 150))) < 1  # hips straight below shoulders
    assert torso_angle_from_vertical(_kpts((50, 100), (150, 100))) > 89  # hips beside shoulders
    assert 40 < torso_angle_from_vertical(_kpts((0, 0), (10, 10))) < 50


def test_grounded_run_ignores_isolated_readings():
    # 5 fps samples over 4 s; one isolated horizontal reading at 1.0 s
    samples = [(i / 5, 1 if i == 5 else 0) for i in range(20)]
    scores = grounded_run_scores(samples, 4.0, 2.0)
    assert scores[(0.0, 2.0)] == 0.0
    assert scores[(2.0, 4.0)] == 0.0


def test_grounded_run_scores_sustained_horizontal_body():
    # body horizontal for samples 10..14 (1.0 s) inside the second window
    samples = [(i / 5, 1 if 10 <= i <= 14 else 0) for i in range(20)]
    scores = grounded_run_scores(samples, 4.0, 2.0)
    assert scores[(0.0, 2.0)] == 0.0
    assert scores[(2.0, 4.0)] == 4.0  # run of 5, minus one


def test_score_windows_redistributes_when_grounded_absent():
    m = {(0.0, 2.0): 1.0}
    z = {(0.0, 2.0): 0.0}
    full = score_windows(m, z, z, audio_scores={(0.0, 2.0): 1.0}, grounded_scores={(0.0, 2.0): 1.0})
    no_grounded = score_windows(m, z, z, audio_scores={(0.0, 2.0): 1.0})
    neither = score_windows(m, z, z)
    assert abs(full[0].score - (0.25 + 0.15 + 0.20)) < 1e-9
    assert abs(no_grounded[0].score - (0.25 + 0.15) / 0.80) < 1e-9
    assert abs(neither[0].score - 0.25 / 0.65) < 1e-9
