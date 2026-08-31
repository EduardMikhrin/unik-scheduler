from __future__ import annotations

import datetime as dt

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.text_decorations import html_decoration as fmt
from sqlalchemy.ext.asyncio import AsyncSession

from unik_scheduler.bot.callbacks import ElectiveCB
from unik_scheduler.bot.keyboards import component_menu, component_subjects
from unik_scheduler.config import get_settings
from unik_scheduler.db.models import Subject, User
from unik_scheduler.db.queries import (
    electives_for_semester,
    selected_elective_ids,
    toggle_elective,
)

router = Router(name="electives")

NO_CATALOG = (
    "Каталог предметів ще не завантажено.\n"
    "Адміністратор має надіслати боту файл <code>electives.json</code>."
)


def _current_semester() -> int:
    settings = get_settings()
    return settings.resolve_semester(dt.datetime.now(settings.timezone).date())


def _components(subjects: list[Subject]) -> list[str]:
    return sorted({s.component or "—" for s in subjects})


def _counts(subjects: list[Subject], selected: set[int]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for subject in subjects:
        if subject.id in selected:
            key = subject.component or "—"
            counts[key] = counts.get(key, 0) + 1
    return counts


def _menu_text(semester: int, subjects: list[Subject], selected: set[int]) -> str:
    chosen = sum(1 for s in subjects if s.id in selected)
    return (
        f"🎯 <b>Вибіркові предмети</b> · {semester} семестр\n\n"
        f"Обрано {chosen} з {len(_components(subjects))} компонентів "
        "(за правилом — по одному з кожного).\n"
        "Нормативні предмети додаються автоматично."
    )


@router.message(Command("electives"))
async def cmd_electives(message: Message, session: AsyncSession, user: User) -> None:
    semester = _current_semester()
    subjects = await electives_for_semester(session, semester)
    if not subjects:
        await message.answer(NO_CATALOG)
        return
    selected = await selected_elective_ids(session, user.id)
    await message.answer(
        _menu_text(semester, subjects, selected),
        reply_markup=component_menu(_components(subjects), _counts(subjects, selected)),
    )


@router.callback_query(ElectiveCB.filter(F.action == "component"))
async def show_component(
    query: CallbackQuery, callback_data: ElectiveCB, session: AsyncSession, user: User
) -> None:
    subjects = await electives_for_semester(session, _current_semester())
    selected = await selected_elective_ids(session, user.id)
    in_component = [s for s in subjects if (s.component or "—") == callback_data.component]
    await query.message.edit_text(
        f"🎯 Компонент <b>{callback_data.component}</b>\n\nНатисни, щоб обрати або зняти вибір.",
        reply_markup=component_subjects(callback_data.component, in_component, selected),
    )
    await query.answer()


@router.callback_query(ElectiveCB.filter(F.action == "toggle"))
async def toggle(
    query: CallbackQuery, callback_data: ElectiveCB, session: AsyncSession, user: User
) -> None:
    added = await toggle_elective(session, user.id, callback_data.subject_id)
    await session.flush()

    subjects = await electives_for_semester(session, _current_semester())
    selected = await selected_elective_ids(session, user.id)
    in_component = [s for s in subjects if (s.component or "—") == callback_data.component]
    await query.message.edit_reply_markup(
        reply_markup=component_subjects(callback_data.component, in_component, selected)
    )
    await query.answer("Додано ✅" if added else "Прибрано ⬜")


@router.callback_query(ElectiveCB.filter(F.action == "back"))
async def back_to_menu(query: CallbackQuery, session: AsyncSession, user: User) -> None:
    semester = _current_semester()
    subjects = await electives_for_semester(session, semester)
    selected = await selected_elective_ids(session, user.id)
    await query.message.edit_text(
        _menu_text(semester, subjects, selected),
        reply_markup=component_menu(_components(subjects), _counts(subjects, selected)),
    )
    await query.answer()


@router.callback_query(ElectiveCB.filter(F.action == "done"))
async def done(query: CallbackQuery, session: AsyncSession, user: User) -> None:
    subjects = await electives_for_semester(session, _current_semester())
    selected = await selected_elective_ids(session, user.id)
    chosen = [s for s in subjects if s.id in selected]
    if not chosen:
        await query.message.edit_text("Нічого не обрано. Повернутися — /electives")
    else:
        lines = "\n".join(
            f"• {fmt.quote(s.display_name)} <i>({s.component or '—'})</i>" for s in chosen
        )
        await query.message.edit_text(f"✅ <b>Твої вибіркові:</b>\n{lines}")
    await query.answer()
