"""Morning summary of the day's pairs, sent only on days that have any."""

from __future__ import annotations

import datetime as dt
import logging

from aiogram import Bot

from unik_scheduler.bot.formatting import render_digest
from unik_scheduler.config import Settings
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


async def send_daily_digest(bot: Bot, settings: Settings) -> int:
    today = dt.datetime.now(settings.timezone).date()
    semester = settings.resolve_semester(today)
    sent = 0

    async with session_scope() as session:
        week = await week_of(session, today)
        if week is None:
            log.warning("no week anchor yet — skipping digest")
            return 0

        for user in await active_users(session):
            if not user.digest_enabled:
                continue
            subject_ids = await visible_subject_ids(session, user.id, semester)
            views = await lessons_for_day(session, subject_ids, week, today)
            if not views:
                continue
            if not await mark_sent(session, user.id, "digest", today.isoformat()):
                continue
            sent += int(await send_safely(bot, session, user, render_digest(today, week, views)))

    log.info("digest sent to %d user(s)", sent)
    return sent
