"""Daily pull of the group timetable, plus change detection."""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.utils.text_decorations import html_decoration as fmt
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from unik_scheduler.bot.formatting import LessonView, render_changes
from unik_scheduler.catalog.linking import LinkReport, relink_lessons
from unik_scheduler.config import Settings
from unik_scheduler.db.models import Lesson, Subject
from unik_scheduler.db.queries import active_users, admins, set_state, visible_subject_ids
from unik_scheduler.db.session import session_scope
from unik_scheduler.jobs.delivery import send_safely
from unik_scheduler.kpi.client import ApiLesson, KpiApiError, KpiClient
from unik_scheduler.kpi.weeks import ANCHOR_DATE_KEY, ANCHOR_WEEK_KEY

log = logging.getLogger(__name__)


@dataclass
class SyncReport:
    added: int = 0
    removed: int = 0
    updated: int = 0
    total: int = 0
    link: LinkReport = field(default_factory=LinkReport)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def _slot_of(lesson: Lesson) -> tuple[int, int, dt.time, str, str]:
    return (lesson.week, lesson.day, lesson.start, lesson.raw_name, lesson.type)


async def sync_schedule(bot: Bot, settings: Settings, *, notify: bool = True) -> SyncReport:
    client = KpiClient(settings.lessons_url, settings.current_time_url)
    try:
        api_lessons = await client.fetch_lessons()
        current_week = await client.fetch_current_week()
    except KpiApiError as exc:
        log.error("schedule sync failed: %s", exc)
        return SyncReport(error=str(exc))

    today = dt.datetime.now(settings.timezone).date()
    semester = settings.resolve_semester(today)

    async with session_scope() as session:
        await set_state(session, ANCHOR_DATE_KEY, today.isoformat())
        await set_state(session, ANCHOR_WEEK_KEY, str(current_week))

        report, added_views, removed_views = await _apply(session, api_lessons, semester)
        if notify and (added_views or removed_views):
            await _notify_changes(bot, session, added_views, removed_views, semester)
        if notify and report.link.unmatched:
            await _notify_admins_unmatched(bot, session, report.link)

    log.info(
        "sync: %d lessons (+%d / -%d / ~%d), %d unmatched",
        report.total,
        report.added,
        report.removed,
        report.updated,
        len(report.link.unmatched),
    )
    return report


async def _apply(
    session: AsyncSession, api_lessons: list[ApiLesson], semester: int
) -> tuple[SyncReport, list[LessonView], list[LessonView]]:
    existing = {
        _slot_of(lesson): lesson
        for lesson in (await session.execute(select(Lesson))).scalars().all()
    }
    incoming = {lesson.slot: lesson for lesson in api_lessons}

    report = SyncReport(total=len(incoming))
    removed_views: list[LessonView] = []
    added_views: list[LessonView] = []

    gone = [existing[slot] for slot in existing.keys() - incoming.keys()]
    for lesson in gone:
        subject = await session.get(Subject, lesson.subject_id) if lesson.subject_id else None
        removed_views.append(LessonView(lesson, subject))
    if gone:
        await session.execute(delete(Lesson).where(Lesson.id.in_([lesson.id for lesson in gone])))
        report.removed = len(gone)

    inserted: list[Lesson] = []
    for slot in incoming.keys() - existing.keys():
        api_lesson = incoming[slot]
        lesson = Lesson(
            week=api_lesson.week,
            day=api_lesson.day,
            start=api_lesson.start,
            raw_name=api_lesson.name,
            type=api_lesson.type,
            tag=api_lesson.tag,
            lecturer=api_lesson.lecturer,
            only_dates=list(api_lesson.only_dates) or None,
        )
        session.add(lesson)
        inserted.append(lesson)
        report.added += 1

    # Same slot, different details (a lecturer swap, dates narrowed) — update quietly.
    for slot in incoming.keys() & existing.keys():
        api_lesson, lesson = incoming[slot], existing[slot]
        new_dates = list(api_lesson.only_dates) or None
        if lesson.lecturer != api_lesson.lecturer or lesson.only_dates != new_dates:
            lesson.lecturer = api_lesson.lecturer
            lesson.only_dates = new_dates
            report.updated += 1

    await session.flush()
    report.link = await relink_lessons(session, semester)
    await session.flush()

    # Newly inserted rows only get their subject after relinking.
    if inserted:
        fresh = await session.execute(
            select(Lesson, Subject)
            .outerjoin(Subject, Subject.id == Lesson.subject_id)
            .where(Lesson.id.in_([lesson.id for lesson in inserted]))
        )
        added_views = [LessonView(lesson, subject) for lesson, subject in fresh.all()]
    return report, added_views, removed_views


async def _notify_changes(
    bot: Bot,
    session: AsyncSession,
    added: list[LessonView],
    removed: list[LessonView],
    semester: int,
) -> None:
    for user in await active_users(session):
        if not user.changes_enabled:
            continue
        subject_ids = await visible_subject_ids(session, user.id, semester)
        mine_added = [v for v in added if v.subject and v.subject.id in subject_ids]
        mine_removed = [v for v in removed if v.subject and v.subject.id in subject_ids]
        if not mine_added and not mine_removed:
            continue
        await send_safely(bot, session, user, render_changes(mine_added, mine_removed))


async def _notify_admins_unmatched(bot: Bot, session: AsyncSession, link: LinkReport) -> None:
    lines = ["⚠️ <b>Предмети з розкладу, які не збіглися з каталогом</b>", ""]
    for raw_name, suggestion in link.unmatched:
        lines.append(f"• <code>{fmt.quote(raw_name)}</code>")
        if suggestion:
            lines.append(f"  схоже на: <i>{fmt.quote(suggestion)}</i>")
    lines.append("")
    lines.append("Додай <code>api_alias</code> у каталог і надішли файл знову.")
    text = "\n".join(lines)
    for admin in await admins(session):
        await send_safely(bot, session, admin, text)
