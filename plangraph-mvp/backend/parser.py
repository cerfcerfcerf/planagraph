from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Iterable

from schemas import ParsedItem

WEEKDAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _normalize_segments(text: str) -> Iterable[str]:
    chunks = re.split(r"[\n;]+|(?<=[.!?])\s+", text)
    for chunk in chunks:
        cleaned = chunk.strip()
        if cleaned:
            yield cleaned


def _parse_date(segment: str, base_date: date) -> tuple[date | None, str | None]:
    lowered = segment.lower()
    if "today" in lowered:
        return base_date, "today"
    if "tomorrow" in lowered:
        return base_date + timedelta(days=1), "tomorrow"
    for name, idx in WEEKDAY_MAP.items():
        if name in lowered:
            delta = (idx - base_date.weekday()) % 7
            delta = 7 if delta == 0 else delta
            return base_date + timedelta(days=delta), name
    match = re.search(r"(\d{4}-\d{2}-\d{2})", segment)
    if match:
        return datetime.strptime(match.group(1), "%Y-%m-%d").date(), "explicit"
    return None, None


def _parse_time(segment: str) -> time | None:
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", segment.lower())
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return time(hour=hour, minute=minute)


def _priority(segment: str) -> str:
    lowered = segment.lower()
    if "urgent" in lowered or "asap" in lowered or "high" in lowered:
        return "high"
    if "low" in lowered or "whenever" in lowered:
        return "low"
    return "med"


def _recurrence(segment: str) -> tuple[str, str | None]:
    lowered = segment.lower()
    if "every day" in lowered or "daily" in lowered:
        return "daily", None
    if "every 2 days" in lowered or "every two days" in lowered:
        return "every_2_days", None
    if "weekly" in lowered:
        return "weekly", None
    weekdays = [name for name in WEEKDAY_MAP if name in lowered]
    if weekdays:
        return "weekly", ",".join(weekdays)
    return "none", None


def fallback_parse(text: str, base_date: date | None = None) -> list[ParsedItem]:
    today = base_date or date.today()
    items: list[ParsedItem] = []
    for segment in _normalize_segments(text):
        planned_date, _ = _parse_date(segment, today)
        planned_time = _parse_time(segment)
        priority = _priority(segment)
        recurrence, recurrence_detail = _recurrence(segment)

        if planned_date is None:
            planned_date = today

        date_str = planned_date.isoformat() if planned_date else None

        if planned_time:
            due_time = planned_time.strftime("%H:%M")
            window_start = None
            window_end = None
        else:
            due_time = None
            if planned_date == today:
                window_start = datetime.combine(planned_date, time(18, 0)).isoformat()
                window_end = datetime.combine(planned_date, time(22, 0)).isoformat()
            else:
                window_start = datetime.combine(planned_date, time(12, 0)).isoformat()
                window_end = datetime.combine(planned_date, time(20, 0)).isoformat()

        items.append(
            ParsedItem(
                title=segment,
                date=date_str,
                due_time=due_time,
                window_start=window_start,
                window_end=window_end,
                priority=priority,
                recurrence=recurrence,
                recurrence_detail=recurrence_detail,
                confidence=0.42,
                notes=None,
            )
        )
    return items
