from __future__ import annotations

import datetime as dt

# The API spells Tuesday "Вв", not "Вт".
DAY_TO_INDEX: dict[str, int] = {"Пн": 0, "Вв": 1, "Вт": 1, "Ср": 2, "Чт": 3, "Пт": 4, "Сб": 5}

DAY_NAMES_UK: tuple[str, ...] = (
    "понеділок",
    "вівторок",
    "середа",
    "четвер",
    "п'ятниця",
    "субота",
    "неділя",
)
DAY_SHORT_UK: tuple[str, ...] = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд")

LESSON_DURATION = dt.timedelta(minutes=95)

TYPE_LABEL_UK: dict[str, str] = {"lec": "Лекція", "prac": "Практика", "lab": "Лабораторна"}
TYPE_EMOJI: dict[str, str] = {"lec": "📘", "prac": "📝", "lab": "🔬"}


def lesson_end(start: dt.time) -> dt.time:
    """KPI pairs all run 1h35m; the grid is 08:30, 10:25, 12:20, 14:15, 16:10, 18:30."""
    base = dt.datetime.combine(dt.date(2000, 1, 1), start)
    return (base + LESSON_DURATION).time()
