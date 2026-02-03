from __future__ import annotations

from collections import defaultdict
from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session

from models import Event, Reminder, Settings, Task


def get_settings(session: Session) -> Settings:
    settings = session.query(Settings).first()
    if not settings:
        settings = Settings()
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def _parse_hhmm(value: str | None) -> time | None:
    if not value:
        return None
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _in_quiet_hours(scheduled_for: datetime, settings: Settings) -> bool:
    start = _parse_hhmm(settings.quiet_hours_start)
    end = _parse_hhmm(settings.quiet_hours_end)
    if not start or not end:
        return False
    current = scheduled_for.time()
    if start < end:
        return start <= current <= end
    return current >= start or current <= end


def _apply_quiet_hours(scheduled_for: datetime, settings: Settings) -> datetime:
    if not _in_quiet_hours(scheduled_for, settings):
        return scheduled_for
    end = _parse_hhmm(settings.quiet_hours_end)
    if not end:
        return scheduled_for
    adjusted = datetime.combine(scheduled_for.date(), end) + timedelta(minutes=5)
    if adjusted <= scheduled_for:
        adjusted += timedelta(days=1)
    return adjusted


def _within_daily_budget(session: Session, settings: Settings, scheduled_for: datetime) -> bool:
    day_start = datetime.combine(scheduled_for.date(), time(0, 0))
    day_end = day_start + timedelta(days=1)
    count = (
        session.query(Reminder)
        .filter(Reminder.scheduled_for >= day_start, Reminder.scheduled_for < day_end)
        .count()
    )
    return count < settings.daily_budget


def _learn_preferred_time(session: Session, task: Task) -> time | None:
    if not task.recurrence:
        return None
    cutoff = datetime.utcnow() - timedelta(days=30)
    events = (
        session.query(Event)
        .filter(
            Event.type == "task_done",
            Event.task_id == task.id,
            Event.ts >= cutoff,
        )
        .all()
    )
    if not events:
        return None
    buckets: dict[int, int] = defaultdict(int)
    for event in events:
        bucket = (event.ts.hour * 60 + event.ts.minute) // 30
        buckets[bucket] += 1
    best_bucket = max(buckets, key=buckets.get)
    hour = (best_bucket * 30) // 60
    minute = (best_bucket * 30) % 60
    return time(hour=hour, minute=minute)


def schedule_reminder(session: Session, task: Task) -> Reminder | None:
    settings = get_settings(session)
    scheduled_for: datetime | None = None
    if settings.policy_mode == "adaptive":
        preferred = _learn_preferred_time(session, task)
        if preferred and task.window_start and task.window_end:
            candidate = datetime.combine(task.window_start.date(), preferred)
            if task.window_start <= candidate <= task.window_end:
                scheduled_for = candidate
    if scheduled_for is None:
        if task.due_at:
            scheduled_for = task.due_at - timedelta(minutes=settings.lead_time_minutes)
        elif task.window_start:
            scheduled_for = task.window_start
    if not scheduled_for:
        return None
    scheduled_for = _apply_quiet_hours(scheduled_for, settings)
    if not _within_daily_budget(session, settings, scheduled_for):
        return None
    reminder = Reminder(task_id=task.id, scheduled_for=scheduled_for)
    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return reminder
