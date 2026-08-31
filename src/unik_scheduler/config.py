from __future__ import annotations

import datetime as dt
from datetime import time
from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_hhmm(raw: str) -> time:
    hours, minutes = raw.strip().split(":")
    return time(int(hours), int(minutes))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    initial_admin_id: int = 0

    kpi_group_id: int = 3695
    kpi_api_base: str = "https://api.campus.kpi.ua"
    current_semester: int | None = None

    database_url: str

    tz: str = "Europe/Kyiv"
    reminder_lead_minutes: int = 10
    digest_time: time = Field(default=time(7, 30))
    sync_time: time = Field(default=time(5, 0))
    log_level: str = "INFO"

    @field_validator("digest_time", "sync_time", mode="before")
    @classmethod
    def _coerce_time(cls, value: object) -> object:
        return _parse_hhmm(value) if isinstance(value, str) else value

    @field_validator("current_semester", mode="before")
    @classmethod
    def _blank_semester_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.tz)

    def resolve_semester(self, today: dt.date) -> int:
        """Which semester of the study plan is running now.

        The catalog numbers semesters absolutely (7 = autumn of the 4th year,
        8 = spring), so September-January maps to the odd one. Override with
        CURRENT_SEMESTER when the plan rolls over to the next year.
        """
        if self.current_semester is not None:
            return self.current_semester
        return 7 if today.month >= 9 or today.month == 1 else 8

    @property
    def lessons_url(self) -> str:
        return f"{self.kpi_api_base}/schedule/lessons?groupId={self.kpi_group_id}"

    @property
    def current_time_url(self) -> str:
        return f"{self.kpi_api_base}/time/current"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
