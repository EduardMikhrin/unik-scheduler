"""Parsing of the real KPI payload, quirks included."""

from __future__ import annotations

import datetime as dt

import pytest

from unik_scheduler.kpi.client import KpiApiError, parse_lessons


def test_parses_both_weeks(schedule_payload: dict):
    lessons = parse_lessons(schedule_payload)
    assert {lesson.week for lesson in lessons} == {1, 2}


def test_tuesday_is_spelled_vv_by_the_api(schedule_payload: dict):
    lessons = parse_lessons(schedule_payload)
    tuesdays = [lesson for lesson in lessons if lesson.day == 1]
    assert tuesdays, "the fixture has Tuesday pairs labelled 'Вв'"


def test_lesson_with_explicit_dates_keeps_them(schedule_payload: dict):
    lessons = parse_lessons(schedule_payload)
    dated = [lesson for lesson in lessons if lesson.only_dates]
    assert dated, "fixture contains a date-restricted lesson"
    assert all(isinstance(day, dt.date) for lesson in dated for day in lesson.only_dates)


def test_most_lessons_have_no_date_restriction(schedule_payload: dict):
    lessons = parse_lessons(schedule_payload)
    assert any(lesson.only_dates == () for lesson in lessons)


def test_slot_identity_ignores_lecturer(schedule_payload: dict):
    lessons = parse_lessons(schedule_payload)
    first = lessons[0]
    assert first.slot == (first.week, first.day, first.start, first.name, first.type)


def test_empty_schedule_is_refused_rather_than_wiping_the_timetable():
    with pytest.raises(KpiApiError):
        parse_lessons({"scheduleFirstWeek": [], "scheduleSecondWeek": []})


def test_pair_without_a_time_is_skipped():
    payload = {
        "scheduleFirstWeek": [
            {"day": "Пн", "pairs": [{"name": "Ok", "time": "08:30:00", "type": "Лек", "tag": "lec"},
                                     {"name": "Broken", "time": None, "type": "Лек", "tag": "lec"}]}
        ],
        "scheduleSecondWeek": [],
    }
    lessons = parse_lessons(payload)
    assert [lesson.name for lesson in lessons] == ["Ok"]


def test_unknown_day_label_is_skipped_not_fatal():
    pair = {"name": "X", "time": "08:30:00", "type": "Лек", "tag": "lec"}
    payload = {
        "scheduleFirstWeek": [
            {"day": "Хз", "pairs": [pair]},
            {"day": "Пн", "pairs": [dict(pair, name="Y")]},
        ],
        "scheduleSecondWeek": [],
    }
    assert [lesson.name for lesson in parse_lessons(payload)] == ["Y"]
