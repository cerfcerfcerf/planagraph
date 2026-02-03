from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from db import engine, get_session, utcnow
from llm_client import LLM_MODEL, USE_LLM, client
from models import Base, Event, Reminder, Settings, Task
from parser import fallback_parse
from policy import ensure_default_settings, schedule_for_tasks
from scheduler import scheduler
from schemas import (
    InsightsResponse,
    InsightsSeriesPoint,
    NowItem,
    NowResponse,
    ParseRequest,
    ParseResponse,
    ReminderAction,
    SettingsIn,
    SettingsOut,
    TaskCreate,
    TaskOut,
    TaskUpdate,
    TasksResponse,
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


@app.on_event("startup")
async def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with get_session() as session:
        ensure_default_settings(session)
    await scheduler.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await scheduler.stop()


def _llm_parse(text: str) -> ParseResponse:
    payload = {
        "model": LLM_MODEL,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Extract tasks from the plan. Return ONLY valid JSON matching this schema: "
                    "{items:[{title,date,due_time,window_start,window_end,priority,recurrence,"
                    "recurrence_detail,confidence,notes}]}. "
                    "date is YYYY-MM-DD or null; due_time is HH:MM or null; "
                    "window_start/window_end are ISO datetime or null. "
                    "priority is low|med|high. recurrence is none|daily|weekly|every_2_days|custom."
                ),
            },
            {"role": "user", "content": text},
        ],
    }
    data = client.chat(payload)
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise ValueError("Empty response")
    parsed = ParseResponse.model_validate_json(content)
    return parsed


def _fallback_parse(text: str) -> ParseResponse:
    items = fallback_parse(text)
    return ParseResponse(items=items)


@app.post("/parse", response_model=ParseResponse)
async def parse_text(request: ParseRequest) -> ParseResponse:
    if USE_LLM:
        try:
            return _llm_parse(request.text)
        except (ValidationError, ValueError, json.JSONDecodeError):
            return _fallback_parse(request.text)
    return _fallback_parse(request.text)


@app.get("/tasks", response_model=TasksResponse)
async def list_tasks() -> TasksResponse:
    with get_session() as session:
        tasks = session.query(Task).order_by(Task.created_at.desc()).all()
        items = [
            TaskOut(
                id=task.id,
                title=task.title,
                notes=task.notes,
                due_at=task.due_at,
                window_start=task.window_start,
                window_end=task.window_end,
                priority=task.priority,
                status=task.status,
                recurrence=task.recurrence,
                created_at=task.created_at,
                updated_at=task.updated_at,
            )
            for task in tasks
        ]
        return TasksResponse(items=items)


@app.post("/tasks", response_model=TaskOut)
async def create_task(payload: TaskCreate) -> TaskOut:
    with get_session() as session:
        task = Task(
            title=payload.title,
            notes=payload.notes,
            due_at=payload.due_at,
            window_start=payload.window_start,
            window_end=payload.window_end,
            priority=payload.priority,
            status=payload.status,
            recurrence=payload.recurrence,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        session.add(task)
        session.flush()
        session.add(Event(type="task_created", task_id=task.id, reminder_id=None, ts=utcnow()))
        schedule_for_tasks(session, [task])
        session.refresh(task)
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
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


@app.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(task_id: int, payload: TaskUpdate) -> TaskOut:
    with get_session() as session:
        task = session.query(Task).get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(task, field, value)
        task.updated_at = utcnow()
        if payload.status == "completed":
            session.add(Event(type="task_done", task_id=task.id, reminder_id=None, ts=utcnow()))
        schedule_for_tasks(session, [task])
        session.flush()
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
            created_at=task.created_at,
            updated_at=task.updated_at,
        )


@app.get("/settings", response_model=SettingsOut)
async def get_settings() -> SettingsOut:
    with get_session() as session:
        settings = ensure_default_settings(session)
        return SettingsOut(
            policy_mode=settings.policy_mode,
            daily_budget=settings.daily_budget,
            quiet_hours_start=settings.quiet_hours_start,
            quiet_hours_end=settings.quiet_hours_end,
            lead_time_min=settings.lead_time_min,
        )


@app.post("/settings", response_model=SettingsOut)
async def update_settings(payload: SettingsIn) -> SettingsOut:
    with get_session() as session:
        settings = ensure_default_settings(session)
        settings.policy_mode = payload.policy_mode
        settings.daily_budget = payload.daily_budget
        settings.quiet_hours_start = payload.quiet_hours_start
        settings.quiet_hours_end = payload.quiet_hours_end
        settings.lead_time_min = payload.lead_time_min
        session.add(settings)
        return SettingsOut(
            policy_mode=settings.policy_mode,
            daily_budget=settings.daily_budget,
            quiet_hours_start=settings.quiet_hours_start,
            quiet_hours_end=settings.quiet_hours_end,
            lead_time_min=settings.lead_time_min,
        )


def _why_now_summary(task: Task) -> str:
    if task.due_at:
        return f"Due at {task.due_at.strftime('%H:%M')}"
    if task.window_start and task.window_end:
        return "Within your flexible window"
    return "Scheduled as a priority"


def _llm_why_now(task: Task) -> str:
    payload = {
        "model": LLM_MODEL,
        "temperature": 0.4,
        "messages": [
            {
                "role": "system",
                "content": "Provide a short 1 sentence explanation for why a task should be done now.",
            },
            {"role": "user", "content": f"Task: {task.title}"},
        ],
    }
    data = client.chat(payload)
    return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


