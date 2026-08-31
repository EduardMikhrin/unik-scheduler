from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NORMATIVE = "normative"
ELECTIVE = "elective"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)  # telegram user id
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(256), default="")
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    changes_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Subject(Base):
    """One course from the catalog JSON. `id` is the id the catalog assigns."""

    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(512))
    short_name: Mapped[str | None] = mapped_column(String(128))
    api_alias: Mapped[str | None] = mapped_column(String(512))
    # Normalized forms used to join against the KPI API, see kpi.matching.
    match_key: Mapped[str] = mapped_column(String(512), index=True)
    alias_match_key: Mapped[str | None] = mapped_column(String(512), index=True)

    kind: Mapped[str] = mapped_column(String(16))  # NORMATIVE | ELECTIVE
    semester: Mapped[int] = mapped_column(Integer, index=True)
    component: Mapped[str | None] = mapped_column(String(16))
    default_selected: Mapped[bool] = mapped_column(Boolean, default=False)

    chat_url: Mapped[str | None] = mapped_column(String(512))
    conf_lecture: Mapped[str | None] = mapped_column(String(512))
    conf_practice: Mapped[str | None] = mapped_column(String(512))
    conf_lab: Mapped[str | None] = mapped_column(String(512))
    # `null` in the catalog means "this kind of class does not exist for the course",
    # `""` means "it exists but no link yet" — the two are not interchangeable.
    has_lecture: Mapped[bool] = mapped_column(Boolean, default=False)
    has_practice: Mapped[bool] = mapped_column(Boolean, default=False)
    has_lab: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def display_name(self) -> str:
        return self.short_name or self.name

    def conference_for(self, tag: str) -> str | None:
        return {"lec": self.conf_lecture, "prac": self.conf_practice, "lab": self.conf_lab}.get(tag)

    def declares(self, tag: str) -> bool:
        return {"lec": self.has_lecture, "prac": self.has_practice, "lab": self.has_lab}.get(
            tag, False
        )


class UserSubject(Base):
    """Electives a user picked. Normative courses are implicit for everyone."""

    __tablename__ = "user_subjects"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    subject_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("subjects.id", ondelete="CASCADE"), primary_key=True
    )


class Lesson(Base):
    """One cell of the group timetable, as returned by the KPI API."""

    __tablename__ = "lessons"
    __table_args__ = (
        UniqueConstraint("week", "day", "start", "raw_name", "type", name="uq_lesson_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week: Mapped[int] = mapped_column(Integer, index=True)  # 1 or 2
    day: Mapped[int] = mapped_column(Integer, index=True)  # 0=Mon .. 5=Sat
    start: Mapped[dt.time] = mapped_column(Time)
    raw_name: Mapped[str] = mapped_column(String(512))
    type: Mapped[str] = mapped_column(String(16))  # Лек / Прак / Лаб
    tag: Mapped[str] = mapped_column(String(16))  # lec / prac / lab
    lecturer: Mapped[str | None] = mapped_column(String(256))
    # Non-empty means the lesson runs only on these calendar dates.
    only_dates: Mapped[list[dt.date] | None] = mapped_column(ARRAY(Date))
    subject_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("subjects.id", ondelete="SET NULL"), index=True
    )


class NotificationLog(Base):
    """Dedup guard so a restart cannot re-send a reminder that already went out."""

    __tablename__ = "notification_log"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)  # reminder | digest
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    sent_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AppState(Base):
    """Small key/value store: week-parity anchor, last successful sync, etc."""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512))
