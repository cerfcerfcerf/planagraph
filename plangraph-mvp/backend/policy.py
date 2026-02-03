from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database import now_utc
from models import Event, Reminder, Settings, Task


def _parse_time(value: str) -> tuple[int, int]:
    hours, minutes = value.split(":")
    return int(hours), int(minutes)


def _apply_quiet_hours(scheduled_for: datetime, settings: Settings) -> datetime:
    if not settings.quiet_hours_start or not settings.quiet_hours_end:
        return scheduled_for
    start_h, start_m = _parse_time(settings.quiet_hours_start)
    end_h, end_m = _parse_time(settings.quiet_hours_end)
    quiet_start = scheduled_for.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    quiet_end = scheduled_for.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
    if quiet_start <= quiet_end:
        if quiet_start <= scheduled_for <= quiet_end:
            return quiet_end + timedelta(minutes=5)
    else:
        if scheduled_for >= quiet_start or scheduled_for <= quiet_end:
            return quiet_end + timedelta(minutes=5)
    return scheduled_for


def _completion_histogram(session: Session, task_id: int) -> Counter[int]:
    rows = (
        session.query(Event)
        .filter(Event.type == "task_done", Event.task_id == task_id)
        .order_by(Event.ts.desc())
        .limit(50)
        .all()
    )
    counter: Counter[int] = Counter()
    for row in rows:
        minutes = row.ts.hour * 60 + row.ts.minute
        bucket = minutes // 30
        counter[bucket] += 1
    return counter


def _adaptive_time(task: Task, session: Session) -> datetime | None:
    histogram = _completion_histogram(session, task.id)
    if sum(histogram.values()) < 3:
        return None
    best_bucket = histogram.most_common(1)[0][0]
    minutes = best_bucket * 30
    hour = minutes // 60
    minute = minutes % 60
    if task.window_start and task.window_end:
        candidate = task.window_start.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate < task.window_start:
            candidate = task.window_start
        if candidate > task.window_end:
            candidate = task.window_end - timedelta(minutes=10)
        return candidate
    if task.due_at:
        return task.due_at.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return None


def _lead_time(settings: Settings) -> int:
    return settings.lead_time_min or 20


def _budget_exceeded(session: Session, scheduled_for: datetime, settings: Settings) -> bool:
    day_start = scheduled_for.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    count = (
        session.query(Reminder)
        .filter(
            Reminder.scheduled_for >= day_start,
            Reminder.scheduled_for < day_end,
            Reminder.state == "scheduled",
        )
        .count()
    )
    return count >= settings.daily_budget


def schedule_task_reminder(session: Session, task: Task, settings: Settings) -> Reminder | None:
    if task.status != "active":
        return None

    scheduled_for: datetime | None = None
    lead = _lead_time(settings)

    if settings.policy_mode == "adaptive" and task.recurrence and task.recurrence != "none":
        scheduled_for = _adaptive_time(task, session)

    if not scheduled_for:
        if task.due_at:
            scheduled_for = task.due_at - timedelta(minutes=lead)
        elif task.window_start:
            scheduled_for = task.window_start

    if not scheduled_for:
        return None

    scheduled_for = _apply_quiet_hours(scheduled_for, settings)

    if _budget_exceeded(session, scheduled_for, settings):
        return None

    reminder = Reminder(
        task_id=task.id,
        scheduled_for=scheduled_for,
        state="scheduled",
    )
    session.add(reminder)
    session.commit()
    session.refresh(reminder)

    event = Event(
        type="task_created",
        task_id=task.id,
        reminder_id=reminder.id,
        ts=now_utc(),
        payload_json=json.dumps({"scheduled_for": reminder.scheduled_for.isoformat()}),
    )
    session.add(event)
    session.commit()
    return reminder


def reschedule_for_task(session: Session, task: Task, settings: Settings) -> Reminder | None:
    for reminder in task.reminders:
        if reminder.state in {"scheduled", "sent", "snoozed"}:
            reminder.state = "expired"
    session.commit()
    return schedule_task_reminder(session, task, settings)
