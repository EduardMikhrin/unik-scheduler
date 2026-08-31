"""Per-minute tick that fires the "pair starts in N minutes" reminders.

A single tick is cheaper than one scheduler job per lesson per user, and it
survives restarts: the notification log, not scheduler state, decides whether a
reminder already went out.
"""

from __future__ import annotations

import datetime as dt
import logging

from aiogram import Bot
from sqlalchemy import select

from unik_scheduler.bot.formatting import LessonView, render_reminder
from unik_scheduler.bot.keyboards import lesson_links
from unik_scheduler.config import Settings
from unik_scheduler.db.models import Lesson, Subject
from unik_scheduler.db.queries import (
    active_users,
    lessons_for_day,
    mark_sent,
    visible_subject_ids,
    week_of,
)
from unik_scheduler.db.session import session_scope
from unik_scheduler.jobs.delivery import send_safely

log = logging.getLogger(__name__)


async def tick(bot: Bot, settings: Settings) -> int:
    now = dt.datetime.now(settings.timezone)
    target = (now + dt.timedelta(minutes=settings.reminder_lead_minutes)).replace(
        second=0, microsecond=0
    )
    today = now.date()

    async with session_scope() as session:
        week = await week_of(session, today)
        if week is None:
            return 0

        rows = await session.execute(
            select(Lesson, Subject)
            .join(Subject, Subject.id == Lesson.subject_id)
            .where(
                Lesson.week == week,
                Lesson.day == today.weekday(),
                Lesson.start == dt.time(target.hour, target.minute),
            )
        )
        starting = [
            LessonView(lesson, subject)
            for lesson, subject in rows.all()
            if not lesson.only_dates or today in lesson.only_dates
        ]
        if not starting:
            return 0

        by_subject = {view.subject.id: view for view in starting if view.subject}
        semester = settings.resolve_semester(today)
        sent = 0

        for user in await active_users(session):
            if not user.reminders_enabled:
                continue
            subject_ids = await visible_subject_ids(session, user.id, semester)
            mine = [view for sid, view in by_subject.items() if sid in subject_ids]
            if not mine:
                continue

            day_plan = await lessons_for_day(session, subject_ids, week, today)
            for view in mine:
                key = f"{today.isoformat()}|{view.lesson.id}"
                if not await mark_sent(session, user.id, "reminder", key):
                    continue  # already delivered, e.g. before a restart
                following = _next_after(day_plan, view)
                delivered = await send_safely(
                    bot,
                    session,
                    user,
                    render_reminder(view, following, settings.reminder_lead_minutes),
                    reply_markup=lesson_links(view.subject, view.lesson.tag),
                )
                sent += int(delivered)

    if sent:
        log.info("sent %d reminder(s) for %s", sent, target.strftime("%H:%M"))
    return sent


def _next_after(day_plan: list[LessonView], current: LessonView) -> LessonView | None:
    later = [v for v in day_plan if v.start > current.start]
    return min(later, key=lambda v: v.start) if later else None
