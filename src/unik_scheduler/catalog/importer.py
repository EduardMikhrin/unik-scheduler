from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from unik_scheduler.catalog.linking import LinkReport, relink_lessons
from unik_scheduler.catalog.schema import Catalog, CatalogSubject
from unik_scheduler.db.models import Subject, UserSubject
from unik_scheduler.kpi.matching import normalize


class CatalogError(ValueError):
    """The uploaded file is not a catalog we can import."""


@dataclass
class ImportReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    dropped_selections: int = 0
    total: int = 0
    link: LinkReport = field(default_factory=LinkReport)


def parse_catalog(raw: bytes) -> Catalog:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise CatalogError("Файл має бути у кодуванні UTF-8.") from exc
    except json.JSONDecodeError as exc:
        raise CatalogError(f"Це не коректний JSON: {exc.msg} (рядок {exc.lineno}).") from exc

    if not isinstance(payload, dict):
        raise CatalogError("Очікую об'єкт з ключами `normative` та `electives`.")

    try:
        catalog = Catalog.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors()[0]
        location = " → ".join(str(part) for part in first["loc"])
        raise CatalogError(f"Помилка у полі `{location}`: {first['msg']}") from exc

    if not catalog.all_subjects:
        raise CatalogError("У файлі немає жодного предмета.")
    dupes = catalog.duplicate_ids()
    if dupes:
        raise CatalogError(f"Повторювані id: {', '.join(map(str, dupes))}.")
    return catalog


def _fields_of(kind: str, item: CatalogSubject) -> dict:
    return {
        "name": item.name,
        "short_name": item.short_name or None,
        "api_alias": item.api_alias or None,
        "match_key": normalize(item.name),
        "alias_match_key": normalize(item.api_alias) if item.api_alias else None,
        "kind": kind,
        "semester": item.semester,
        "component": item.component or None,
        "default_selected": item.default_selected,
        "chat_url": item.chat_url or None,
        "conf_lecture": item.conferences.lecture or None,
        "conf_practice": item.conferences.practice or None,
        "conf_lab": item.conferences.lab or None,
        "has_lecture": item.conferences.lecture is not None,
        "has_practice": item.conferences.practice is not None,
        "has_lab": item.conferences.lab is not None,
    }


async def import_catalog(session: AsyncSession, raw: bytes, semester: int) -> ImportReport:
    catalog = parse_catalog(raw)
    report = ImportReport(total=len(catalog.all_subjects))

    existing = {s.id: s for s in (await session.execute(select(Subject))).scalars().all()}
    incoming_ids: set[int] = set()

    for kind, item in catalog.all_subjects:
        incoming_ids.add(item.id)
        values = _fields_of(kind, item)
        current = existing.get(item.id)
        if current is None:
            session.add(Subject(id=item.id, **values))
            report.added.append(item.short_name or item.name)
            continue
        changed = [key for key, value in values.items() if getattr(current, key) != value]
        if changed:
            for key, value in values.items():
                setattr(current, key, value)
            # Renames are the interesting case; the rest is noise in a report.
            label = item.short_name or item.name
            report.updated.append(f"{label} ({', '.join(sorted(changed))})")

    stale = [s for s_id, s in existing.items() if s_id not in incoming_ids]
    if stale:
        stale_ids = [s.id for s in stale]
        dropped = await session.execute(
            select(UserSubject).where(UserSubject.subject_id.in_(stale_ids))
        )
        report.dropped_selections = len(dropped.scalars().all())
        await session.execute(delete(Subject).where(Subject.id.in_(stale_ids)))
        report.removed = [s.short_name or s.name for s in stale]

    await session.flush()
    report.link = await relink_lessons(session, semester)
    return report
