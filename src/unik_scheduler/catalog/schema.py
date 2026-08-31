"""Shape of the catalog JSON that admins upload to the bot.

Unknown keys are ignored on purpose, so the file the user maintains by hand can
carry extra bookkeeping (credits, department, notes) without breaking imports.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Conferences(BaseModel):
    model_config = ConfigDict(extra="ignore")

    # None -> the course has no classes of this kind at all.
    # ""   -> it has them, the link is simply not filled in yet.
    lecture: str | None = None
    practice: str | None = None
    lab: str | None = None


class CatalogSubject(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: int
    name: str
    short_name: str | None = None
    api_alias: str | None = None
    semester: int
    component: str | None = None
    chat_url: str | None = None
    conferences: Conferences = Field(default_factory=Conferences)
    # `selected` is what the hand-maintained file already used.
    default_selected: bool = Field(default=False, alias="selected")

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be empty")
        return value.strip()


class Catalog(BaseModel):
    model_config = ConfigDict(extra="ignore")

    normative: list[CatalogSubject] = Field(default_factory=list)
    electives: list[CatalogSubject] = Field(default_factory=list)

    @property
    def all_subjects(self) -> list[tuple[str, CatalogSubject]]:
        return [("normative", s) for s in self.normative] + [
            ("elective", s) for s in self.electives
        ]

    def duplicate_ids(self) -> list[int]:
        seen: set[int] = set()
        dupes: set[int] = set()
        for _, subject in self.all_subjects:
            (dupes if subject.id in seen else seen).add(subject.id)
        return sorted(dupes)
