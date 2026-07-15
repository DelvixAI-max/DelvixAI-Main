from common.time_utils import clamp, format_clock_string, parse_clock_string, windows


def test_parse_clock_string_valid():
    assert parse_clock_string("12:34") == 12 * 60 + 34
    assert parse_clock_string("0:00") == 0
    assert parse_clock_string("59:59") == 59 * 60 + 59


def test_parse_clock_string_rejects_garbage():
    assert parse_clock_string("garbage") is None
    assert parse_clock_string("12:60") is None
    assert parse_clock_string("99:99") is None
    assert parse_clock_string("") is None


def test_format_clock_string_roundtrip():
    assert format_clock_string(754) == "12:34"
    assert format_clock_string(0) == "00:00"
    assert format_clock_string(-5) == "00:00"


def test_clamp():
    assert clamp(5, 0, 10) == 5
    assert clamp(-5, 0, 10) == 0
    assert clamp(50, 0, 10) == 10


def test_windows_covers_full_duration_without_overlap():
    result = list(windows(7.0, 2.0))
    assert result == [(0.0, 2.0), (2.0, 4.0), (4.0, 6.0), (6.0, 7.0)]


def test_windows_exact_multiple():
    result = list(windows(6.0, 2.0))
    assert result == [(0.0, 2.0), (2.0, 4.0), (4.0, 6.0)]
