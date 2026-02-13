from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from schemas import ParseItem

WEEKDAYS = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}
TIME_TOKEN = r"(\d{1,2}(?::\d{2}|\.\d{2})?\s*(?:am|pm)?)"
RANGE_PATTERN = re.compile(rf"\b{TIME_TOKEN}\s*(?:-|–|to)\s*{TIME_TOKEN}\b", re.IGNORECASE)
SINGLE_TIME_PATTERN = re.compile(rf"\b{TIME_TOKEN}\b", re.IGNORECASE)
ISO_DATE_PATTERN = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
SLASH_DATE_PATTERN = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def _next_weekday(base: date, target: int) -> date:
    days_ahead = (target - base.weekday() + 7) % 7
    return base + timedelta(days=days_ahead or 7)


def _parse_time_token(token: str) -> time | None:
    raw = token.strip().lower().replace(" ", "").replace(".", ":")
    period = None
    if raw.endswith("am") or raw.endswith("pm"):
        period = raw[-2:]
        raw = raw[:-2]
    if ":" in raw:
        hour_text, minute_text = raw.split(":", 1)
    else:
        hour_text, minute_text = raw, "00"
    if not hour_text.isdigit() or not minute_text.isdigit():
        return None
    hour = int(hour_text)
    minute = int(minute_text)
    if minute > 59:
        return None
    if period:
        if hour < 1 or hour > 12:
            return None
        if period == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
    elif hour > 23:
        return None
    return time(hour=hour, minute=minute)


def _extract_date(text: str, today: date) -> tuple[date | None, str | None]:
    lowered = text.lower()
    if "today" in lowered:
        return today, None
    if "tomorrow" in lowered:
        return today + timedelta(days=1), None
    for label, weekday in WEEKDAYS.items():
        if re.search(rf"\b{label}\b", lowered):
            return _next_weekday(today, weekday), None
    iso_match = ISO_DATE_PATTERN.search(text)
    if iso_match:
        try:
            return date.fromisoformat(iso_match.group(0)), None
        except ValueError:
            return None, "Invalid ISO date"
    slash_match = SLASH_DATE_PATTERN.search(text)
    if slash_match:
        first = int(slash_match.group(1))
        second = int(slash_match.group(2))
        year = int(slash_match.group(3))
        # Default is DD/MM/YYYY.
        if first <= 12 and second <= 12:
            return None, "Ambiguous slash date; use YYYY-MM-DD or spell month"
        day, month = first, second
        try:
            return date(year, month, day), None
        except ValueError:
            return None, "Invalid DD/MM/YYYY date"
    return None, None


def _extract_time_range(text: str) -> tuple[time, time] | None:
    match = RANGE_PATTERN.search(text)
    if not match:
        return None
    start = _parse_time_token(match.group(1))
    end = _parse_time_token(match.group(2))
    if not start or not end:
        return None
    return start, end


def _extract_single_time(text: str) -> time | None:
    range_match = RANGE_PATTERN.search(text)
    cleaned = text
    if range_match:
        cleaned = text.replace(range_match.group(0), " ")
    match = SINGLE_TIME_PATTERN.search(cleaned)
    if not match:
        return None
    return _parse_time_token(match.group(1))


def _strip_markers(text: str) -> str:
    lowered = text
    lowered = RANGE_PATTERN.sub("", lowered)
    lowered = ISO_DATE_PATTERN.sub("", lowered)
    lowered = SLASH_DATE_PATTERN.sub("", lowered)
    lowered = re.sub(r"\b(today|tomorrow|mon|monday|tue|tuesday|wed|wednesday|thu|thursday|fri|friday|sat|saturday|sun|sunday)\b", "", lowered, flags=re.IGNORECASE)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip(" -:,.")


def _build_item_from_line(line: str, today: date) -> ParseItem:
    parsed_date, date_error = _extract_date(line, today)
    line_date = parsed_date or today
    time_range = _extract_time_range(line)
    due_time = _extract_single_time(line)
    title = _strip_markers(line) or line.strip()

    if date_error:
        return ParseItem(title=title, date=None, parse_error=date_error)

    if time_range:
        start, end = time_range
        start_dt = datetime.combine(line_date, start)
        end_dt = datetime.combine(line_date, end)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        return ParseItem(
            title=title,
            date=line_date.isoformat(),
            window_start=start_dt.isoformat(),
            window_end=end_dt.isoformat(),
            due_time=None,
            confidence=0.9,
        )

    if due_time:
        return ParseItem(
            title=title,
            date=line_date.isoformat(),
            due_time=due_time.strftime("%H:%M"),
            confidence=0.9,
        )

    return ParseItem(
        title=title,
        date=line_date.isoformat(),
        parse_error="Missing or invalid time. Use formats like 20:00, 20.00, 8pm, or 20:00-23:00",
        confidence=0.2,
    )


def deterministic_parse(text: str) -> list[ParseItem]:
    today = date.today()
    items: list[ParseItem] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        items.append(_build_item_from_line(line, today))
    return items


def infer_priority(title: str, notes: str | None = None) -> str:
    lowered = f"{title} {notes or ''}".lower()
    if any(keyword in lowered for keyword in ["exam", "test", "submit", "due", "meeting", "flight", "doctor", "medication", "visa", "deadline"]):
        return "high"
    if any(keyword in lowered for keyword in ["optional", "maybe", "if time", "chill"]):
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
    if not detected_date:
        return []
    lowered = title.lower()
    if any(keyword in lowered for keyword in ["class", "lecture", "lab"]):
        return [{"recurrence": "weekly", "recurrence_detail": detected_date.strftime("%A").lower(), "confidence": 0.7}]
    return []
