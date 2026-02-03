from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any, Iterable

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal, init_db
from llm_client import LLMClient
from models import Event, Reminder, Task
from parser import deterministic_parse
from policy import get_settings, schedule_reminder
from scheduler import ReminderScheduler
from schemas import (
    InsightsResponse,
    NowAction,
    NowResponse,
    ParseRequest,
    ParseResponse,
    ReminderActionRequest,
    ReminderOut,
    SettingsOut,
    SettingsUpdate,
    TaskCreate,
    TaskListResponse,
    TaskOut,
    TaskUpdate,
)

load_dotenv()

USE_LLM = os.getenv("USE_LLM", "true").lower() == "true"

app = FastAPI(title="Plangraph (Life OS)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

scheduler = ReminderScheduler()


@app.on_event("startup")
async def startup() -> None:
    init_db()
    scheduler.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    scheduler.stop()


def get_db() -> Iterable[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _parse_llm_items(text: str) -> list[dict[str, Any]] | None:
    client = LLMClient()
    schema_hint = (
        "{items:[{title:string,date:'YYYY-MM-DD|null',due_time:'HH:MM|null',"
        "window_start:'YYYY-MM-DDTHH:MM:SS|null',window_end:'YYYY-MM-DDTHH:MM:SS|null',"
        "priority:'low|med|high',recurrence:'none|daily|weekly|every_2_days|custom',"
        "recurrence_detail:'string|null',confidence:number,notes:'string|null'}]}"
    )
    try:
        response = client.parse_plan(text, schema_hint)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = json.loads(content)
        validated = ParseResponse.model_validate(parsed)
        return [item.model_dump() for item in validated.items]
    except (RuntimeError, json.JSONDecodeError, ValidationError):
        return None


def _parse_text(text: str) -> ParseResponse:
    items: list[dict[str, Any]] | None = None
    if USE_LLM:
        items = _parse_llm_items(text)
    if items is None:
        items = [item.model_dump() for item in deterministic_parse(text)]
    return ParseResponse(items=items)


@app.post("/parse", response_model=ParseResponse)
async def parse_text(request: ParseRequest) -> ParseResponse:
    return _parse_text(request.text)


@app.get("/tasks", response_model=TaskListResponse)
async def list_tasks(db: Session = Depends(get_db)) -> TaskListResponse:
    tasks = db.execute(select(Task).order_by(Task.created_at.desc())).scalars().all()
    return TaskListResponse(tasks=[TaskOut.model_validate(task) for task in tasks])


@app.post("/tasks", response_model=TaskListResponse)
async def create_tasks(
    tasks: list[TaskCreate],
    db: Session = Depends(get_db),
) -> TaskListResponse:
    created: list[Task] = []
    for payload in tasks:
        task = Task(**payload.model_dump())
        db.add(task)
        db.flush()
        db.add(Event(type="task_created", task_id=task.id, reminder_id=None))
        created.append(task)
    db.commit()
    for task in created:
        schedule_reminder(db, task)
    db.commit()
    return TaskListResponse(tasks=[TaskOut.model_validate(task) for task in created])


@app.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
) -> TaskOut:
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, field, value)
    db.add(task)
    db.commit()
    db.refresh(task)
    return TaskOut.model_validate(task)


@app.get("/settings", response_model=SettingsOut)
async def get_settings_route(db: Session = Depends(get_db)) -> SettingsOut:
    settings = get_settings(db)
    return SettingsOut.model_validate(settings)


@app.post("/settings", response_model=SettingsOut)
async def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
) -> SettingsOut:
    settings = get_settings(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, field, value)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return SettingsOut.model_validate(settings)


def _summarize_action(reminder: Reminder, task: Task) -> str:
    when = reminder.scheduled_for.strftime("%H:%M")
    return f"{task.title} at {when}"


def _generate_why_now(task: Task, reminder: Reminder | None) -> str:
    default = "This keeps your plan on track while the window is open."
    if not USE_LLM:
        return default
    client = LLMClient()
    prompt = f"Task: {task.title}. Priority: {task.priority}."
    if reminder:
        prompt += f" Scheduled for {reminder.scheduled_for.isoformat()}."
    try:
        response = client.why_now(prompt)
        return response or default
    except RuntimeError:
        return default


