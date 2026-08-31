from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class ElectiveCB(CallbackData, prefix="el"):
    action: str  # component | toggle | back | done
    component: str = ""
    subject_id: int = 0


class SettingsCB(CallbackData, prefix="set"):
    field: str  # reminders | digest | changes
