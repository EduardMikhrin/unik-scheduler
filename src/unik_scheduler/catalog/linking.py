from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unik_scheduler.db.models import Lesson, Subject
from unik_scheduler.kpi.matching import SubjectMatcher

log = logging.getLogger(__name__)


@dataclass
class LinkReport:
    matched: int = 0
    unmatched: list[tuple[str, str | None]] = field(default_factory=list)
    # (raw API name, best guess from the catalog or None)

    @property
    def has_problems(self) -> bool:
        return bool(self.unmatched)


async def build_matcher(session: AsyncSession, semester: int) -> SubjectMatcher:
    """Only current-semester courses are eligible.

    The catalog carries the same title in both semesters ("Практичний курс
    іноземної мови ... Частина 2" is id 1 for semester 7 and id 7 for semester 8),
    so an unscoped matcher would bind the timetable to the wrong one.
    """
    rows = await session.execute(
        select(Subject.id, Subject.name, Subject.match_key, Subject.alias_match_key).where(
            Subject.semester == semester
        )
    )
    return SubjectMatcher([tuple(row) for row in rows.all()])  # type: ignore[misc]


async def relink_lessons(session: AsyncSession, semester: int) -> LinkReport:
    """Re-resolve every stored lesson against the current catalog.

    Runs after a sync and after a catalog import, since either side can change.
    """
    matcher = await build_matcher(session, semester)
    lessons = (await session.execute(select(Lesson))).scalars().all()

    report = LinkReport()
    seen_unmatched: set[str] = set()
    for lesson in lessons:
        subject_id = matcher.match(lesson.raw_name)
        if lesson.subject_id != subject_id:
            lesson.subject_id = subject_id
        if subject_id is None:
            if lesson.raw_name not in seen_unmatched:
                seen_unmatched.add(lesson.raw_name)
                candidate = matcher.suggest(lesson.raw_name)
                report.unmatched.append(
                    (lesson.raw_name, candidate.subject_name if candidate else None)
                )
        else:
            report.matched += 1

    await session.flush()
    if report.unmatched:
        log.warning("%d schedule course name(s) did not match the catalog", len(report.unmatched))
    return report
