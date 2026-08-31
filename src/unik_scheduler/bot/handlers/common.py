from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from unik_scheduler.db.models import User

router = Router(name="common")

HELP = (
    "<b>Команди</b>\n"
    "/today — пари на сьогодні\n"
    "/tomorrow — пари на завтра\n"
    "/week — розклад на поточний тиждень\n"
    "/next — найближча пара\n"
    "/electives — обрати вибіркові предмети\n"
    "/settings — які сповіщення надсилати\n"
    "/id — твій Telegram id"
)


@router.message(CommandStart())
async def cmd_start(message: Message, user: User) -> None:
    greeting = (
        "Привіт! Я стежу за розкладом групи й нагадую тільки про <b>твої</b> пари.\n\n"
        "1️⃣ Обери вибіркові предмети — /electives\n"
        "2️⃣ Далі я щоранку надсилатиму зведення на день "
        "і нагадаю за 10 хвилин до кожної пари.\n\n"
        f"{HELP}"
    )
    if user.is_admin:
        greeting += "\n\nУ тебе є права адміністратора — /admin"
    await message.answer(greeting)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP)


@router.message(Command("id"))
async def cmd_id(message: Message, user: User) -> None:
    await message.answer(
        f"Твій Telegram id: <code>{user.id}</code>\n"
        "Його потрібно вказати в <code>INITIAL_ADMIN_ID</code> або передати адміну."
    )
