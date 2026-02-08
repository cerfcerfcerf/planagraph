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


def infer_priority(title: str, notes: str | None = None) -> str:
    lowered = f"{title} {notes or ''}".lower()
    if any(keyword in lowered for keyword in ["exam", "test", "submit", "due", "meeting", "flight", "doctor", "medication", "visa", "deadline"]):
        return "high"
    if any(keyword in lowered for keyword in ["optional", "maybe", "if time", "chill"]):
        return "low"
    return "med"


def infer_task_type(title: str) -> str:
    lowered = title.lower()
    if any(keyword in lowered for keyword in ["meal", "breakfast", "lunch", "dinner", "sleep", "wake", "hygiene", "shower", "medication"]):
        return "routine"
    if any(keyword in lowered for keyword in ["doctor", "dentist", "meeting", "appointment", "flight"]):
        return "appointment"
    if any(keyword in lowered for keyword in ["class", "lecture", "lab", "study", "homework"]):
        return "study"
    if any(keyword in lowered for keyword in ["exercise", "gym", "workout", "run", "yoga"]):
        return "exercise"
    return "other"


def is_actionable_now(task: Task, now: datetime, settings: Settings) -> bool:
    if task.status != "active":
        return False
    if task.window_start and task.window_end:
        if now < task.window_start - timedelta(minutes=settings.lead_time_minutes):
            return False
        if now > task.window_end:
            return False
    if task.due_at:
        grace = task.due_at + timedelta(minutes=30)
        if now > grace:
            return False
    return True


def should_fire(reminder: Reminder, task: Task, now: datetime, settings: Settings) -> bool:
    if task.window_start and now < task.window_start - timedelta(minutes=settings.lead_time_minutes):
        return False
    if task.window_end and now > task.window_end:
        return False
    if task.due_at and now > task.due_at + timedelta(minutes=30):
        return False
    return True


def urgency_score(task: Task, now: datetime) -> float:
    priority_weights = {"low": 0.8, "med": 1.0, "high": 1.4}
    routine_boost = 0.15 if task.task_type == "routine" else 0.0
    base = priority_weights.get(task.priority, 1.0) + routine_boost
    time_target = task.window_end or task.due_at or task.window_start
    if not time_target:
        return base
    minutes_remaining = (time_target - now).total_seconds() / 60
    if minutes_remaining <= 0:
        overdue_boost = 0.5
    else:
        overdue_boost = 0.0
    urgency = base + overdue_boost + max(0.0, 120 - minutes_remaining) / 120
    return urgency


def roll_task_forward(task: Task) -> bool:
    recurrence_map = {"daily": 1, "every_2_days": 2, "weekly": 7}
    delta_days = recurrence_map.get(task.recurrence or "")
    if not delta_days:
        return False
    if task.due_at:
        task.due_at = task.due_at + timedelta(days=delta_days)
    if task.window_start:
        task.window_start = task.window_start + timedelta(days=delta_days)
    if task.window_end:
        task.window_end = task.window_end + timedelta(days=delta_days)
    task.status = "active"
    return True


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


def schedule_upcoming_reminders(session: Session, now: datetime) -> None:
    settings = get_settings(session)
    upcoming_window = now + timedelta(hours=6)
    day_start = datetime.combine(now.date(), time(0, 0))
    day_end = day_start + timedelta(days=1)
    existing_count = (
        session.query(Reminder)
        .filter(Reminder.scheduled_for >= day_start, Reminder.scheduled_for < day_end)
        .count()
    )
    remaining_budget = max(settings.daily_budget - existing_count, 0)
    if remaining_budget <= 0:
        return
    tasks = (
        session.query(Task)
        .filter(Task.status == "active")
        .all()
    )
    candidates = []
    for task in tasks:
        target = task.due_at or task.window_start
        if not target or target > upcoming_window:
            continue
        has_reminder = (
            session.query(Reminder)
            .filter(Reminder.task_id == task.id, Reminder.state == "scheduled")
            .count()
            > 0
        )
        if has_reminder:
            continue
        if not is_actionable_now(task, now, settings):
            continue
        candidates.append(task)
    candidates.sort(key=lambda task: urgency_score(task, now), reverse=True)
    for task in candidates[:remaining_budget]:
        schedule_reminder(session, task)
