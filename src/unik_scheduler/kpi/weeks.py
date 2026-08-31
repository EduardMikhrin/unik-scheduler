"""Week parity (1st / 2nd week) without asking the API on every tick.

The API tells us the parity of *today*; anchoring on that and counting whole
weeks forward or back keeps the answer correct between daily syncs.
"""

from __future__ import annotations

import datetime as dt

ANCHOR_DATE_KEY = "week_anchor_date"
ANCHOR_WEEK_KEY = "week_anchor_week"


def _monday(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def week_for(target: dt.date, anchor_date: dt.date, anchor_week: int) -> int:
    delta_weeks = (_monday(target) - _monday(anchor_date)).days // 7
    return (anchor_week - 1 + delta_weeks) % 2 + 1
