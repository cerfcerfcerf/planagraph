from __future__ import annotations

from collections import Counter
from datetime import datetime, time, timedelta
from typing import Iterable, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from db import utcnow
from models import Event, Reminder, Settings, Task


def _in_quiet_hours(ts: datetime, quiet_start: time, quiet_end: time) -> bool:
    current = ts.time()
    if quiet_start < quiet_end:
        return quiet_start <= current < quiet_end
    return current >= quiet_start or current < quiet_end


def _shift_out_of_quiet(ts: datetime, quiet_start: time, quiet_end: time) -> datetime:
    if quiet_start < quiet_end:
        if quiet_start <= ts.time() < quiet_end:
            return ts.replace(hour=quiet_end.hour, minute=quiet_end.minute)
        return ts
    if ts.time() >= quiet_start or ts.time() < quiet_end:
        return ts.replace(hour=quiet_end.hour, minute=quiet_end.minute)
    return ts


def _daily_budget_ok(session: Session, day: datetime, budget: int) -> bool:
    start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    count = session.query(Reminder).filter(Reminder.scheduled_for >= start, Reminder.scheduled_for < end).count()
    return count < budget


def _recurring_peak(session: Session, task_id: int) -> Optional[time]:
    rows = session.execute(
        select(Event.ts).where(Event.type == "task_done", Event.task_id == task_id)
    ).scalars()
    bins: Counter[int] = Counter()
    for ts in rows:
        bucket = (ts.hour * 60 + ts.minute) // 30
        bins[bucket] += 1
    if not bins:
        return None
    best_bucket = bins.most_common(1)[0][0]
    minutes = best_bucket * 30
    return time(hour=minutes // 60, minute=minutes % 60)


def _default_reminder_time(task: Task, lead_time_min: int) -> Optional[datetime]:
    if task.due_at:
        return task.due_at - timedelta(minutes=lead_time_min)
    if task.window_start:
        return task.window_start
    return None


def schedule_reminder(session: Session, task: Task, settings: Settings) -> Optional[Reminder]:
    base_time = _default_reminder_time(task, settings.lead_time_min)
    if base_time is None:
        return None
    if settings.policy_mode == "adaptive" and task.recurrence:
        peak = _recurring_peak(session, task.id)
        if peak and task.window_start:
            base_time = task.window_start.replace(hour=peak.hour, minute=peak.minute)
    quiet_start = datetime.strptime(settings.quiet_hours_start, "%H:%M").time()
    quiet_end = datetime.strptime(settings.quiet_hours_end, "%H:%M").time()
    base_time = _shift_out_of_quiet(base_time, quiet_start, quiet_end)
    if not _daily_budget_ok(session, base_time, settings.daily_budget):
        return None
    reminder = Reminder(task_id=task.id, scheduled_for=base_time, state="scheduled")
    session.add(reminder)
    session.flush()
    return reminder


def schedule_for_tasks(session: Session, tasks: Iterable[Task]) -> None:
    settings = session.query(Settings).get(1)
    if settings is None:
        settings = Settings(id=1)
        session.add(settings)
        session.flush()
    for task in tasks:
        session.execute(
            delete(Reminder).where(Reminder.task_id == task.id, Reminder.state == "scheduled")
        )
        schedule_reminder(session, task, settings)


def ensure_default_settings(session: Session) -> Settings:
    settings = session.query(Settings).get(1)
    if settings is None:
        settings = Settings(id=1)
        session.add(settings)
        session.flush()
    return settings


def mark_due_reminders(session: Session) -> list[Reminder]:
    now = utcnow()
    reminders = (
        session.query(Reminder)
        .filter(Reminder.state == "scheduled", Reminder.scheduled_for <= now)
        .all()
    )
    for reminder in reminders:
        reminder.state = "sent"
        session.add(
            Event(
                type="reminder_sent",
                task_id=reminder.task_id,
                reminder_id=reminder.id,
                ts=now,
            )
        )
    return reminders
