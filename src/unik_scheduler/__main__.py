from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func, select

from unik_scheduler.bot.handlers import build_router
from unik_scheduler.bot.middlewares import DbSessionMiddleware
from unik_scheduler.config import Settings, get_settings
from unik_scheduler.db.models import Lesson, User
from unik_scheduler.db.session import create_schema, dispose_engine, init_engine, session_scope
from unik_scheduler.jobs.digest import send_daily_digest
from unik_scheduler.jobs.reminders import tick as reminder_tick
from unik_scheduler.jobs.sync import sync_schedule

log = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="today", description="Пари на сьогодні"),
    BotCommand(command="tomorrow", description="Пари на завтра"),
    BotCommand(command="week", description="Розклад на тиждень"),
    BotCommand(command="next", description="Найближча пара"),
    BotCommand(command="electives", description="Вибіркові предмети"),
    BotCommand(command="settings", description="Сповіщення"),
    BotCommand(command="help", description="Довідка"),
]


async def _bootstrap_owner(settings: Settings) -> None:
    if not settings.initial_admin_id:
        log.warning("INITIAL_ADMIN_ID is not set — nobody can administer the bot yet")
        return
    async with session_scope() as session:
        owner = await session.get(User, settings.initial_admin_id)
        if owner is None:
            session.add(User(id=settings.initial_admin_id, full_name="owner", is_admin=True))
        else:
            owner.is_admin = True


async def _sync_if_empty(bot: Bot, settings: Settings) -> None:
    async with session_scope() as session:
        stored = await session.scalar(select(func.count()).select_from(Lesson))
    if stored:
        return
    log.info("no timetable stored yet — running an initial sync")
    # Nothing to compare against, so a first sync must not report "changes".
    await sync_schedule(bot, settings, notify=False)


def _schedule_jobs(scheduler: AsyncIOScheduler, bot: Bot, settings: Settings) -> None:
    timezone = settings.timezone
    scheduler.add_job(
        reminder_tick,
        CronTrigger(minute="*", timezone=timezone),
        args=(bot, settings),
        id="reminders",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=60,
    )
    scheduler.add_job(
        send_daily_digest,
        CronTrigger(
            hour=settings.digest_time.hour, minute=settings.digest_time.minute, timezone=timezone
        ),
        args=(bot, settings),
        id="digest",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    scheduler.add_job(
        sync_schedule,
        CronTrigger(
            hour=settings.sync_time.hour, minute=settings.sync_time.minute, timezone=timezone
        ),
        args=(bot, settings),
        id="sync",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)

    init_engine(settings.database_url)
    await create_schema()
    await _bootstrap_owner(settings)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    middleware = DbSessionMiddleware(settings.initial_admin_id)
    dispatcher.message.outer_middleware(middleware)
    dispatcher.callback_query.outer_middleware(middleware)
    dispatcher.include_router(build_router())

    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    _schedule_jobs(scheduler, bot, settings)

    await _sync_if_empty(bot, settings)
    await bot.set_my_commands(COMMANDS)
    scheduler.start()
    log.info("bot started for group %s", settings.kpi_group_id)

    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        await dispose_engine()


def run() -> None:
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("shutting down")


if __name__ == "__main__":
    run()
