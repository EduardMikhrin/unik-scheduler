from __future__ import annotations

import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def schedule_payload() -> dict:
    return json.loads((FIXTURES / "schedule.json").read_text(encoding="utf-8"))
