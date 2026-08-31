from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unik_scheduler.db.models import ELECTIVE, NORMATIVE, Subject


def _conferences(subject: Subject) -> dict[str, str | None]:
    # Preserve the null / "" distinction the catalog relies on.
    return {
        "lecture": (subject.conf_lecture or "") if subject.has_lecture else None,
        "practice": (subject.conf_practice or "") if subject.has_practice else None,
        "lab": (subject.conf_lab or "") if subject.has_lab else None,
    }


def _dump(subject: Subject) -> dict:
    payload: dict = {
        "id": subject.id,
        "name": subject.name,
        "short_name": subject.short_name,
        "semester": subject.semester,
        "chat_url": subject.chat_url or "",
        "conferences": _conferences(subject),
    }
    if subject.api_alias:
        payload["api_alias"] = subject.api_alias
    if subject.kind == ELECTIVE:
        payload["component"] = subject.component
        payload["default_selected"] = subject.default_selected
    return payload


async def export_catalog(session: AsyncSession) -> bytes:
    rows = await session.execute(select(Subject).order_by(Subject.id))
    subjects = list(rows.scalars().all())
    catalog = {
        "normative": [_dump(s) for s in subjects if s.kind == NORMATIVE],
        "electives": [_dump(s) for s in subjects if s.kind == ELECTIVE],
    }
    return json.dumps(catalog, ensure_ascii=False, indent=2).encode("utf-8")
