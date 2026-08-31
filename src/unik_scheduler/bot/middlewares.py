from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from aiogram.types import User as TgUser

from unik_scheduler.db.queries import get_or_create_user
from unik_scheduler.db.session import session_scope

log = logging.getLogger(__name__)


class DbSessionMiddleware(BaseMiddleware):
    """Opens one transaction per update and resolves the Telegram user into a row."""

    def __init__(self, initial_admin_id: int) -> None:
        self._initial_admin_id = initial_admin_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user is None or tg_user.is_bot:
            return None

        async with session_scope() as session:
            user, created = await get_or_create_user(
                session,
                user_id=tg_user.id,
                username=tg_user.username,
                full_name=tg_user.full_name,
            )
            # The owner configured in .env is always an admin, even after a wipe.
            if self._initial_admin_id and tg_user.id == self._initial_admin_id:
                user.is_admin = True
            if created:
                log.info("new user %s (%s)", tg_user.id, tg_user.username)
            data["session"] = session
            data["user"] = user
            return await handler(event, data)
