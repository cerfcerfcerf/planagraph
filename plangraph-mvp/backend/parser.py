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


def _extract_time_range(text: str) -> tuple[time, time] | None:
    match = re.search(r"\b(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})\b", text)
    if not match:
        return None
    start = _extract_time(match.group(1))
    end = _extract_time(match.group(2))
    if not start or not end:
        return None
    return start, end


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


def priority_from_text(text: str) -> str:
    lowered = text.lower()
    high_keywords = [
        "exam",
        "test",
        "submit",
        "due",
        "meeting",
        "flight",
        "doctor",
        "medication",
        "visa",
        "deadline",
    ]
    low_keywords = ["optional", "maybe", "if time", "chill"]
    if any(keyword in lowered for keyword in high_keywords):
        return "high"
    if any(keyword in lowered for keyword in low_keywords):
        return "low"
    return "med"


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
    lines = [line.strip() for line in text.splitlines()]
    items: list[ParseItem] = []

    current_range: tuple[time, time] | None = None
    buffer: list[str] = []

    def flush_buffer() -> None:
        nonlocal buffer, current_range
        if not buffer:
            return
        description = " ".join(buffer).strip()
        title = buffer[0]
        notes = " ".join(buffer[1:]).strip() if len(buffer) > 1 else None
        detected_date = _extract_date(description, today) or today
        recurrence, recurrence_detail = _extract_recurrence(description)
        priority = priority_from_text(description)
        if current_range:
            start, end = current_range
            window_start = datetime.combine(detected_date, start).isoformat()
            window_end = datetime.combine(detected_date, end).isoformat()
            items.append(
                ParseItem(
                    title=title,
                    date=detected_date.isoformat(),
                    due_time=None,
                    window_start=window_start,
                    window_end=window_end,
                    priority=priority,
                    recurrence=recurrence,
                    recurrence_detail=recurrence_detail,
                    confidence=0.55,
                    notes=notes,
                )
            )
        else:
            detected_time = _extract_time(description)
            if detected_time:
                due_time = detected_time.strftime("%H:%M")
                items.append(
                    ParseItem(
                        title=title,
                        date=detected_date.isoformat(),
                        due_time=due_time,
                        window_start=None,
                        window_end=None,
                        priority=priority,
                        recurrence=recurrence,
                        recurrence_detail=recurrence_detail,
                        confidence=0.5,
                        notes=notes,
                    )
                )
            else:
                window_start, window_end = _default_window(detected_date)
                items.append(
                    ParseItem(
                        title=title,
                        date=detected_date.isoformat(),
                        due_time=None,
                        window_start=window_start.isoformat(),
                        window_end=window_end.isoformat(),
                        priority=priority,
                        recurrence=recurrence,
                        recurrence_detail=recurrence_detail,
                        confidence=0.45,
                        notes=notes,
                    )
                )
        buffer = []
        current_range = None

    for line in lines:
        if not line:
            continue
        range_only = _extract_time_range(line)
        if range_only and re.fullmatch(r"\s*\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\s*", line):
            flush_buffer()
            current_range = range_only
            continue
        if current_range:
            buffer.append(line)
            continue
        if range_only:
            current_range = range_only
            remainder = re.sub(r"\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}", "", line).strip()
            if remainder:
                buffer.append(remainder)
                flush_buffer()
            continue
        for chunk in re.split(r"[.;]+", line):
            chunk = chunk.strip()
            if not chunk:
                continue
            buffer.append(chunk)
            flush_buffer()
    flush_buffer()
    return items
