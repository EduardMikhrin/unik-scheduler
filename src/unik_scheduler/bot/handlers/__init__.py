from aiogram import Router

from unik_scheduler.bot.handlers import admin, common, electives, schedule, settings


def build_router() -> Router:
    router = Router(name="root")
    router.include_router(common.router)
    router.include_router(schedule.router)
    router.include_router(electives.router)
    router.include_router(settings.router)
    router.include_router(admin.router)
    return router
