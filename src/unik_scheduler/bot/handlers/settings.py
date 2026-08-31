from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from unik_scheduler.bot.callbacks import SettingsCB
from unik_scheduler.bot.keyboards import settings_menu
from unik_scheduler.config import get_settings
from unik_scheduler.db.models import User

router = Router(name="settings")

_FIELDS = {
    "reminders": "reminders_enabled",
    "digest": "digest_enabled",
    "changes": "changes_enabled",
}


def _text() -> str:
    lead = get_settings().reminder_lead_minutes
    digest = get_settings().digest_time.strftime("%H:%M")
    return (
        "🔔 <b>Сповіщення</b>\n\n"
        f"• Нагадування — за {lead} хв до пари\n"
        f"• Ранкове зведення — о {digest}\n"
        "• Зміни в розкладі — коли КПІ щось переносить\n\n"
        "Натисни, щоб увімкнути або вимкнути."
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message, user: User) -> None:
    await message.answer(_text(), reply_markup=settings_menu(user))


@router.callback_query(SettingsCB.filter())
async def toggle_setting(
    query: CallbackQuery, callback_data: SettingsCB, session: AsyncSession, user: User
) -> None:
    field = _FIELDS.get(callback_data.field)
    if field is None:
        await query.answer()
        return
    setattr(user, field, not getattr(user, field))
    await session.flush()
    await query.message.edit_reply_markup(reply_markup=settings_menu(user))
    await query.answer("Увімкнено" if getattr(user, field) else "Вимкнено")
