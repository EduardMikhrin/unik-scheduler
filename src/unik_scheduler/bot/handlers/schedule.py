from __future__ import annotations

import datetime as dt

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from unik_scheduler.bot.formatting import render_day, render_next, render_week
from unik_scheduler.bot.keyboards import lesson_links
from unik_scheduler.config import get_settings
from unik_scheduler.db.models import User
from unik_scheduler.db.queries import (
    lessons_for_day,
    lessons_for_week,
    visible_subject_ids,
    week_of,
)

router = Router(name="schedule")

NO_SCHEDULE = "Розклад ще не завантажено. Адміністратор має виконати /sync."


async def _day_reply(
    message: Message, session: AsyncSession, user: User, day: dt.date, *, tomorrow: bool
) -> None:
    settings = get_settings()
    week = await week_of(session, day)
    if week is None:
        await message.answer(NO_SCHEDULE)
        return
    subject_ids = await visible_subject_ids(session, user.id, settings.resolve_semester(day))
    views = await lessons_for_day(session, subject_ids, week, day)
    await message.answer(render_day(day, week, views, tomorrow=tomorrow))


@router.message(Command("today"))
async def cmd_today(message: Message, session: AsyncSession, user: User) -> None:
    today = dt.datetime.now(get_settings().timezone).date()
    await _day_reply(message, session, user, today, tomorrow=False)


@router.message(Command("tomorrow"))
async def cmd_tomorrow(message: Message, session: AsyncSession, user: User) -> None:
    tomorrow = dt.datetime.now(get_settings().timezone).date() + dt.timedelta(days=1)
    await _day_reply(message, session, user, tomorrow, tomorrow=True)


@router.message(Command("week"))
async def cmd_week(message: Message, session: AsyncSession, user: User) -> None:
    settings = get_settings()
    today = dt.datetime.now(settings.timezone).date()
    week = await week_of(session, today)
    if week is None:
        await message.answer(NO_SCHEDULE)
        return
    subject_ids = await visible_subject_ids(session, user.id, settings.resolve_semester(today))
    by_day = await lessons_for_week(session, subject_ids, week)
    await message.answer(render_week(week, by_day))


@router.message(Command("next"))
async def cmd_next(message: Message, session: AsyncSession, user: User) -> None:
    settings = get_settings()
    now = dt.datetime.now(settings.timezone)
    subject_ids = await visible_subject_ids(session, user.id, settings.resolve_semester(now.date()))

    # Walk forward up to two full weeks — beyond that the parity repeats anyway.
    for offset in range(15):
        day = now.date() + dt.timedelta(days=offset)
        week = await week_of(session, day)
        if week is None:
            await message.answer(NO_SCHEDULE)
            return
        for view in await lessons_for_day(session, subject_ids, week, day):
            if offset == 0 and view.start <= now.time():
                continue
            when = {0: "сьогодні", 1: "завтра"}.get(offset, day.strftime("%d.%m"))
            await message.answer(
                render_next(view, when),
                reply_markup=lesson_links(view.subject, view.lesson.tag),
            )
            return
    await message.answer("Найближчим часом пар немає 🎉")
