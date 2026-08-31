from __future__ import annotations

import datetime as dt

import pytest

from unik_scheduler.kpi.weeks import week_for

ANCHOR = dt.date(2026, 8, 31)  # Monday, reported by the API as week 1


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (dt.date(2026, 8, 31), 1),  # anchor Monday
        (dt.date(2026, 9, 5), 1),  # Saturday of the same week
        (dt.date(2026, 9, 7), 2),  # next Monday flips parity
        (dt.date(2026, 9, 14), 1),
        (dt.date(2026, 9, 21), 2),
        (dt.date(2026, 8, 24), 2),  # a week before the anchor
    ],
)
def test_parity_walks_both_directions(day: dt.date, expected: int):
    assert week_for(day, ANCHOR, 1) == expected


def test_anchor_week_two_inverts_everything():
    assert week_for(ANCHOR, ANCHOR, 2) == 2
    assert week_for(dt.date(2026, 9, 7), ANCHOR, 2) == 1


def test_sunday_belongs_to_the_week_that_is_ending():
    sunday = dt.date(2026, 9, 6)
    assert week_for(sunday, ANCHOR, 1) == 1
