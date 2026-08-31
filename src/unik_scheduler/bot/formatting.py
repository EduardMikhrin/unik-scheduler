"""Rendering of the user-facing messages. All copy is Ukrainian.

Course titles contain `&` (e.g. "ESI&IoT") and angle-quote characters, so every
interpolated value goes through html.quote — the bot sends parse_mode=HTML.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from aiogram.utils.text_decorations import html_decoration as fmt

from unik_scheduler.db.models import Lesson, Subject
from unik_scheduler.kpi.constants import (
    DAY_NAMES_UK,
    DAY_SHORT_UK,
    TYPE_EMOJI,
    TYPE_LABEL_UK,
    lesson_end,
)


@dataclass(frozen=True)
class LessonView:
    lesson: Lesson
    subject: Subject | None

    @property
    def title(self) -> str:
        if self.subject is not None:
            return self.subject.display_name
        return self.lesson.raw_name

    @property
    def full_title(self) -> str:
        return self.subject.name if self.subject is not None else self.lesson.raw_name

    @property
    def start(self) -> dt.time:
        return self.lesson.start


def hhmm(value: dt.time) -> str:
    return value.strftime("%H:%M")


def time_range(start: dt.time) -> str:
    return f"{hhmm(start)} – {hhmm(lesson_end(start))}"


def type_label(tag: str, fallback: str) -> str:
    return TYPE_LABEL_UK.get(tag, fallback or "Заняття")


def render_reminder(view: LessonView, following: LessonView | None, lead_minutes: int) -> str:
    lesson = view.lesson
    emoji = TYPE_EMOJI.get(lesson.tag, "📘")
    lines = [
        f"⏰ Пара через {lead_minutes} хвилин",
        "",
        f"{emoji} {fmt.bold(fmt.quote(view.full_title))}",
        f"🎓 {type_label(lesson.tag, lesson.type)} · {time_range(lesson.start)}",
    ]
    if lesson.lecturer:
        lines.append(f"👤 {fmt.quote(lesson.lecturer)}")
    lines.append("")
    if following is None:
        lines.append("Це остання пара сьогодні 🎉")
    else:
        next_type = following.lesson.type or type_label(following.lesson.tag, "")
        lines.append(
            f"Далі сьогодні: {hhmm(following.start)} · "
            f"{fmt.quote(following.title)} ({fmt.quote(next_type)})"
        )
    return "\n".join(lines)


def render_digest(day: dt.date, week: int, views: list[LessonView]) -> str:
    header = f"📅 Сьогодні, {DAY_NAMES_UK[day.weekday()]} · {week} тиждень"
    lines = [header, ""]
    for view in views:
        lines.append(
            f"{hhmm(view.start)} {fmt.quote(view.lesson.type)} · {fmt.quote(view.title)}"
        )
    return "\n".join(lines)


def render_day(day: dt.date, week: int, views: list[LessonView], *, tomorrow: bool = False) -> str:
    label = "Завтра" if tomorrow else "Сьогодні"
    if not views:
        return f"📅 {label}, {DAY_NAMES_UK[day.weekday()]} · пар немає 🎉"
    header = f"📅 {label}, {DAY_NAMES_UK[day.weekday()]} · {week} тиждень"
    lines = [header, ""]
    for view in views:
        lines.append(
            f"{fmt.bold(time_range(view.start))}\n"
            f"{TYPE_EMOJI.get(view.lesson.tag, '📘')} {fmt.quote(view.title)} "
            f"({fmt.quote(view.lesson.type)})"
        )
    return "\n\n".join([lines[0], *lines[2:]])


def render_week(week: int, views_by_day: dict[int, list[LessonView]]) -> str:
    if not any(views_by_day.values()):
        return f"📅 {week} тиждень · у тебе немає жодної пари."
    blocks = [f"📅 Розклад · {week} тиждень"]
    for day_index in sorted(views_by_day):
        views = views_by_day[day_index]
        if not views:
            continue
        rows = [
            f"  {hhmm(v.start)} {fmt.quote(v.lesson.type)} · {fmt.quote(v.title)}" for v in views
        ]
        blocks.append(fmt.bold(DAY_NAMES_UK[day_index].capitalize()) + "\n" + "\n".join(rows))
    return "\n\n".join(blocks)


def render_next(view: LessonView, when: str) -> str:
    return (
        f"⏭ Найближча пара — {when} о {hhmm(view.start)}\n\n"
        f"{TYPE_EMOJI.get(view.lesson.tag, '📘')} {fmt.bold(fmt.quote(view.full_title))}\n"
        f"{type_label(view.lesson.tag, view.lesson.type)} · {time_range(view.start)}"
    )


def render_changes(added: list[LessonView], removed: list[LessonView]) -> str:
    lines = ["🔄 Розклад змінився", ""]
    for view in removed:
        lines.append(
            f"➖ {DAY_SHORT_UK[view.lesson.day]} {hhmm(view.start)} · "
            f"{fmt.quote(view.title)} ({fmt.quote(view.lesson.type)})"
        )
    for view in added:
        lines.append(
            f"➕ {DAY_SHORT_UK[view.lesson.day]} {hhmm(view.start)} · "
            f"{fmt.quote(view.title)} ({fmt.quote(view.lesson.type)})"
        )
    return "\n".join(lines)
