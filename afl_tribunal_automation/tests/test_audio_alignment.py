from stage1_candidates.scoring import align_reaction_backwards


def test_reaction_is_credited_to_preceding_windows():
    sig = {(0.0, 2.0): 0.0, (2.0, 4.0): 0.0, (4.0, 6.0): 10.0, (6.0, 8.0): 0.0}
    out = align_reaction_backwards(sig, lag_windows=2)
    assert out[(0.0, 2.0)] == 10.0  # two windows before the reaction
    assert out[(2.0, 4.0)] == 10.0  # one window before
    assert out[(4.0, 6.0)] == 10.0  # the reaction itself
    assert out[(6.0, 8.0)] == 0.0  # never carried forward


def test_alignment_keeps_own_value_when_larger():
    sig = {(0.0, 2.0): 7.0, (2.0, 4.0): 1.0}
    out = align_reaction_backwards(sig, lag_windows=1)
    assert out[(0.0, 2.0)] == 7.0
