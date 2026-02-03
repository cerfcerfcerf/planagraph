from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Generator

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine, now_utc
from llm_client import LLMClient
from models import Event, Reminder, Settings, Task
from parser import parse_text
from policy import reschedule_for_task, schedule_task_reminder
from scheduler import ReminderScheduler
from schemas import (
    InsightsResponse,
    NowResponse,
    ParseRequest,
    ParseResponse,
    ReminderActionRequest,
    ReminderOut,
    SettingsOut,
    SettingsUpdate,
    TaskCreate,
    TaskOut,
    TaskUpdate,
)

load_dotenv()

app = FastAPI(title="Plangraph (Life OS)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = ReminderScheduler(interval_seconds=30)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_settings(session: Session) -> Settings:
    settings = session.query(Settings).first()
    if not settings:
        settings = Settings(
            policy_mode="baseline",
            daily_budget=6,
            quiet_hours_start="22:00",
            quiet_hours_end="07:00",
            lead_time_min=20,
        )
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def map_task(task: Task) -> TaskOut:
    return TaskOut(
        id=task.id,
        title=task.title,
        notes=task.notes,
        due_at=task.due_at,
        window_start=task.window_start,
        window_end=task.window_end,
        priority=task.priority,
        status=task.status,
        recurrence=task.recurrence,
        recurrence_detail=task.recurrence_detail,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def parse_datetime(date_value: str | None, time_value: str | None) -> datetime | None:
    if not date_value:
        return None
    if time_value:
        return datetime.fromisoformat(f"{date_value}T{time_value}:00")
    return None


@app.on_event("startup")
async def startup() -> None:
    Base.metadata.create_all(bind=engine)
    scheduler.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    scheduler.stop()


@app.post("/parse", response_model=ParseResponse)
async def parse_plan(request: ParseRequest) -> ParseResponse:
    use_llm = os.getenv("USE_LLM", "true").lower() == "true"
    return parse_text(request.text, use_llm=use_llm)


@app.get("/tasks", response_model=list[TaskOut])
async def list_tasks(session: Session = Depends(get_db)) -> list[TaskOut]:
    tasks = session.query(Task).order_by(Task.created_at.desc()).all()
    return [map_task(task) for task in tasks]


@app.post("/tasks", response_model=TaskOut)
async def create_task(payload: TaskCreate, session: Session = Depends(get_db)) -> TaskOut:
    due_at = parse_datetime(payload.date, payload.due_time)
    window_start = datetime.fromisoformat(payload.window_start) if payload.window_start else None
    window_end = datetime.fromisoformat(payload.window_end) if payload.window_end else None
    task = Task(
        title=payload.title,
        notes=payload.notes,
        due_at=due_at,
        window_start=window_start,
        window_end=window_end,
        priority=payload.priority,
        status=payload.status,
        recurrence=payload.recurrence,
        recurrence_detail=payload.recurrence_detail,
        created_at=now_utc(),
        updated_at=now_utc(),
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    settings = get_settings(session)
    schedule_task_reminder(session, task, settings)
    return map_task(task)


@app.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: int, payload: TaskUpdate, session: Session = Depends(get_db)) -> TaskOut:
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    data = payload.model_dump(exclude_unset=True)
    if "date" in data or "due_time" in data:
        date_value = data.get("date")
        time_value = data.get("due_time")
        task.due_at = parse_datetime(date_value, time_value)
    if "window_start" in data:
        task.window_start = datetime.fromisoformat(data["window_start"]) if data["window_start"] else None
    if "window_end" in data:
        task.window_end = datetime.fromisoformat(data["window_end"]) if data["window_end"] else None
    for field in ["title", "notes", "priority", "status", "recurrence", "recurrence_detail"]:
        if field in data:
            setattr(task, field, data[field])
    task.updated_at = now_utc()
    session.commit()
    session.refresh(task)
    settings = get_settings(session)
    reschedule_for_task(session, task, settings)
    return map_task(task)


@app.get("/settings", response_model=SettingsOut)
async def read_settings(session: Session = Depends(get_db)) -> SettingsOut:
    settings = get_settings(session)
    return SettingsOut(
        policy_mode=settings.policy_mode,
        daily_budget=settings.daily_budget,
        quiet_hours_start=settings.quiet_hours_start,
        quiet_hours_end=settings.quiet_hours_end,
        lead_time_min=settings.lead_time_min,
    )


@app.post("/settings", response_model=SettingsOut)
async def update_settings(payload: SettingsUpdate, session: Session = Depends(get_db)) -> SettingsOut:
    settings = get_settings(session)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(settings, field, value)
    settings.updated_at = now_utc()
    session.commit()
    session.refresh(settings)
    return SettingsOut(
        policy_mode=settings.policy_mode,
        daily_budget=settings.daily_budget,
        quiet_hours_start=settings.quiet_hours_start,
        quiet_hours_end=settings.quiet_hours_end,
        lead_time_min=settings.lead_time_min,
    )


@app.get("/now", response_model=NowResponse)
async def get_now(session: Session = Depends(get_db)) -> NowResponse:
    now = now_utc()
    reminders = (
        session.query(Reminder)
        .join(Task)
        .filter(Reminder.state.in_(["scheduled", "sent", "snoozed"]))
        .order_by(Reminder.scheduled_for.asc())
        .all()
    )
    next_best: Reminder | None = reminders[0] if reminders else None

    next_six = []
    later_today = []
    six_hours = now + timedelta(hours=6)
    end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=0)

    def reminder_out(reminder: Reminder) -> ReminderOut:
        return ReminderOut(
            id=reminder.id,
            task_id=reminder.task_id,
            title=reminder.task.title,
            scheduled_for=reminder.scheduled_for,
            state=reminder.state,
        )

    for reminder in reminders:
        if reminder.scheduled_for <= six_hours:
            next_six.append(reminder_out(reminder))
        elif reminder.scheduled_for <= end_of_day:
            later_today.append(reminder_out(reminder))

    why_now = "Based on your schedule and due times."
    use_llm = os.getenv("USE_LLM", "true").lower() == "true"
    if use_llm and next_best:
        client = LLMClient()
        prompt = (
            "Explain in one short sentence why this reminder is showing now. "
            "Keep it under 18 words."
        )
        message = {
            "role": "user",
            "content": f"Reminder: {next_best.task.title} at {next_best.scheduled_for.isoformat()}.",
        }
        try:
            why_now = client.chat([{"role": "system", "content": prompt}, message])
        except RuntimeError:
            why_now = "Based on your schedule and due times."

    return NowResponse(
        next_best_action=reminder_out(next_best) if next_best else None,
        next_6_hours=next_six,
        later_today=later_today,
        why_now=why_now,
    )


@app.post("/reminders/{reminder_id}/action", response_model=ReminderOut)
async def reminder_action(
    reminder_id: int,
    payload: ReminderActionRequest,
    session: Session = Depends(get_db),
) -> ReminderOut:
    reminder = session.get(Reminder, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    now = now_utc()

    if payload.action == "done":
        reminder.state = "done"
        reminder.task.status = "completed"
        session.add(
            Event(
                type="task_done",
                task_id=reminder.task_id,
                reminder_id=reminder.id,
                ts=now,
                payload_json=json.dumps({"action": "done"}),
            )
        )
    elif payload.action.startswith("snooze"):
        minutes = 10 if payload.action == "snooze_10" else 30
        reminder.state = "snoozed"
        new_reminder = Reminder(
            task_id=reminder.task_id,
            scheduled_for=now + timedelta(minutes=minutes),
            state="scheduled",
        )
        session.add(new_reminder)
        session.add(
            Event(
                type="reminder_snoozed",
                task_id=reminder.task_id,
                reminder_id=reminder.id,
                ts=now,
                payload_json=json.dumps({"snooze_minutes": minutes}),
            )
        )
    else:
        reminder.state = "dismissed"
        session.add(
            Event(
                type="reminder_dismissed",
                task_id=reminder.task_id,
                reminder_id=reminder.id,
                ts=now,
            )
        )

    session.commit()
    session.refresh(reminder)
    return ReminderOut(
        id=reminder.id,
        task_id=reminder.task_id,
        title=reminder.task.title,
        scheduled_for=reminder.scheduled_for,
        state=reminder.state,
    )


@app.get("/insights", response_model=InsightsResponse)
async def insights(session: Session = Depends(get_db)) -> InsightsResponse:
    events = session.query(Event).order_by(Event.ts.asc()).all()
    notifications: dict[str, int] = {}
    completions: dict[str, int] = {}
    for event in events:
        day = event.ts.date().isoformat()
        if event.type == "reminder_sent":
            notifications[day] = notifications.get(day, 0) + 1
        if event.type == "task_done":
            completions[day] = completions.get(day, 0) + 1

    all_days = sorted({*notifications.keys(), *completions.keys()})

    def series(data: dict[str, int]) -> list[dict[str, int]]:
        return [{"date": day, "value": data.get(day, 0)} for day in all_days]

    notifications_series = series(notifications)
    completions_series = series(completions)
    ratio_series = []
    missed_series = []
    for day in all_days:
        notif = notifications.get(day, 0)
        comp = completions.get(day, 0)
        ratio = int(notif / comp) if comp else notif
        missed = max(notif - comp, 0)
        ratio_series.append({"date": day, "value": ratio})
        missed_series.append({"date": day, "value": missed})

    return InsightsResponse(
        notifications_per_day=notifications_series,
        completions_per_day=completions_series,
        notifications_per_completion=ratio_series,
        missed_rate_proxy=missed_series,
    )


@app.post("/seed")
async def seed(session: Session = Depends(get_db)) -> dict[str, str]:
    if os.getenv("ALLOW_SEED", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="Seed disabled")
    session.query(Event).delete()
    session.query(Reminder).delete()
    session.query(Task).delete()
    session.commit()

    now = datetime.utcnow().replace(microsecond=0)
    tasks = [
        Task(
            title="Write quarterly roadmap",
            notes="Draft and share with leadership",
            due_at=now + timedelta(hours=4),
            priority="high",
            status="active",
            recurrence="none",
            created_at=now,
            updated_at=now,
        ),
        Task(
            title="Team standup prep",
            notes="Collect blockers",
            window_start=now + timedelta(hours=1),
            window_end=now + timedelta(hours=5),
            priority="med",
            status="active",
            recurrence="daily",
            recurrence_detail="weekdays",
            created_at=now,
            updated_at=now,
        ),
    ]
    session.add_all(tasks)
    session.commit()
    for task in tasks:
        schedule_task_reminder(session, task, get_settings(session))
    return {"status": "seeded"}
