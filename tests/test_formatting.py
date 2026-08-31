"""Messages go out as HTML, and course titles contain characters HTML cares about."""

from __future__ import annotations

import datetime as dt

from unik_scheduler.bot.formatting import (
    LessonView,
    render_changes,
    render_day,
    render_digest,
    render_reminder,
    time_range,
)
from unik_scheduler.db.models import Lesson, Subject

QA_TITLE = (
    "Тестування та контроль якості (QA) вбудованих систем "
    "(Сертифікатна програма ESI&IoT з компанією Global Logic)"
)


def make_view(
    name: str = QA_TITLE,
    *,
    short: str | None = None,
    start: dt.time = dt.time(10, 25),
    tag: str = "lec",
    type_: str = "Лек",
    lecturer: str | None = "Клименко Ірина Анатоліївна",
    day: int = 0,
) -> LessonView:
    subject = Subject(id=16, name=name, short_name=short, kind="elective", semester=7)
    lesson = Lesson(
        id=1, week=1, day=day, start=start, raw_name=name, type=type_, tag=tag, lecturer=lecturer
    )
    return LessonView(lesson, subject)


def test_ampersand_in_a_course_title_is_escaped():
    text = render_reminder(make_view(), None, 10)
    assert "ESI&amp;IoT" in text
    assert "ESI&IoT" not in text.replace("ESI&amp;IoT", "")


def test_reminder_carries_start_and_end_time():
    text = render_reminder(make_view(), None, 10)
    assert "10:25 – 12:00" in text


def test_reminder_names_the_lecturer_and_the_lead_time():
    text = render_reminder(make_view(), None, 10)
    assert "через 10 хвилин" in text
    assert "Клименко Ірина Анатоліївна" in text


def test_lecturer_line_is_dropped_when_the_api_has_none():
    text = render_reminder(make_view(lecturer=None), None, 10)
    assert "👤" not in text


def test_last_pair_of_the_day_says_so():
    text = render_reminder(make_view(), None, 10)
    assert "остання пара сьогодні" in text
    assert "Далі сьогодні" not in text


def test_next_pair_line_uses_the_following_lesson():
    following = make_view("Технології інтернет речей", start=dt.time(12, 20))
    text = render_reminder(make_view(), following, 10)
    assert "Далі сьогодні: 12:20 · Технології інтернет речей (Лек)" in text


def test_reminder_prefers_the_full_title_over_the_short_one():
    text = render_reminder(make_view(short="QA вбудованих систем"), None, 10)
    assert "Сертифікатна програма" in text


def test_digest_prefers_the_short_title_to_stay_scannable():
    view = make_view(short="QA вбудованих систем")
    text = render_digest(dt.date(2026, 8, 31), 1, [view])
    assert "QA вбудованих систем" in text
    assert "Сертифікатна програма" not in text


def test_digest_header_names_the_weekday_and_parity():
    text = render_digest(dt.date(2026, 8, 31), 1, [make_view()])
    assert "понеділок" in text
    assert "1 тиждень" in text


def test_empty_day_is_reported_as_a_free_day():
    text = render_day(dt.date(2026, 9, 4), 1, [])
    assert "пар немає" in text


def test_changes_message_marks_removals_and_additions():
    removed = make_view("Технології інтернет речей", start=dt.time(10, 25), day=2)
    added = make_view("Технології інтернет речей", start=dt.time(14, 15), day=3, type_="Лаб")
    text = render_changes([added], [removed])
    assert "➖ Ср 10:25" in text
    assert "➕ Чт 14:15" in text


def test_pair_grid_is_ninety_five_minutes():
    assert time_range(dt.time(8, 30)) == "08:30 – 10:05"
    assert time_range(dt.time(16, 10)) == "16:10 – 17:45"
