from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from unik_scheduler.db.models import User

log = logging.getLogger(__name__)

# Telegram tolerates ~30 messages/second to distinct chats; stay well under it.
_SEND_PAUSE = 0.05


async def send_safely(
    bot: Bot,
    session: AsyncSession,
    user: User,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    """Send a broadcast-style message, tolerating the two failures that matter.

    A user who blocked the bot is flagged so later runs skip them; a flood wait
    is honoured once rather than dropped.
    """
    try:
        await bot.send_message(user.id, text, reply_markup=reply_markup)
    except TelegramRetryAfter as exc:
        log.warning("flood wait %ss for user %s", exc.retry_after, user.id)
        await asyncio.sleep(exc.retry_after)
        try:
            await bot.send_message(user.id, text, reply_markup=reply_markup)
        except Exception:
            log.exception("giving up on user %s after flood wait", user.id)
            return False
    except TelegramForbiddenError:
        log.info("user %s blocked the bot — muting", user.id)
        user.is_blocked = True
        await session.flush()
        return False
    except Exception:
        log.exception("failed to deliver a message to user %s", user.id)
        return False
    await asyncio.sleep(_SEND_PAUSE)
    return True