@app.get("/now", response_model=NowResponse)
async def now_view(db: Session = Depends(get_db)) -> NowResponse:
    now = datetime.utcnow()
    next_window = now + timedelta(hours=6)
    end_of_day = datetime.combine(now.date(), datetime.max.time())
    reminders = (
        db.execute(
            select(Reminder)
            .where(Reminder.state == "scheduled")
            .order_by(Reminder.scheduled_for.asc())
        )
        .scalars()
        .all()
    )
    next_6 = [r for r in reminders if now <= r.scheduled_for <= next_window]
    later = [r for r in reminders if next_window < r.scheduled_for <= end_of_day]

    next_action: NowAction | None = None
    if reminders:
        reminder = reminders[0]
        task = db.get(Task, reminder.task_id)
        if task:
            next_action = NowAction(
                reminder_id=reminder.id,
                task_id=task.id,
                title=task.title,
                scheduled_for=reminder.scheduled_for,
                window_start=task.window_start,
                window_end=task.window_end,
                priority=task.priority,
                why_now=_generate_why_now(task, reminder),
            )

    return NowResponse(
        next_best_action=next_action,
        next_6_hours=[ReminderOut.model_validate(r) for r in next_6],
        later_today=[ReminderOut.model_validate(r) for r in later],
    )


@app.post("/reminders/{reminder_id}/action", response_model=ReminderOut)
async def reminder_action(
    reminder_id: int,
    payload: ReminderActionRequest,
    db: Session = Depends(get_db),
) -> ReminderOut:
    reminder = db.get(Reminder, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    task = db.get(Task, reminder.task_id)
    now = datetime.utcnow()
    if payload.action == "done":
        reminder.state = "done"
        if task:
            task.status = "completed"
            db.add(Event(type="task_done", task_id=task.id, reminder_id=reminder.id))
            if task.recurrence and task.recurrence != "none":
                recurrence_map = {
                    "daily": 1,
                    "every_2_days": 2,
                    "weekly": 7,
                }
                delta_days = recurrence_map.get(task.recurrence)
                if delta_days and task.due_at:
                    task.due_at = task.due_at + timedelta(days=delta_days)
                    task.status = "active"
                    schedule_reminder(db, task)
    elif payload.action == "dismiss":
        reminder.state = "dismissed"
        db.add(Event(type="reminder_dismissed", task_id=task.id, reminder_id=reminder.id))
    elif payload.action in {"snooze_10", "snooze_30"}:
        minutes = 10 if payload.action == "snooze_10" else 30
        reminder.state = "snoozed"
        new_reminder = Reminder(
            task_id=reminder.task_id, scheduled_for=now + timedelta(minutes=minutes)
        )
        db.add(new_reminder)
        db.add(Event(type="reminder_snoozed", task_id=task.id, reminder_id=reminder.id))
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
    db.commit()
    db.refresh(reminder)
    return ReminderOut.model_validate(reminder)


@app.get("/insights", response_model=InsightsResponse)
async def insights(db: Session = Depends(get_db)) -> InsightsResponse:
    events = db.execute(select(Event).order_by(Event.ts.asc())).scalars().all()
    daily: dict[str, dict[str, int]] = {}
    for event in events:
        day = event.ts.date().isoformat()
        daily.setdefault(day, {"notifications": 0, "completions": 0, "sent": 0})
        if event.type == "reminder_sent":
            daily[day]["notifications"] += 1
            daily[day]["sent"] += 1
        if event.type == "task_done":
            daily[day]["completions"] += 1
    notifications_per_day = [
        {"date": day, "value": values["notifications"]}
        for day, values in daily.items()
    ]
    completions_per_day = [
        {"date": day, "value": values["completions"]}
        for day, values in daily.items()
    ]
    missed_rate_proxy = [
        {
            "date": day,
            "value": max(values["notifications"] - values["completions"], 0),
        }
        for day, values in daily.items()
    ]
    notifications_per_completion = [
        {
            "date": day,
            "value": values["notifications"] / values["completions"]
            if values["completions"]
            else values["notifications"],
        }
        for day, values in daily.items()
    ]
    return InsightsResponse(
        notifications_per_day=notifications_per_day,
        completions_per_day=completions_per_day,
        missed_rate_proxy=missed_rate_proxy,
        notifications_per_completion=notifications_per_completion,
    )


@app.post("/seed")
async def seed(db: Session = Depends(get_db)) -> dict[str, Any]:
    if os.getenv("APP_ENV") != "dev":
        raise HTTPException(status_code=403, detail="Seed disabled")
    sample_tasks = [
        Task(title="Review weekly goals", priority="high"),
        Task(title="Walk and stretch", priority="med"),
        Task(title="Plan tomorrow", priority="low"),
    ]
    for task in sample_tasks:
        db.add(task)
        db.flush()
        db.add(Event(type="task_created", task_id=task.id, reminder_id=None))
        schedule_reminder(db, task)
    db.commit()
    return {"ok": True, "tasks": len(sample_tasks)}
