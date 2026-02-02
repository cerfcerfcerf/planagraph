from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Iterable, Optional

import db
from models import PlannedItem, ScheduleItem

DEFAULT_LEADS = {
    "event": 15,
    "task": 10,
    "reminder": 10,
}

ANCHOR_HINTS = ["before", "when leaving", "leave home", "for school", "before school", "after school"]
ESSENTIALS_HINTS = ["essentials", "don't forget", "do not forget", "remember"]
ESSENTIALS_KEYWORDS = ["headphones", "keys", "wallet", "bottle", "passport", "charger"]


def parse_time(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def format_time(minutes_since_midnight: int) -> str:
    hours = minutes_since_midnight // 60
    minutes = minutes_since_midnight % 60
    return f"{hours:02d}:{minutes:02d}"


def combine_date_time(day: str, time_value: str) -> str:
    return f"{day}T{time_value}:00"


def time_context(time_value: str) -> str:
    minutes = parse_time(time_value)
    if minutes < 12 * 60:
        return "morning"
    if minutes < 17 * 60:
        return "afternoon"
    return "evening"


def reminder_message(kind: str, title: str, time_value: Optional[str], lead_min: int, context: str) -> tuple[str, str]:
    if kind == "ending":
        return (f"Wrap up {title} — {lead_min} minutes left.", f"{context.title()} wrap-up reminder.")
    if kind == "contextual":
        return (f"Before you go: {title}.", f"{context.title()} essentials reminder.")
    if kind == "habit":
        return (f"Keep it going: {title}.", f"{context.title()} habit reminder.")
    if time_value:
        return (f"It’s almost time for {title} ({time_value}).", f"{context.title()} upcoming reminder.")
    return (f"Quick one: {title}.", f"{context.title()} reminder.")


def build_suppression_key(rule_id: Optional[int], item_id: Optional[int], signature: str) -> str:
    return f"{rule_id or 'none'}:{item_id or 'none'}:{signature}"


def should_suppress(rule_id: Optional[int], item_id: Optional[int], signature: str) -> bool:
    key = build_suppression_key(rule_id, item_id, signature)
    if db.is_suppressed(key):
        return True
    if item_id:
        item_key = build_suppression_key(rule_id, item_id, "item")
        return db.is_suppressed(item_key)
    return False


def generate_event_reminders(plan_id: int, planned_items: Iterable[PlannedItem]) -> list[int]:
    reminder_ids: list[int] = []
    for item in planned_items:
        if not item.planned_start:
            continue
        if should_suppress(None, item.id, "upcoming"):
            continue
        lead_min = DEFAULT_LEADS.get(item.type, 10)
        start_minutes = parse_time(item.planned_start)
        due_minutes = max(0, start_minutes - lead_min)
        due_at = combine_date_time(item.date or "", format_time(due_minutes))
        context = time_context(item.planned_start)
        title, body = reminder_message("upcoming", item.title, item.planned_start, lead_min, context)
        reason = f"Reminder set {lead_min} minutes before {item.title}."
        reminder_ids.append(
            db.insert_reminder_event(
                {
                    "rule_id": None,
                    "item_id": item.id,
                    "plan_id": plan_id,
                    "due_at": due_at,
                    "kind": "upcoming",
                    "title": title,
                    "body": body,
                    "status": "pending",
                    "reason": reason,
                    "created_at": db.now_iso(),
                    "delivered_at": None,
                    "snoozed_until": None,
                }
            )
        )
        if item.planned_end and item.duration_min > 60:
            if should_suppress(None, item.id, "ending"):
                continue
            end_minutes = parse_time(item.planned_end)
            end_due_minutes = max(0, end_minutes - 10)
            end_due_at = combine_date_time(item.date or "", format_time(end_due_minutes))
            end_context = time_context(item.planned_end)
            end_title, end_body = reminder_message("ending", item.title, item.planned_end, 10, end_context)
            reminder_ids.append(
                db.insert_reminder_event(
                    {
                        "rule_id": None,
                        "item_id": item.id,
                        "plan_id": plan_id,
                        "due_at": end_due_at,
                        "kind": "ending",
                        "title": end_title,
                        "body": end_body,
                        "status": "pending",
                        "reason": "Long event ending soon.",
                        "created_at": db.now_iso(),
                        "delivered_at": None,
                        "snoozed_until": None,
                    }
                )
            )
    return reminder_ids


def attach_contextual_reminders(
    plan_id: int,
    day: str,
    day_start: str,
    planned_items: Iterable[PlannedItem],
    parsed_items: Iterable[ScheduleItem],
) -> list[int]:
    reminder_ids: list[int] = []
    anchor_items = [item for item in planned_items if item.planned_start and item.type == "event"]
    if not anchor_items:
        anchor_items = [item for item in planned_items if item.planned_start]
    anchor_items.sort(key=lambda item: item.planned_start or "99:99")

    for item in parsed_items:
        if item.type != "reminder" or item.start_time or item.end_time:
            continue
        if should_suppress(None, item.id, "contextual"):
            continue
        content = f"{item.title} {item.notes or ''}".lower()
        anchor = None
        reason = None
        lead_min = 10
        if anchor_items:
            anchor = anchor_items[0]
            if any(hint in content for hint in ANCHOR_HINTS):
                reason = f"Attached to '{anchor.title}' because the note suggests an anchor event."
            else:
                reason = f"Attached to '{anchor.title}' because it is the first scheduled item."
            if any(hint in content for hint in ESSENTIALS_HINTS) or any(keyword in content for keyword in ESSENTIALS_KEYWORDS):
                reason = f"Essentials reminder anchored to '{anchor.title}'."
                lead_min = 15
        if anchor and anchor.planned_start:
            anchor_minutes = parse_time(anchor.planned_start)
            due_minutes = max(0, anchor_minutes - lead_min)
            due_at = combine_date_time(day, format_time(due_minutes))
        else:
            start_minutes = parse_time(day_start)
            due_minutes = start_minutes + 30
            due_at = combine_date_time(day, format_time(due_minutes))
            reason = "No anchor found; scheduled shortly after day start."
        due_time = format_time(due_minutes)
        context = time_context(due_time)
        title, body = reminder_message("contextual", item.title, due_time, lead_min, context)
        reminder_ids.append(
            db.insert_reminder_event(
                {
                    "rule_id": None,
                    "item_id": item.id,
                    "plan_id": plan_id,
                    "due_at": due_at,
                    "kind": "contextual",
                    "title": title,
                    "body": body,
                    "status": "pending",
                    "reason": reason,
                    "created_at": db.now_iso(),
                    "delivered_at": None,
                    "snoozed_until": None,
                }
            )
        )
    return reminder_ids


def compute_typical_time(rule_id: int) -> Optional[int]:
    rows = db.list_recent_completions(rule_id, limit=14)
    if len(rows) < 4:
        return None
    minutes = []
    for row in rows:
        completed_at = row["completed_at"]
        timestamp = datetime.fromisoformat(completed_at)
        minutes.append(timestamp.hour * 60 + timestamp.minute)
    return int(median(minutes))


def choose_weekdays(target_per_week: int) -> set[int]:
    if target_per_week <= 0:
        return set()
    spacing = 7 / target_per_week
    return {int(round(i * spacing)) % 7 for i in range(target_per_week)}


def generate_habit_reminders(day: str) -> list[int]:
    reminder_ids: list[int] = []
    rules = db.list_reminder_rules()
    day_date = datetime.fromisoformat(day)
    week_start = (day_date - timedelta(days=day_date.weekday())).date().isoformat()
    week_end = (datetime.fromisoformat(week_start) + timedelta(days=7)).date().isoformat()

    for rule in rules:
        if not rule["enabled"]:
            continue
        if should_suppress(rule["id"], None, f"habit:{week_start}"):
            continue
        target_per_week = rule["target_per_week"]
        if target_per_week:
            completed = db.count_week_completions(rule["id"], week_start, week_end)
            if completed >= target_per_week:
                continue
            if day_date.weekday() not in choose_weekdays(target_per_week):
                continue
        typical_minutes = compute_typical_time(rule["id"])
        if typical_minutes is None:
            default_time = rule["default_time"] or "09:00"
            typical_minutes = parse_time(default_time)
        lead_min = rule["lead_min"]
        due_minutes = max(0, typical_minutes - lead_min)
        due_time = format_time(due_minutes)
        due_at = combine_date_time(day, due_time)
        context = time_context(due_time)
        title, body = reminder_message("habit", rule["title"], due_time, lead_min, context)
        reminder_ids.append(
            db.insert_reminder_event(
                {
                    "rule_id": rule["id"],
                    "item_id": None,
                    "plan_id": None,
                    "due_at": due_at,
                    "kind": "habit",
                    "title": title,
                    "body": body,
                    "status": "pending",
                    "reason": "Scheduled from habit pattern.",
                    "created_at": db.now_iso(),
                    "delivered_at": None,
                    "snoozed_until": None,
                }
            )
        )
    return reminder_ids


def generate_single_item_reminder(item: ScheduleItem) -> Optional[int]:
    if not item.date or not item.start_time:
        return None
    if should_suppress(None, item.id, "upcoming"):
        return None
    lead_min = DEFAULT_LEADS.get(item.type, 10)
    start_minutes = parse_time(item.start_time)
    due_minutes = max(0, start_minutes - lead_min)
    due_time = format_time(due_minutes)
    due_at = combine_date_time(item.date, due_time)
    context = time_context(due_time)
    title, body = reminder_message("upcoming", item.title, item.start_time, lead_min, context)
    return db.insert_reminder_event(
        {
            "rule_id": None,
            "item_id": item.id,
            "plan_id": None,
            "due_at": due_at,
            "kind": "upcoming",
            "title": title,
            "body": body,
            "status": "pending",
            "reason": "Quick add reminder.",
            "created_at": db.now_iso(),
            "delivered_at": None,
            "snoozed_until": None,
        }
    )
