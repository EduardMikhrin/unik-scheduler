from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Document, Message
from aiogram.utils.text_decorations import html_decoration as fmt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from unik_scheduler.bot.filters import IsAdmin
from unik_scheduler.catalog.exporter import export_catalog
from unik_scheduler.catalog.importer import CatalogError, ImportReport, import_catalog
from unik_scheduler.config import get_settings
from unik_scheduler.db.models import Subject, User, UserSubject
from unik_scheduler.db.queries import admins, find_user_by_username
from unik_scheduler.jobs.sync import sync_schedule

router = Router(name="admin")

MAX_CATALOG_BYTES = 2 * 1024 * 1024

PANEL = (
    "🛠 <b>Адмінка</b>\n\n"
    "<b>Каталог</b>\n"
    "Надішли боту файл <code>.json</code> — він оновить каталог предметів.\n"
    "/export — вивантажити поточний каталог файлом\n\n"
    "<b>Розклад</b>\n"
    "/sync — підтягнути розклад з КПІ просто зараз\n\n"
    "<b>Права</b>\n"
    "/grant <code>id | @username</code> — видати права адміна\n"
    "/revoke <code>id | @username</code> — забрати права\n"
    "/admins — список адмінів\n\n"
    "/stats — коротка статистика"
)


def _who(user: User) -> str:
    label = f"@{user.username}" if user.username else (user.full_name or "без імені")
    return f"{fmt.quote(label)} (<code>{user.id}</code>)"


async def _resolve_target(session: AsyncSession, raw: str, *, create_missing: bool) -> User | None:
    raw = raw.strip()
    if raw.startswith("@"):
        return await find_user_by_username(session, raw)
    if not raw.lstrip("-").isdigit():
        return None
    target = await session.get(User, int(raw))
    if target is None and create_missing:
        # Lets an admin be appointed before they ever open the bot.
        target = User(id=int(raw), username=None, full_name="")
        session.add(target)
        await session.flush()
    return target


@router.message(Command("admin"), IsAdmin())
async def cmd_admin(message: Message) -> None:
    await message.answer(PANEL)


@router.message(Command("grant"), IsAdmin())
async def cmd_grant(message: Message, command: CommandObject, session: AsyncSession) -> None:
    if not command.args:
        await message.answer(
            "Вкажи кого: <code>/grant 123456789</code> або <code>/grant @nick</code>"
        )
        return
    target = await _resolve_target(session, command.args, create_missing=True)
    if target is None:
        await message.answer(
            "Не знайшов такого користувача. За @username я знаходжу лише тих, "
            "хто вже запускав бота — інакше передай числовий id."
        )
        return
    if target.is_admin:
        await message.answer(f"{_who(target)} — вже адмін.")
        return
    target.is_admin = True
    await session.flush()
    await message.answer(f"✅ {_who(target)} тепер адміністратор.")


@router.message(Command("revoke"), IsAdmin())
async def cmd_revoke(
    message: Message, command: CommandObject, session: AsyncSession, user: User
) -> None:
    if not command.args:
        await message.answer("Вкажи кого: <code>/revoke 123456789</code>")
        return
    target = await _resolve_target(session, command.args, create_missing=False)
    if target is None or not target.is_admin:
        await message.answer("Такого адміна немає.")
        return
    if target.id == get_settings().initial_admin_id:
        await message.answer("Власника бота (INITIAL_ADMIN_ID) розжалувати не можна.")
        return
    if target.id == user.id:
        await message.answer("Себе розжалувати не можна — попроси іншого адміна.")
        return
    target.is_admin = False
    await session.flush()
    await message.answer(f"🚫 {_who(target)} більше не адміністратор.")


@router.message(Command("admins"), IsAdmin())
async def cmd_admins(message: Message, session: AsyncSession) -> None:
    rows = await admins(session)
    owner = get_settings().initial_admin_id
    lines = [f"• {_who(admin)}" + (" — власник" if admin.id == owner else "") for admin in rows]
    await message.answer("👑 <b>Адміністратори</b>\n" + "\n".join(lines))


