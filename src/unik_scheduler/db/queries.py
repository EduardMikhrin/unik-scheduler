from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from unik_scheduler.bot.formatting import LessonView
from unik_scheduler.db.models import (
    ELECTIVE,
    NORMATIVE,
    AppState,
    Lesson,
    NotificationLog,
    Subject,
    User,
    UserSubject,
)


async def get_or_create_user(
    session: AsyncSession, user_id: int, username: str | None, full_name: str
) -> tuple[User, bool]:
    user = await session.get(User, user_id)
    if user is not None:
        # Keep the display data fresh; users rename themselves.
        user.username = username
        user.full_name = full_name
        user.is_blocked = False
        return user, False

    user = User(id=user_id, username=username, full_name=full_name)
    session.add(user)
    await session.flush()
    await preselect_defaults(session, user_id)
    return user, True


async def preselect_defaults(session: AsyncSession, user_id: int) -> None:
    """New users start from the catalog's `default_selected` electives."""
    rows = await session.execute(
        select(Subject.id).where(Subject.kind == ELECTIVE, Subject.default_selected.is_(True))
    )
    for (subject_id,) in rows.all():
        session.add(UserSubject(user_id=user_id, subject_id=subject_id))


async def selected_elective_ids(session: AsyncSession, user_id: int) -> set[int]:
    rows = await session.execute(
        select(UserSubject.subject_id).where(UserSubject.user_id == user_id)
    )
    return {row[0] for row in rows.all()}


async def toggle_elective(session: AsyncSession, user_id: int, subject_id: int) -> bool:
    existing = await session.get(UserSubject, {"user_id": user_id, "subject_id": subject_id})
    if existing is None:
        session.add(UserSubject(user_id=user_id, subject_id=subject_id))
        return True
    await session.delete(existing)
    return False


async def electives_for_semester(session: AsyncSession, semester: int) -> list[Subject]:
    rows = await session.execute(
        select(Subject)
        .where(Subject.kind == ELECTIVE, Subject.semester == semester)
        .order_by(Subject.component, Subject.name)
    )
    return list(rows.scalars().all())


async def visible_subject_ids(session: AsyncSession, user_id: int, semester: int) -> set[int]:
    """Normative courses of the semester plus the electives this user picked."""
    normative = await session.execute(
        select(Subject.id).where(Subject.kind == NORMATIVE, Subject.semester == semester)
    )
    chosen = await session.execute(
        select(UserSubject.subject_id)
        .join(Subject, Subject.id == UserSubject.subject_id)
        .where(UserSubject.user_id == user_id, Subject.semester == semester)
    )
    return {row[0] for row in normative.all()} | {row[0] for row in chosen.all()}


def _applies_on(lesson: Lesson, day: dt.date) -> bool:
    """A lesson with explicit dates runs only on those dates."""
    return not lesson.only_dates or day in lesson.only_dates


async def lessons_for_day(
    session: AsyncSession, subject_ids: set[int], week: int, day: dt.date
) -> list[LessonView]:
    if not subject_ids:
        return []
    rows = await session.execute(
        select(Lesson, Subject)
        .join(Subject, Subject.id == Lesson.subject_id)
        .where(
            Lesson.week == week,
            Lesson.day == day.weekday(),
            Lesson.subject_id.in_(subject_ids),
        )
        .order_by(Lesson.start)
    )
    return [
        LessonView(lesson, subject) for lesson, subject in rows.all() if _applies_on(lesson, day)
    ]


async def lessons_for_week(
    session: AsyncSession, subject_ids: set[int], week: int
) -> dict[int, list[LessonView]]:
    if not subject_ids:
        return {}
    rows = await session.execute(
        select(Lesson, Subject)
        .join(Subject, Subject.id == Lesson.subject_id)
        .where(Lesson.week == week, Lesson.subject_id.in_(subject_ids))
        .order_by(Lesson.day, Lesson.start)
    )
    by_day: dict[int, list[LessonView]] = {}
    for lesson, subject in rows.all():
        by_day.setdefault(lesson.day, []).append(LessonView(lesson, subject))
    return by_day


async def active_users(session: AsyncSession) -> list[User]:
    rows = await session.execute(select(User).where(User.is_blocked.is_(False)))
    return list(rows.scalars().all())


async def admins(session: AsyncSession) -> list[User]:
    rows = await session.execute(select(User).where(User.is_admin.is_(True)).order_by(User.id))
    return list(rows.scalars().all())


async def find_user_by_username(session: AsyncSession, username: str) -> User | None:
    rows = await session.execute(
        select(User).where(func.lower(User.username) == username.lstrip("@").lower())
    )
    return rows.scalars().first()


async def mark_sent(session: AsyncSession, user_id: int, kind: str, key: str) -> bool:
    """Returns True when this is the first time the notification is recorded."""
    statement = (
        pg_insert(NotificationLog)
        .values(user_id=user_id, kind=kind, key=key)
        .on_conflict_do_nothing(index_elements=["user_id", "kind", "key"])
        .returning(NotificationLog.key)
    )
    result = await session.execute(statement)
    return result.scalar_one_or_none() is not None


async def get_state(session: AsyncSession, key: str) -> str | None:
    row = await session.get(AppState, key)
    return row.value if row else None


async def set_state(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(AppState, key)
    if row is None:
        session.add(AppState(key=key, value=value))
    else:
        row.value = value


async def week_of(session: AsyncSession, day: dt.date) -> int | None:
    """Parity of the given date, derived from the anchor the last sync stored."""
    from unik_scheduler.kpi.weeks import ANCHOR_DATE_KEY, ANCHOR_WEEK_KEY, week_for

    raw_date = await get_state(session, ANCHOR_DATE_KEY)
    raw_week = await get_state(session, ANCHOR_WEEK_KEY)
    if not raw_date or not raw_week:
        return None
    return week_for(day, dt.date.fromisoformat(raw_date), int(raw_week))
