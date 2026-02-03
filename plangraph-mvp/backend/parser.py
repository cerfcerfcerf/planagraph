from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Iterable

from pydantic import ValidationError

from llm_client import LLMClient
from schemas import ParseResponse, ParsedItem

WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]


def parse_date_token(token: str, today: date) -> date | None:
    lowered = token.lower()
    if match := re.search(r"\b(\d{4}-\d{2}-\d{2})\b", lowered):
        return date.fromisoformat(match.group(1))
    if "today" in lowered:
        return today
    if "tomorrow" in lowered:
        return today + timedelta(days=1)
    for idx, name in enumerate(WEEKDAYS):
        if name in lowered:
            days_ahead = (idx - today.weekday()) % 7
            days_ahead = 7 if days_ahead == 0 else days_ahead
            return today + timedelta(days=days_ahead)
    return None


def parse_time_token(token: str) -> str | None:
    if match := re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", token, re.IGNORECASE):
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridiem = match.group(3)
        if meridiem:
            mer = meridiem.lower()
            if mer == "pm" and hour < 12:
                hour += 12
            if mer == "am" and hour == 12:
                hour = 0
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    return None


def clean_title(text: str) -> str:
    cleaned = re.sub(r"\b(today|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d{1,2}(:\d{2})?\s*(am|pm)?\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:")
    return cleaned or text.strip()


def detect_priority(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ["urgent", "asap", "important", "critical"]):
        return "high"
    if any(word in lowered for word in ["low", "optional", "maybe"]):
        return "low"
    return "med"


def detect_recurrence(text: str) -> tuple[str, str | None]:
    lowered = text.lower()
    if "every 2 days" in lowered or "every two days" in lowered:
        return "every_2_days", None
    if "daily" in lowered or "every day" in lowered:
        return "daily", None
    if "weekly" in lowered:
        return "weekly", None
    for day in WEEKDAYS:
        if f"every {day}" in lowered:
            return "weekly", day
    return "none", None


def default_window(task_date: date, today: date) -> tuple[str, str]:
    if task_date == today:
        start, end = ("18:00", "22:00")
    elif task_date == today + timedelta(days=1):
        start, end = ("12:00", "20:00")
    else:
        start, end = ("09:00", "17:00")
    return start, end


def deterministic_parse(text: str, today_value: date) -> ParseResponse:
    chunks = [chunk.strip() for chunk in re.split(r"[\n\.;]+", text) if chunk.strip()]
    items: list[ParsedItem] = []
    for chunk in chunks:
        task_date = parse_date_token(chunk, today_value) or today_value
        due_time = parse_time_token(chunk)
        title = clean_title(chunk)
        priority = detect_priority(chunk)
        recurrence, recurrence_detail = detect_recurrence(chunk)
        if due_time:
            items.append(
                ParsedItem(
                    title=title,
                    date=task_date.isoformat(),
                    due_time=due_time,
                    window_start=None,
                    window_end=None,
                    priority=priority,
                    recurrence=recurrence,
                    recurrence_detail=recurrence_detail,
                    confidence=0.42,
                    notes=None,
                )
            )
        else:
            start, end = default_window(task_date, today_value)
            items.append(
                ParsedItem(
                    title=title,
                    date=task_date.isoformat(),
                    due_time=None,
                    window_start=f"{task_date.isoformat()}T{start}:00",
                    window_end=f"{task_date.isoformat()}T{end}:00",
                    priority=priority,
                    recurrence=recurrence,
                    recurrence_detail=recurrence_detail,
                    confidence=0.38,
                    notes=None,
                )
            )
    return ParseResponse(items=items)


def build_system_prompt() -> str:
    return (
        "You are a strict JSON generator. Return ONLY valid JSON that matches this schema: "
        "{items:[{title,date,due_time,window_start,window_end,priority,recurrence,recurrence_detail,confidence,notes}]}. "
        "priority must be low, med, or high. recurrence must be none, daily, weekly, every_2_days, or custom. "
        "Dates use YYYY-MM-DD. Times use HH:MM 24h. window_start/window_end use YYYY-MM-DDTHH:MM:SS. "
        "confidence is 0-1. Use null when unknown."
    )


def parse_with_llm(text: str) -> ParseResponse:
    client = LLMClient()
    messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": text},
    ]
    content = client.chat(messages, response_format={"type": "json_object"})
    data = json.loads(content)
    return ParseResponse.model_validate(data)


def parse_text(text: str, use_llm: bool) -> ParseResponse:
    today_value = date.today()
    if use_llm:
        try:
            return parse_with_llm(text)
        except (RuntimeError, json.JSONDecodeError, ValidationError, ValueError):
            return deterministic_parse(text, today_value)
    return deterministic_parse(text, today_value)


def items_from_response(parsed: ParseResponse) -> Iterable[ParsedItem]:
    return parsed.items
