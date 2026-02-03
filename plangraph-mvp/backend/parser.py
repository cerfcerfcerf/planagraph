from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from schemas import ParseItem

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _next_weekday(base: date, target: int) -> date:
    days_ahead = (target - base.weekday() + 7) % 7
    return base + timedelta(days=days_ahead or 7)


def _extract_time(text: str) -> time | None:
    match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        return None
    return time(hour=hour, minute=minute)


def _extract_date(text: str, today: date) -> date | None:
    lowered = text.lower()
    if "today" in lowered:
        return today
    if "tomorrow" in lowered:
        return today + timedelta(days=1)
    for name, weekday in WEEKDAYS.items():
        if name in lowered:
            return _next_weekday(today, weekday)
    match = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if match:
        return date.fromisoformat(match.group(0))
    return None


def _extract_recurrence(text: str) -> tuple[str, str | None]:
    lowered = text.lower()
    if "every 2 days" in lowered or "every two days" in lowered:
        return "every_2_days", None
    if "every day" in lowered or "daily" in lowered:
        return "daily", None
    if "weekly" in lowered:
        return "weekly", None
    for name in WEEKDAYS:
        if name in lowered and "every" in lowered:
            return "weekly", name
    return "none", None


def _default_window(base_date: date) -> tuple[datetime, datetime]:
    if base_date == date.today():
        start = datetime.combine(base_date, time(18, 0))
        end = datetime.combine(base_date, time(22, 0))
    else:
        start = datetime.combine(base_date, time(12, 0))
        end = datetime.combine(base_date, time(20, 0))
    return start, end


def deterministic_parse(text: str) -> list[ParseItem]:
    today = date.today()
    parts = [
        part.strip()
        for part in re.split(r"[\n\.;]+", text)
        if part.strip()
    ]
    items: list[ParseItem] = []
    for part in parts:
        detected_date = _extract_date(part, today) or today
        detected_time = _extract_time(part)
        recurrence, recurrence_detail = _extract_recurrence(part)
        if detected_time:
            due_time = detected_time.strftime("%H:%M")
            item = ParseItem(
                title=part,
                date=detected_date.isoformat(),
                due_time=due_time,
                window_start=None,
                window_end=None,
                priority="med",
                recurrence=recurrence,
                recurrence_detail=recurrence_detail,
                confidence=0.5,
                notes=None,
            )
        else:
            window_start, window_end = _default_window(detected_date)
            item = ParseItem(
                title=part,
                date=detected_date.isoformat(),
                due_time=None,
                window_start=window_start.isoformat(),
                window_end=window_end.isoformat(),
                priority="med",
                recurrence=recurrence,
                recurrence_detail=recurrence_detail,
                confidence=0.45,
                notes=None,
            )
        items.append(item)
    return items
