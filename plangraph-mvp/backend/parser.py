from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone

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


def _extract_leading_time(text: str) -> tuple[time, str] | None:
    match = re.match(r"^\s*(\d{1,2}:\d{2})\s*[–-]\s*(.+)$", text)
    if not match:
        return None
    start = _extract_time(match.group(1))
    if not start:
        return None
    return start, match.group(2).strip()


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


def infer_priority(title: str, notes: str | None = None) -> str:
    text = f"{title} {notes or ''}".strip()
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


def infer_task_type(title: str, notes: str | None = None) -> str:
    lowered = f"{title} {notes or ''}".lower()
    if any(keyword in lowered for keyword in ["breakfast", "lunch", "dinner", "eat", "meal prep", "meal"]):
        return "meal"
    if any(keyword in lowered for keyword in ["sleep", "wake up", "wakeup", "bed"]):
        return "sleep"
    if any(keyword in lowered for keyword in ["pills", "meds", "vitamins", "medication"]):
        return "medication"
    if any(keyword in lowered for keyword in ["shower", "brush", "teeth", "hygiene"]):
        return "hygiene"
    if any(keyword in lowered for keyword in ["lecture", "class", "lab", "seminar"]):
        return "class"
    if any(keyword in lowered for keyword in ["gym", "workout", "run", "exercise"]):
        return "exercise"
    return "other"


def recurrence_suggestions(title: str, detected_date: date | None = None) -> list[dict]:
    lowered = title.lower()
    suggestions: list[dict] = []
    if detected_date and any(keyword in lowered for keyword in ["class", "lecture", "lab"]):
        weekday = detected_date.strftime("%A").lower()
        suggestions.append(
            {
                "recurrence": "weekly",
                "recurrence_detail": weekday,
                "confidence": 0.7,
            }
        )
    return suggestions


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


def _duration_minutes(title: str, notes: str | None = None) -> int:
    lowered = f"{title} {notes or ''}".lower()
    if any(keyword in lowered for keyword in ["wake", "hygiene", "breakfast", "shower"]):
        return 30
    if "commute" in lowered:
        return 30
    if any(keyword in lowered for keyword in ["lecture", "lab"]):
        return 90
    if any(keyword in lowered for keyword in ["lunch", "dinner"]):
        return 60
    if "gym" in lowered:
        return 90
    if "homework" in lowered:
        return 120
    if "sleep" in lowered:
        return 420
    return 30


def _to_utc_iso(value: datetime) -> str:
    local_tz = datetime.now(timezone.utc).astimezone().tzinfo
    if value.tzinfo is None:
        value = value.replace(tzinfo=local_tz)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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
        task_type = infer_task_type(title, notes)
        priority = infer_priority(title, notes)
        suggestions = recurrence_suggestions(title, detected_date)
        if task_type in {"meal", "sleep", "medication", "hygiene"} and recurrence == "none":
            recurrence = "daily"
            recurrence_detail = "auto-routine"
        if current_range:
            start, end = current_range
            end_date = detected_date
            if end < start:
                end_date = detected_date + timedelta(days=1)
            window_start = _to_utc_iso(datetime.combine(detected_date, start))
            window_end = _to_utc_iso(datetime.combine(end_date, end))
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
                    recurrence_suggestions=suggestions or None,
                    task_type=task_type,
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
                        recurrence_suggestions=suggestions or None,
                        task_type=task_type,
                    )
                )
            else:
                window_start, window_end = _default_window(detected_date)
                items.append(
                    ParseItem(
                        title=title,
                        date=detected_date.isoformat(),
                        due_time=None,
                        window_start=_to_utc_iso(window_start),
                        window_end=_to_utc_iso(window_end),
                        priority=priority,
                        recurrence=recurrence,
                        recurrence_detail=recurrence_detail,
                        confidence=0.45,
                        notes=notes,
                        recurrence_suggestions=suggestions or None,
                        task_type=task_type,
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
        leading_time = _extract_leading_time(line) if not range_only else None
        if leading_time and not current_range:
            start_time, remainder = leading_time
            description = remainder
            detected_date = _extract_date(description, today) or today
            notes = None
            task_type = infer_task_type(remainder, notes)
            priority = infer_priority(remainder, notes)
            recurrence, recurrence_detail = _extract_recurrence(description)
            suggestions = recurrence_suggestions(remainder, detected_date)
            if task_type in {"meal", "sleep", "medication", "hygiene"} and recurrence == "none":
                recurrence = "daily"
                recurrence_detail = "auto-routine"
            if task_type == "sleep":
                window_start = _to_utc_iso(datetime.combine(detected_date, time(23, 30)))
                window_end = _to_utc_iso(
                    datetime.combine(detected_date + timedelta(days=1), time(6, 30))
                )
            else:
                duration = _duration_minutes(remainder, notes)
                window_start_dt = datetime.combine(detected_date, start_time)
                window_end_dt = window_start_dt + timedelta(minutes=duration)
                window_start = _to_utc_iso(window_start_dt)
                window_end = _to_utc_iso(window_end_dt)
            items.append(
                ParseItem(
                    title=remainder,
                    date=detected_date.isoformat(),
                    due_time=None,
                    window_start=window_start,
                    window_end=window_end,
                    priority=priority,
                    recurrence=recurrence,
                    recurrence_detail=recurrence_detail,
                    confidence=0.55,
                    notes=notes,
                    recurrence_suggestions=suggestions or None,
                    task_type=task_type,
                )
            )
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
