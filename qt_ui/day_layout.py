"""Pure datetime-math logic for the hourly day-schedule view -- ported
verbatim from calendar_gui.py's Tk implementation (_layout_day_blocks /
_contrasting_text_color). Deliberately has zero Qt/Tk imports: this is the
one piece of business-adjacent logic actually touched by the
Tkinter->PySide6 migration (moved, not rewritten), so it's kept isolated
and independently unit-testable (see tests/test_day_layout.py) rather than
folded into the rendering code that consumes it (qt_ui/day_view.py).
"""
from datetime import timedelta


def layout_day_blocks(items, min_duration=timedelta(0)):
    """Assigns each (start, end, payload) interval a (column, column_count)
    pair so overlapping blocks in a day-schedule view are drawn side by
    side, narrowed to fit, instead of full-width and stacked directly on
    top of one another. Returns items in start-sorted order with the two
    extra fields appended.

    min_duration should match the caller's rendered minimum block height
    (converted to a time span) — a short event's *drawn* box is clamped to
    that minimum height, so two short events sitting close together (but not
    technically overlapping by their raw start/end) can still collide once
    rendered. Collision detection here uses each interval's end stretched
    out to at least min_duration so the column split matches what actually
    gets drawn; the true (start, end) is still what's returned."""
    items = sorted(items, key=lambda t: t[0])
    active = []  # (effective_end, column) for intervals still "open" at the current point
    columns = [0] * len(items)
    clusters = []
    cluster_indices = []

    for i, (start, end, _payload) in enumerate(items):
        effective_end = max(end, start + min_duration)
        active = [a for a in active if a[0] > start]
        if not active and cluster_indices:
            clusters.append(cluster_indices)
            cluster_indices = []
        used = {col for _end2, col in active}
        col = 0
        while col in used:
            col += 1
        columns[i] = col
        active.append((effective_end, col))
        cluster_indices.append(i)
    if cluster_indices:
        clusters.append(cluster_indices)

    column_counts = [1] * len(items)
    for cluster in clusters:
        count = max(columns[i] for i in cluster) + 1
        for i in cluster:
            column_counts[i] = count

    return [
        (items[i][0], items[i][1], items[i][2], columns[i], column_counts[i])
        for i in range(len(items))
    ]


def contrasting_text_color(hex_color):
    """Plain-white or plain-black label text over an arbitrary event color
    swatch, picked by relative luminance so day-view blocks stay readable
    regardless of which palette color an event uses."""
    try:
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return "black" if luminance > 0.6 else "white"
    except Exception:
        return "white"
