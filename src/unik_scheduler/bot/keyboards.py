from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from unik_scheduler.bot.callbacks import ElectiveCB, SettingsCB
from unik_scheduler.db.models import Subject, User


def lesson_links(subject: Subject | None, tag: str) -> InlineKeyboardMarkup | None:
    """Chat and conference buttons — shown only for links that are actually filled."""
    if subject is None:
        return None
    buttons: list[InlineKeyboardButton] = []
    if subject.chat_url:
        buttons.append(InlineKeyboardButton(text="💬 Чат предмета", url=subject.chat_url))
    conference = subject.conference_for(tag)
    if conference:
        buttons.append(InlineKeyboardButton(text="🎥 Конференція", url=conference))
    if not buttons:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def component_menu(
    components: list[str], counts: dict[str, int], expected: int = 1
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for component in components:
        chosen = counts.get(component, 0)
        mark = "✅" if chosen == expected else ("⚠️" if chosen else "▫️")
        builder.button(
            text=f"{mark} {component} · обрано {chosen}",
            callback_data=ElectiveCB(action="component", component=component),
        )
    builder.button(text="✔️ Готово", callback_data=ElectiveCB(action="done"))
    builder.adjust(1)
    return builder.as_markup()


def component_subjects(
    component: str, subjects: list[Subject], selected: set[int]
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for subject in subjects:
        mark = "✅" if subject.id in selected else "⬜"
        title = subject.display_name
        if len(title) > 55:
            title = title[:52] + "…"
        builder.button(
            text=f"{mark} {title}",
            callback_data=ElectiveCB(action="toggle", component=component, subject_id=subject.id),
        )
    builder.button(text="⬅️ До компонентів", callback_data=ElectiveCB(action="back"))
    builder.adjust(1)
    return builder.as_markup()


def settings_menu(user: User) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    rows = (
        ("reminders", "Нагадування за 10 хв", user.reminders_enabled),
        ("digest", "Ранкова зведення", user.digest_enabled),
        ("changes", "Зміни в розкладі", user.changes_enabled),
    )
    for field, label, enabled in rows:
        builder.button(
            text=f"{'🔔' if enabled else '🔕'} {label}",
            callback_data=SettingsCB(field=field),
        )
    builder.adjust(1)
    return builder.as_markup()
