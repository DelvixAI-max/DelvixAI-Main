import numpy as np

from stage1_candidates.audio import crowd_rise_per_second
from stage1_candidates.scoring import score_windows


def test_crowd_rise_flags_sudden_jump_not_sustained_noise():
    # 20 s of steady -24 dB, then a 3 s "ooh" at -12 dB, then steady again,
    # then a slow ramp up to -12 dB over 20 s (sustained, not a reaction).
    quiet = [-24.0] * 20
    reaction = [-12.0] * 3
    ramp = list(np.linspace(-24.0, -12.0, 20))
    loudness = np.array(quiet + reaction + quiet + ramp)
    rise = crowd_rise_per_second(loudness, baseline_seconds=8)

    assert rise[20] > 10  # the first second of the reaction is a big jump
    assert rise[:20].max() == 0.0  # steady level never registers
    assert rise[-5:].max() < 3  # a slow ramp stays below the baseline window


def test_score_windows_redistributes_audio_weight_when_absent():
    m = {(0.0, 2.0): 1.0}
    d = {(0.0, 2.0): 0.0}
    p = {(0.0, 2.0): 0.0}
    with_audio = score_windows(m, d, p, audio_scores={(0.0, 2.0): 1.0})
    without = score_windows(m, d, p, audio_scores=None)
    # Max on every present signal should give the same full-scale score either way
    assert abs(with_audio[0].score - (0.30 + 0.20)) < 1e-9
    assert abs(without[0].score - 0.30 / 0.80) < 1e-9


def test_audio_contributes_to_score():
    m = {(0.0, 2.0): 1.0, (2.0, 4.0): 1.0}
    d = {(0.0, 2.0): 0.0, (2.0, 4.0): 0.0}
    p = {(0.0, 2.0): 0.0, (2.0, 4.0): 0.0}
    a = {(0.0, 2.0): 10.0, (2.0, 4.0): 0.0}
    out = score_windows(m, d, p, a)
    assert out[0].score > out[1].score
    assert out[0].audio_score == 1.0 and out[1].audio_score == 0.0
