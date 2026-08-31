"""Joining catalog course names to KPI API course names.

The two sources disagree in ways plain equality cannot bridge:
  * apostrophes differ (U+2019 vs U+0027) — normalization fixes these;
  * the API carries its own typos ("глибого" for "глибокого") and spacing
    variants ("TimeSeries" vs "Time Series") — those need an explicit alias.

So: normalize both sides, and let the catalog override with `api_alias`.
Anything still unmatched is reported to admins rather than silently dropped.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "`": "'", "´": "'", "ʼ": "'"})
_DASHES = str.maketrans({"–": "-", "—": "-", "−": "-"})
_WHITESPACE = re.compile(r"\s+")


def normalize(name: str) -> str:
    text = unicodedata.normalize("NFKC", name)
    text = text.translate(_APOSTROPHES).translate(_DASHES)
    return _WHITESPACE.sub(" ", text).strip().casefold()


@dataclass(frozen=True)
class MatchCandidate:
    subject_id: int
    subject_name: str
    ratio: float


class SubjectMatcher:
    """Maps an API course name onto a catalog subject id."""

    def __init__(self, subjects: list[tuple[int, str, str, str | None]]) -> None:
        # subjects: (id, display name, match_key, alias_match_key)
        self._by_key: dict[str, int] = {}
        self._names: dict[int, str] = {}
        for subject_id, name, match_key, alias_key in subjects:
            self._names[subject_id] = name
            self._by_key.setdefault(match_key, subject_id)
            if alias_key:
                self._by_key[alias_key] = subject_id

    def match(self, api_name: str) -> int | None:
        return self._by_key.get(normalize(api_name))

    def suggest(self, api_name: str, cutoff: float = 0.82) -> MatchCandidate | None:
        """Best near-miss for an unmatched name, so admins get an actionable hint."""
        key = normalize(api_name)
        best = difflib.get_close_matches(key, list(self._by_key), n=1, cutoff=cutoff)
        if not best:
            return None
        subject_id = self._by_key[best[0]]
        ratio = difflib.SequenceMatcher(None, key, best[0]).ratio()
        return MatchCandidate(subject_id, self._names[subject_id], ratio)
