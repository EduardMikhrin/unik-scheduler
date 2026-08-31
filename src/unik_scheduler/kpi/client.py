from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass

import aiohttp

from unik_scheduler.kpi.constants import DAY_TO_INDEX

log = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=30)


@dataclass(frozen=True)
class ApiLesson:
    week: int
    day: int
    start: dt.time
    name: str
    type: str
    tag: str
    lecturer: str | None
    only_dates: tuple[dt.date, ...]

    @property
    def slot(self) -> tuple[int, int, dt.time, str, str]:
        """Identity of a timetable cell — used to diff one sync against the next."""
        return (self.week, self.day, self.start, self.name, self.type)


class KpiApiError(RuntimeError):
    pass


class KpiClient:
    def __init__(self, lessons_url: str, current_time_url: str) -> None:
        self._lessons_url = lessons_url
        self._current_time_url = current_time_url

    async def _get_json(self, url: str) -> dict:
        try:
            async with aiohttp.ClientSession(timeout=_TIMEOUT) as session, session.get(url) as resp:
                if resp.status != 200:
                    raise KpiApiError(f"{url} returned HTTP {resp.status}")
                # The API mislabels its content type on some responses.
                return await resp.json(content_type=None)
        except aiohttp.ClientError as exc:
            raise KpiApiError(f"{url} failed: {exc}") from exc

    async def fetch_current_week(self) -> int:
        payload = await self._get_json(self._current_time_url)
        week = int(payload.get("currentWeek", 0))
        if week not in (1, 2):
            raise KpiApiError(f"unexpected currentWeek={week!r}")
        return week

    async def fetch_lessons(self) -> list[ApiLesson]:
        return parse_lessons(await self._get_json(self._lessons_url))


def parse_lessons(payload: dict) -> list[ApiLesson]:
    lessons: list[ApiLesson] = []
    for week, field in ((1, "scheduleFirstWeek"), (2, "scheduleSecondWeek")):
        for day_entry in payload.get(field) or []:
            day_index = DAY_TO_INDEX.get(day_entry.get("day", ""))
            if day_index is None:
                log.warning("skipping unknown day label %r", day_entry.get("day"))
                continue
            for pair in day_entry.get("pairs") or []:
                parsed = _parse_pair(week, day_index, pair)
                if parsed is not None:
                    lessons.append(parsed)
    if not lessons:
        raise KpiApiError("schedule came back empty — refusing to wipe the timetable")
    return lessons


def _parse_pair(week: int, day: int, pair: dict) -> ApiLesson | None:
    name = (pair.get("name") or "").strip()
    raw_time = pair.get("time")
    if not name or not raw_time:
        return None
    try:
        start = dt.time.fromisoformat(raw_time)
    except ValueError:
        log.warning("skipping pair %r with unparsable time %r", name, raw_time)
        return None
    lecturer = (pair.get("lecturer") or {}).get("name") if pair.get("lecturer") else None
    dates: list[dt.date] = []
    for raw_date in pair.get("dates") or []:
        try:
            dates.append(dt.date.fromisoformat(raw_date))
        except (TypeError, ValueError):
            log.warning("skipping unparsable date %r on %r", raw_date, name)
    return ApiLesson(
        week=week,
        day=day,
        start=start,
        name=name,
        type=(pair.get("type") or "").strip(),
        tag=(pair.get("tag") or "").strip(),
        lecturer=lecturer.strip() if lecturer else None,
        only_dates=tuple(sorted(dates)),
    )
