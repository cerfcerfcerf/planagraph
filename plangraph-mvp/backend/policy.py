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


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _minutes_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / 60


def _time_target(task: Task) -> datetime | None:
    return task.window_end or task.due_at or task.window_start


def _closing_soon(task: Task, now: datetime, threshold_minutes: int = 60) -> bool:
    target = _time_target(task)
    if not target:
        return False
    return 0 <= _minutes_between(now, target) <= threshold_minutes


def is_actionable_now(task: Task, now: datetime, settings: Settings) -> bool:
    if task.status != "active":
        return False
    if task.window_start and task.window_end:
        early_margin = min(settings.lead_time_minutes, 30)
        if now < task.window_start - timedelta(minutes=early_margin):
            return False
        return now <= task.window_end
    if task.due_at:
        lead_time = timedelta(minutes=settings.lead_time_minutes)
        grace = timedelta(minutes=30)
        return task.due_at - lead_time <= now <= task.due_at + grace
    return task.created_at.date() == now.date()


def should_fire(reminder: Reminder, task: Task, now: datetime, settings: Settings) -> bool:
    return (
        reminder.state == "scheduled"
        and reminder.scheduled_for <= now
        and is_actionable_now(task, now, settings)
    )


def is_occurrence_expired(task: Task, now: datetime, settings: Settings) -> bool:
    if task.window_end:
        return now > task.window_end
    if task.due_at:
        return now > task.due_at + timedelta(minutes=30)
    return task.created_at.date() < now.date()


def _ignored_recently(task: Task) -> bool:
    reminders = sorted(
        (task.reminders or []),
        key=lambda reminder: reminder.scheduled_for,
        reverse=True,
    )
    recent = reminders[:2]
    if len(recent) < 2:
        return False
    return all(reminder.state in {"dismissed", "expired"} for reminder in recent)


def urgency_score(task: Task, now: datetime) -> float:
    routine_types = {"meal", "sleep", "medication", "hygiene"}
    if task.window_start and task.window_end:
        minutes_to_close = _minutes_between(now, task.window_end)
        base = 100 - _clamp(minutes_to_close, 0, 300) / 3
    elif task.due_at:
        minutes_to_due = _minutes_between(now, task.due_at)
        base = 100 - _clamp(minutes_to_due, -60, 240) / 3
    else:
        base = 50
    base = _clamp(base, 0, 100)
    priority_weight = {"low": 0, "med": 10, "high": 25}.get(task.priority, 10)
    routine_boost = 15 if task.task_type in routine_types else 0
    overdue_boost = 10 if task.due_at and _minutes_between(now, task.due_at) < 0 else 0
    ignore_penalty = 10 if task.priority != "high" and _ignored_recently(task) else 0
    return base + priority_weight + routine_boost + overdue_boost - ignore_penalty


def build_explanation(task: Task, now: datetime) -> dict[str, object]:
    reasons: list[str] = []
    if task.window_start and task.window_end:
        minutes_to_close = _minutes_between(now, task.window_end)
        if minutes_to_close >= 0:
            reasons.append(f"window closes in {int(round(minutes_to_close))}m")
    elif task.due_at:
        minutes_to_due = _minutes_between(now, task.due_at)
        if minutes_to_due >= 0:
            reasons.append(f"due in {int(round(minutes_to_due))}m")
        else:
            reasons.append(f"overdue by {int(round(abs(minutes_to_due)))}m")
    else:
        reasons.append("scheduled for today")
    if task.task_type in {"meal", "sleep", "medication", "hygiene"}:
        reasons.append(f"routine: {task.task_type}")
    if task.priority == "high":
        reasons.append("high priority")
    elif task.priority == "med":
        reasons.append("medium priority")
    if task.priority != "high" and _ignored_recently(task):
        reasons.append("ignored recently")
    return {"reasons": reasons, "score": round(urgency_score(task, now))}


def roll_task_forward(task: Task) -> bool:
    recurrence_map = {"daily": 1, "every_2_days": 2, "weekly": 7}
    delta_days = recurrence_map.get(task.recurrence or "")
    if not delta_days:
        return False
    if task.due_at:
        task.due_at = task.due_at + timedelta(days=delta_days)
    if task.window_start and task.window_end:
        duration = task.window_end - task.window_start
        if duration.total_seconds() <= 0 and task.window_end.time() < task.window_start.time():
            start_date = task.window_start.date()
            duration = (
                datetime.combine(start_date + timedelta(days=1), task.window_end.time())
                - datetime.combine(start_date, task.window_start.time())
            )
        new_start = task.window_start + timedelta(days=delta_days)
        task.window_start = new_start
        task.window_end = new_start + duration
    elif task.window_start:
        task.window_start = task.window_start + timedelta(days=delta_days)
    elif task.window_end:
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
        if not (
            task.priority == "high"
            or _closing_soon(task, scheduled_for, threshold_minutes=60)
        ):
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
    tasks = session.query(Task).filter(Task.status == "active").all()
    candidates: list[Task] = []
    for task in tasks:
        target = _time_target(task)
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
    k_limit = min(settings.daily_budget, 6)
    slots = min(remaining_budget, k_limit) if remaining_budget > 0 else k_limit
    for task in candidates[:slots]:
        schedule_reminder(session, task)