@router.message(Command("sync"), IsAdmin())
async def cmd_sync(message: Message, bot: Bot) -> None:
    notice = await message.answer("Тягну розклад з КПІ…")
    report = await sync_schedule(bot, get_settings())
    if not report.ok:
        await notice.edit_text(f"❌ Не вдалося: {fmt.quote(report.error or '')}")
        return
    text = (
        f"✅ Розклад оновлено: {report.total} пар\n"
        f"додано {report.added}, прибрано {report.removed}, змінено {report.updated}"
    )
    if report.link.unmatched:
        text += f"\n⚠️ Не збіглося з каталогом: {len(report.link.unmatched)}"
    await notice.edit_text(text)


@router.message(Command("export"), IsAdmin())
async def cmd_export(message: Message, session: AsyncSession) -> None:
    payload = await export_catalog(session)
    if payload.strip() in (b"", b"{}"):
        await message.answer("Каталог порожній — нема чого вивантажувати.")
        return
    await message.answer_document(
        BufferedInputFile(payload, filename="electives.json"),
        caption="Поточний каталог. Онови файл і надішли назад.",
    )


@router.message(Command("stats"), IsAdmin())
async def cmd_stats(message: Message, session: AsyncSession) -> None:
    users = await session.scalar(select(func.count()).select_from(User))
    blocked = await session.scalar(
        select(func.count()).select_from(User).where(User.is_blocked.is_(True))
    )
    subjects = await session.scalar(select(func.count()).select_from(Subject))
    picks = await session.scalar(select(func.count()).select_from(UserSubject))
    await message.answer(
        "📊 <b>Статистика</b>\n"
        f"Користувачів: {users} (заблокували бота: {blocked})\n"
        f"Предметів у каталозі: {subjects}\n"
        f"Вибірок користувачів: {picks}"
    )


def _render_import_report(report: ImportReport) -> str:
    lines = [f"✅ Каталог оновлено: {report.total} предметів", ""]
    if report.added:
        lines.append(f"➕ Додано ({len(report.added)}): {fmt.quote(', '.join(report.added[:10]))}")
    if report.updated:
        lines.append(f"✏️ Змінено ({len(report.updated)}):")
        lines.extend(f"  • {fmt.quote(item)}" for item in report.updated[:10])
    if report.removed:
        lines.append(
            f"➖ Прибрано ({len(report.removed)}): {fmt.quote(', '.join(report.removed[:10]))}"
        )
        if report.dropped_selections:
            lines.append(f"  ⚠️ разом з ними знято {report.dropped_selections} вибірок користувачів")
    if not (report.added or report.updated or report.removed):
        lines.append("Нічого не змінилося.")

    if report.link.unmatched:
        lines += ["", "⚠️ <b>Не збіглося з розкладом КПІ:</b>"]
        for raw_name, suggestion in report.link.unmatched[:10]:
            lines.append(f"• <code>{fmt.quote(raw_name)}</code>")
            if suggestion:
                lines.append(f"  схоже на: <i>{fmt.quote(suggestion)}</i>")
        lines.append("Додай цим предметам <code>api_alias</code> і надішли файл знову.")
    else:
        lines += ["", f"🔗 Прив'язано пар до предметів: {report.link.matched}"]
    return "\n".join(lines)


@router.message(F.document, IsAdmin())
async def on_catalog_document(message: Message, bot: Bot, session: AsyncSession) -> None:
    document: Document = message.document  # type: ignore[assignment]
    if not (document.file_name or "").lower().endswith(".json"):
        await message.answer("Очікую файл <code>.json</code> з каталогом предметів.")
        return
    if (document.file_size or 0) > MAX_CATALOG_BYTES:
        await message.answer("Файл завеликий — очікую щось до 2 МБ.")
        return

    buffer = await bot.download(document)
    if buffer is None:
        await message.answer("Не вдалося завантажити файл, спробуй ще раз.")
        return

    try:
        report = await import_catalog(
            session, buffer.read(), get_settings().resolve_semester(message.date.date())
        )
    except CatalogError as exc:
        await message.answer(f"❌ {fmt.quote(str(exc))}")
        return
    await message.answer(_render_import_report(report))
