"""Pure-logic tests for the ported overlap-column-assignment algorithm --
no Qt involved. This is the one piece of business-adjacent logic actually
touched (moved, not rewritten) by the Tkinter->PySide6 migration, and a
regression here would be visually subtle (misaligned/overlapping blocks)
rather than a crash, so it gets direct fixture-based coverage independent
of any rendering."""
from datetime import datetime, timedelta

from qt_ui.day_layout import contrasting_text_color, layout_day_blocks


def _dt(hour, minute=0):
    return datetime(2026, 1, 1, hour, minute)


def test_non_overlapping_events_all_get_full_width():
    items = [
        (_dt(9), _dt(10), "A"),
        (_dt(11), _dt(12), "B"),
        (_dt(13), _dt(14), "C"),
    ]
    result = layout_day_blocks(items)
    for _start, _end, _payload, col, cols in result:
        assert col == 0
        assert cols == 1


def test_fully_overlapping_events_split_into_columns():
    items = [
        (_dt(9), _dt(10), "A"),
        (_dt(9), _dt(10), "B"),
        (_dt(9), _dt(10), "C"),
    ]
    result = layout_day_blocks(items)
    cols_assigned = sorted(col for _s, _e, _p, col, _c in result)
    assert cols_assigned == [0, 1, 2]
    assert all(cols == 3 for _s, _e, _p, _col, cols in result)


def test_partial_overlap_splits_into_two_columns():
    # A: 9:00-9:30, B: 9:15-9:45 -- partially overlapping, must not share a column
    items = [
        (_dt(9, 0), _dt(9, 30), "A"),
        (_dt(9, 15), _dt(9, 45), "B"),
    ]
    result = layout_day_blocks(items)
    by_payload = {payload: (col, cols) for _s, _e, payload, col, cols in result}
    assert by_payload["A"][0] != by_payload["B"][0]
    assert by_payload["A"][1] == 2
    assert by_payload["B"][1] == 2


def test_chain_of_partial_overlaps_reuses_freed_column():
    # A: 9:00-9:30, B: 9:15-9:45, C: 9:40-10:00 -- A and C never overlap
    # (A ends before C starts), so C should be able to reuse A's column
    # instead of needing a 3rd.
    items = [
        (_dt(9, 0), _dt(9, 30), "A"),
        (_dt(9, 15), _dt(9, 45), "B"),
        (_dt(9, 40), _dt(10, 0), "C"),
    ]
    result = layout_day_blocks(items)
    by_payload = {payload: (col, cols) for _s, _e, payload, col, cols in result}
    assert by_payload["A"][1] == 2
    assert by_payload["B"][1] == 2
    assert by_payload["C"][1] == 2
    assert by_payload["A"][0] == by_payload["C"][0]
    assert by_payload["B"][0] != by_payload["A"][0]


def test_min_duration_prevents_visual_collision_from_clamped_short_blocks():
    # Two very short events (4 min each) that don't overlap by raw time but
    # would visually collide once each is clamped to a ~18.5 minute minimum
    # rendered height -- must land in different columns when min_duration
    # reflects that clamp.
    items = [
        (_dt(10, 0), _dt(10, 4), "short1"),
        (_dt(10, 8), _dt(10, 48), "long"),
    ]
    min_duration = timedelta(minutes=18.46)
    result = layout_day_blocks(items, min_duration=min_duration)
    by_payload = {payload: col for _s, _e, payload, col, _c in result}
    assert by_payload["short1"] != by_payload["long"]


def test_min_duration_zero_matches_default_behavior():
    items = [(_dt(9), _dt(9, 5), "A"), (_dt(9, 10), _dt(9, 15), "B")]
    default_result = layout_day_blocks(items)
    explicit_zero_result = layout_day_blocks(items, min_duration=timedelta(0))
    assert default_result == explicit_zero_result


def test_contrasting_text_color_light_background_gets_black_text():
    assert contrasting_text_color("#ffffff") == "black"
    assert contrasting_text_color("#f4511e") in ("black", "white")  # doesn't raise


def test_contrasting_text_color_dark_background_gets_white_text():
    assert contrasting_text_color("#000000") == "white"
    assert contrasting_text_color("#1e1e1e") == "white"


def test_contrasting_text_color_invalid_input_falls_back_to_white():
    assert contrasting_text_color("not-a-color") == "white"
    assert contrasting_text_color(None) == "white"
