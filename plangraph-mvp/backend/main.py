from __future__ import annotations

import json
import os
import statistics
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
from models import Event, Reminder, Task, Template
from parser import deterministic_parse, infer_priority, infer_task_type, recurrence_suggestions
from policy import (
    build_explanation,
    get_settings,
    is_actionable_now,
    roll_task_forward,
    schedule_reminder,
    urgency_score,
)
from scheduler import ReminderScheduler
from schemas import (
    InsightsResponse,
    InsightsSummaryResponse,
    NowAction,
    NowResponse,
    ParseRequest,
    ParseResponse,
    LazySuggestionRequest,
    LazySuggestionResponse,
    ReminderActionRequest,
    ReminderOut,
    SettingsOut,
    SettingsUpdate,
    TaskCreate,
    TaskListResponse,
    TaskOut,
    TaskUpdate,
    TemplateCreate,
    TemplateOut,
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
    schema_hint = {
        "name": "parse_response",
        "schema": ParseResponse.model_json_schema(),
        "strict": True,
    }
    try:
        response = client.parse_plan(text, schema_hint)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = json.loads(content)
        validated = ParseResponse.model_validate(parsed)
        items = []
        for item in validated.items:
            payload = item.model_dump()
            if payload.get("priority") not in {"low", "med", "high"}:
                payload["priority"] = infer_priority(
                    payload.get("title", ""), payload.get("notes")
                )
            if not payload.get("task_type"):
                payload["task_type"] = infer_task_type(
                    payload.get("title", ""), payload.get("notes")
                )
            if not payload.get("recurrence_suggestions"):
                detected_date = None
                if payload.get("date"):
                    try:
                        detected_date = datetime.fromisoformat(payload["date"]).date()
                    except ValueError:
                        detected_date = None
                payload["recurrence_suggestions"] = recurrence_suggestions(
                    payload.get("title", ""),
                    detected_date,
                )
            if payload.get("task_type") in {"meal", "sleep", "medication", "hygiene"} and payload.get(
                "recurrence"
            ) in {None, "none"}:
                payload["recurrence"] = "daily"
                payload["recurrence_detail"] = "auto-routine"
            if payload.get("window_start") and payload.get("window_end"):
                try:
                    start_dt = datetime.fromisoformat(payload["window_start"])
                    end_dt = datetime.fromisoformat(payload["window_end"])
                    if end_dt < start_dt:
                        payload["window_end"] = (end_dt + timedelta(days=1)).isoformat()
                except ValueError:
                    pass
            items.append(payload)
        return items
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


@app.get("/config")
async def config() -> dict[str, Any]:
    return {"use_llm": USE_LLM}


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
        payload_data = payload.model_dump()
        if payload_data.get("priority") not in {"low", "med", "high"}:
            payload_data["priority"] = infer_priority(
                payload_data.get("title", ""), payload_data.get("notes")
            )
        payload_data["task_type"] = infer_task_type(
            payload_data.get("title", ""), payload_data.get("notes")
        )
        if payload_data.get("task_type") in {"meal", "sleep", "medication", "hygiene"} and not payload_data.get(
            "recurrence"
        ):
            payload_data["recurrence"] = "daily"
            payload_data["recurrence_detail"] = "auto-routine"
        task = Task(**payload_data)
        db.add(task)
        db.flush()
        db.add(Event(type="task_created", task_id=task.id, reminder_id=None))
        created.append(task)
    db.commit()
    now = datetime.utcnow()
    for task in created:
        target = task.due_at or task.window_start
        if target and target <= now + timedelta(hours=6):
            continue
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
    updates = payload.model_dump(exclude_unset=True)
    previous_status = task.status
    for field, value in updates.items():
        setattr(task, field, value)
    db.add(task)
    if previous_status != "archived" and updates.get("status") == "archived":
        db.add(Event(type="task_skipped", task_id=task.id, reminder_id=None))
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


@app.get("/now", response_model=NowResponse)
async def now_view(db: Session = Depends(get_db)) -> NowResponse:
    now = datetime.utcnow()
    next_window = now + timedelta(hours=6)
    end_of_day = datetime.combine(now.date(), datetime.max.time())
    tasks = (
        db.execute(select(Task).where(Task.status == "active")).scalars().all()
    )
    settings = get_settings(db)
    actionable = [task for task in tasks if is_actionable_now(task, now, settings)]
    next_action: NowAction | None = None
    if actionable:
        best = max(actionable, key=lambda task: urgency_score(task, now))
        next_action = NowAction(
            reminder_id=None,
            task_id=best.id,
            title=best.title,
            scheduled_for=best.due_at or best.window_start,
            window_start=best.window_start,
            window_end=best.window_end,
            priority=best.priority,
            why_now=build_explanation(best, now),
        )

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

    def _reminder_payload(reminder: Reminder) -> dict[str, Any]:
        task = db.get(Task, reminder.task_id)
        return {
            **reminder.__dict__,
            "title": task.title if task else None,
            "why_now": build_explanation(task, now) if task else None,
        }

    return NowResponse(
        next_best_action=next_action,
        next_6_hours=[ReminderOut.model_validate(_reminder_payload(r)) for r in next_6],
        later_today=[ReminderOut.model_validate(_reminder_payload(r)) for r in later],
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
                if roll_task_forward(task):
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
    now = datetime.utcnow().date()
    start_day = now - timedelta(days=6)
    days = [(start_day + timedelta(days=idx)).isoformat() for idx in range(7)]
    events = (
        db.execute(select(Event).where(Event.ts >= datetime.combine(start_day, datetime.min.time())))
        .scalars()
        .all()
    )
    daily: dict[str, dict[str, int]] = {
        day: {"notifications": 0, "completions": 0, "sent": 0, "expired": 0} for day in days
    }
    sent_lookup: dict[int, datetime] = {}
    completion_delays: dict[str, list[float]] = {day: [] for day in days}
    for event in events:
        day = event.ts.date().isoformat()
        if day not in daily:
            continue
        if event.type == "reminder_sent":
            daily[day]["notifications"] += 1
            daily[day]["sent"] += 1
            if event.reminder_id is not None:
                sent_lookup[event.reminder_id] = event.ts
        if event.type == "reminder_expired":
            daily[day]["expired"] += 1
        if event.type == "task_done":
            daily[day]["completions"] += 1
            if event.reminder_id is not None and event.reminder_id in sent_lookup:
                delay_minutes = (event.ts - sent_lookup[event.reminder_id]).total_seconds() / 60
                completion_delays[day].append(delay_minutes)
    notifications_per_day = [
        {"date": day, "value": daily[day]["notifications"]} for day in days
    ]
    completions_per_day = [
        {"date": day, "value": daily[day]["completions"]} for day in days
    ]
    missed_rate_proxy = [
        {"date": day, "value": max(daily[day]["notifications"] - daily[day]["completions"], 0)}
        for day in days
    ]
    notifications_per_completion = [
        {
            "date": day,
            "value": daily[day]["notifications"] / daily[day]["completions"]
            if daily[day]["completions"]
            else daily[day]["notifications"],
        }
        for day in days
    ]
    stale_reminder_rate = [
        {
            "date": day,
            "value": daily[day]["expired"] / daily[day]["sent"] if daily[day]["sent"] else 0,
        }
        for day in days
    ]
    median_completion_delay = [
        {
            "date": day,
            "value": round(statistics.median(completion_delays[day]), 2)
            if completion_delays[day]
            else 0,
        }
        for day in days
    ]
    return InsightsResponse(
        notifications_per_day=notifications_per_day,
        completions_per_day=completions_per_day,
        missed_rate_proxy=missed_rate_proxy,
        notifications_per_completion=notifications_per_completion,
        stale_reminder_rate=stale_reminder_rate,
        median_completion_delay=median_completion_delay,
    )


@app.get("/templates", response_model=list[TemplateOut])
async def list_templates(db: Session = Depends(get_db)) -> list[TemplateOut]:
    templates = (
        db.execute(select(Template).order_by(Template.pinned.desc(), Template.used_count.desc()))
        .scalars()
        .all()
    )
    return [TemplateOut.model_validate(template) for template in templates]


@app.post("/templates", response_model=TemplateOut)
async def create_template(payload: TemplateCreate, db: Session = Depends(get_db)) -> TemplateOut:
    template = Template(**payload.model_dump())
    db.add(template)
    db.commit()
    db.refresh(template)
    return TemplateOut.model_validate(template)


@app.post("/templates/{template_id}/use", response_model=TaskOut)
async def use_template(template_id: int, db: Session = Depends(get_db)) -> TaskOut:
    template = db.get(Template, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    now = datetime.utcnow()
    window_start = now.replace(minute=0, second=0, microsecond=0)
    window_end = window_start + timedelta(minutes=template.default_duration_min)
    task = Task(
        title=template.title,
        notes=None,
        window_start=window_start,
        window_end=window_end,
        priority=template.default_priority,
        task_type=template.default_type,
        recurrence=None,
        recurrence_detail=None,
    )
    db.add(task)
    template.used_count += 1
    template.last_used = now
    db.commit()
    db.refresh(task)
    return TaskOut.model_validate(task)


@app.get("/insights/summary", response_model=InsightsSummaryResponse)
async def insights_summary(db: Session = Depends(get_db)) -> InsightsSummaryResponse:
    insights_payload = await insights(db)
    total_notifications = sum(item["value"] for item in insights_payload.notifications_per_day)
    total_completions = sum(item["value"] for item in insights_payload.completions_per_day)
    completion_rate = (
        total_completions / total_notifications if total_notifications else 0.0
    )
    notifications_per_day = total_notifications / 7
    notifications_per_completion = (
        total_notifications / total_completions if total_completions else total_notifications
    )
    missed_rate = sum(item["value"] for item in insights_payload.missed_rate_proxy) / 7
    stale_rate = sum(item["value"] for item in insights_payload.stale_reminder_rate) / 7
    median_delay = sum(item["value"] for item in insights_payload.median_completion_delay) / 7
    metrics = {
        "completion_rate": round(completion_rate, 2),
        "notifications_per_day": round(notifications_per_day, 2),
        "notifications_per_completion": round(notifications_per_completion, 2),
        "missed_rate_proxy": round(missed_rate, 2),
        "stale_reminder_rate": round(stale_rate, 2),
        "median_completion_delay": round(median_delay, 2),
    }
    if USE_LLM:
        try:
            response = LLMClient().summarize_insights(metrics)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = json.loads(content)
            narrative = parsed.get("narrative", "")
            recommendations = parsed.get("recommendations", [])
            if narrative and isinstance(recommendations, list) and recommendations:
                return InsightsSummaryResponse(
                    narrative=narrative,
                    recommendations=recommendations[:3],
                    metrics=metrics,
                )
        except (RuntimeError, json.JSONDecodeError):
            pass
    narrative = (
        "This week shows a steady rhythm of reminders and completions. "
        f"Completion rate averaged {metrics['completion_rate'] * 100:.0f}% with "
        f"{metrics['notifications_per_day']} notifications per day. "
        f"Stale reminders averaged {metrics['stale_reminder_rate'] * 100:.0f}% and "
        f"median completion delay was {metrics['median_completion_delay']} minutes. "
        "Use the missed-rate proxy to see where nudges might be too early. "
        "Keep experiments small and adjust settings weekly."
    )
    recommendations = [
        "Schedule high-priority work in your strongest hours.",
        "Reduce notification budget if completions lag.",
        "Use flexible windows for tasks without fixed times.",
    ]
    return InsightsSummaryResponse(
        narrative=narrative,
        recommendations=recommendations,
        metrics=metrics,
    )


@app.post("/lazy_suggestions", response_model=LazySuggestionResponse)
async def lazy_suggestions(payload: LazySuggestionRequest) -> LazySuggestionResponse:
    fallback = [
        "Reschedule for tomorrow morning",
        "Shrink to a 25-minute focus block",
        "Skip and revisit next week",
    ]
    if not USE_LLM:
        return LazySuggestionResponse(suggestions=fallback)
    try:
        response = LLMClient().lazy_suggestions(payload.title, payload.notes)
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = json.loads(content)
        suggestions = parsed.get("suggestions", [])
        if isinstance(suggestions, list) and suggestions:
            return LazySuggestionResponse(suggestions=suggestions[:3])
    except (RuntimeError, json.JSONDecodeError):
        pass
    return LazySuggestionResponse(suggestions=fallback)


@app.post("/seed")
async def seed(db: Session = Depends(get_db)) -> dict[str, Any]:
    if os.getenv("APP_ENV") != "dev":
        raise HTTPException(status_code=403, detail="Seed disabled")
    base_day = datetime.utcnow().date() - timedelta(days=6)
    sample_tasks = []
    for idx in range(7):
        day = base_day + timedelta(days=idx)
        sample_tasks.append(
            Task(
                title=f"Daily review {day.isoformat()}",
                priority="med",
                due_at=datetime.combine(day, datetime.min.time()) + timedelta(hours=18),
            )
        )
    for task in sample_tasks:
        db.add(task)
        db.flush()
        db.add(Event(type="task_created", task_id=task.id, reminder_id=None))
        db.add(Event(type="reminder_sent", task_id=task.id, reminder_id=None, ts=task.due_at))
        if task.due_at and task.due_at.date() <= datetime.utcnow().date():
            db.add(Event(type="task_done", task_id=task.id, reminder_id=None, ts=task.due_at))
        schedule_reminder(db, task)
    db.commit()
    return {"ok": True, "tasks": len(sample_tasks)}