@app.get("/now", response_model=NowResponse)
async def now() -> NowResponse:
    with get_session() as session:
        upcoming = (
            session.query(Task)
            .filter(Task.status == "active")
            .order_by(Task.due_at.is_(None), Task.due_at)
            .all()
        )
        now_time = utcnow()
        six_hours = now_time + timedelta(hours=6)
        end_today = now_time.replace(hour=23, minute=59, second=59)

        next_task: Task | None = None
        for task in upcoming:
            if task.due_at and task.due_at <= six_hours:
                next_task = task
                break
            if task.window_start and task.window_start <= six_hours:
                next_task = task
                break
        if next_task is None and upcoming:
            next_task = upcoming[0]

        def to_now_item(task: Task) -> NowItem:
            return NowItem(
                task_id=task.id,
                title=task.title,
                due_at=task.due_at,
                window_start=task.window_start,
                window_end=task.window_end,
                priority=task.priority,
            )

        next_items = []
        later_items = []
        for task in upcoming:
            target_time = task.due_at or task.window_start
            if target_time and target_time <= six_hours:
                next_items.append(to_now_item(task))
            elif target_time and target_time <= end_today:
                later_items.append(to_now_item(task))

        why_now = ""
        if next_task:
            if USE_LLM:
                try:
                    why_now = _llm_why_now(next_task)
                except Exception:
                    why_now = _why_now_summary(next_task)
            else:
                why_now = _why_now_summary(next_task)

        reminder_id = None
        if next_task:
            reminder = (
                session.query(Reminder)
                .filter(Reminder.task_id == next_task.id)
                .order_by(Reminder.scheduled_for.desc())
                .first()
            )
            if reminder:
                reminder_id = reminder.id

        return NowResponse(
            next_best_action=to_now_item(next_task) if next_task else None,
            next_reminder_id=reminder_id,
            why_now=why_now or "Keep momentum on your priorities.",
            next_6_hours=next_items,
            later_today=later_items,
        )


@app.post("/reminders/{reminder_id}/action")
async def reminder_action(reminder_id: int, payload: ReminderAction) -> dict[str, Any]:
    with get_session() as session:
        reminder = session.query(Reminder).get(reminder_id)
        if not reminder:
            raise HTTPException(status_code=404, detail="Reminder not found")
        now_time = utcnow()
        if payload.action == "done":
            reminder.state = "done"
            task = session.query(Task).get(reminder.task_id)
            if task:
                task.status = "completed"
                task.updated_at = now_time
                session.add(Event(type="task_done", task_id=task.id, reminder_id=reminder.id, ts=now_time))
        elif payload.action == "dismiss":
            reminder.state = "dismissed"
            session.add(Event(type="reminder_dismissed", task_id=reminder.task_id, reminder_id=reminder.id, ts=now_time))
        elif payload.action == "snooze_10":
            reminder.state = "snoozed"
            reminder.scheduled_for = now_time + timedelta(minutes=10)
            session.add(Event(type="reminder_snoozed", task_id=reminder.task_id, reminder_id=reminder.id, ts=now_time))
        elif payload.action == "snooze_30":
            reminder.state = "snoozed"
            reminder.scheduled_for = now_time + timedelta(minutes=30)
            session.add(Event(type="reminder_snoozed", task_id=reminder.task_id, reminder_id=reminder.id, ts=now_time))
        session.add(reminder)
        return {"ok": True}


@app.get("/insights", response_model=InsightsResponse)
async def insights() -> InsightsResponse:
    with get_session() as session:
        events = session.query(Event).all()
        notifications = [e for e in events if e.type == "reminder_sent"]
        completions = [e for e in events if e.type == "task_done"]

        def series(events_list: list[Event]) -> list[InsightsSeriesPoint]:
            counts: dict[str, int] = {}
            for event in events_list:
                key = event.ts.date().isoformat()
                counts[key] = counts.get(key, 0) + 1
            return [InsightsSeriesPoint(date=k, count=v) for k, v in sorted(counts.items())]

        notifications_series = series(notifications)
        completions_series = series(completions)
        missed_proxy = 0.0
        if notifications:
            missed_proxy = max(0.0, 1.0 - (len(completions) / len(notifications)))
        notif_per_completion = len(notifications) / len(completions) if completions else 0.0

        return InsightsResponse(
            notifications_per_day=notifications_series,
            completions_per_day=completions_series,
            missed_rate_proxy=missed_proxy,
            notifications_per_completion=notif_per_completion,
            totals={"notifications": len(notifications), "completions": len(completions)},
        )


@app.post("/seed")
async def seed() -> dict[str, Any]:
    if os.getenv("DEV_SEED", "false").lower() != "true":
        raise HTTPException(status_code=403, detail="Seed disabled")
    with get_session() as session:
        now_time = utcnow()
        tasks = [
            Task(
                title="Draft weekly review",
                notes="Focus on top 3 outcomes.",
                due_at=now_time + timedelta(hours=3),
                priority="high",
                status="active",
                created_at=now_time,
                updated_at=now_time,
            ),
            Task(
                title="Grocery run",
                window_start=now_time + timedelta(hours=4),
                window_end=now_time + timedelta(hours=6),
                priority="med",
                status="active",
                created_at=now_time,
                updated_at=now_time,
            ),
        ]
        session.add_all(tasks)
        session.flush()
        schedule_for_tasks(session, tasks)
        return {"ok": True, "tasks": [task.id for task in tasks]}
