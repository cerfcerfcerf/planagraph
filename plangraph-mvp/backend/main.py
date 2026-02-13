from __future__ import annotations

import json
import os
import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import SessionLocal, init_db
from llm_client import LLMClient
from models import Event, NudgeEvent, Reminder, Task, Template
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
    UpcomingTask,
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

USE_LLM = os.getenv("USE_LLM", "false").lower() == "true"

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


def _ensure_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        local_tz = datetime.now(timezone.utc).astimezone().tzinfo
        return value.replace(tzinfo=local_tz).astimezone(timezone.utc)
    return value.astimezone(timezone.utc)


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
                    start_dt = _ensure_utc(datetime.fromisoformat(payload["window_start"]))
                    end_dt = _ensure_utc(datetime.fromisoformat(payload["window_end"]))
                    if end_dt < start_dt:
                        end_dt = end_dt + timedelta(days=1)
                    payload["window_start"] = (
                        start_dt.isoformat().replace("+00:00", "Z") if start_dt else payload["window_start"]
                    )
                    payload["window_end"] = (
                        end_dt.isoformat().replace("+00:00", "Z") if end_dt else payload["window_end"]
                    )
                except ValueError:
                    pass
            items.append(payload)
        return items
    except (RuntimeError, json.JSONDecodeError, ValidationError):
        return None


def _parse_text(text: str) -> ParseResponse:
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
    seen_signatures: set[tuple[str, str | None, str | None, str | None]] = set()

    for payload in tasks:
        payload_data = payload.model_dump()
        title = (payload_data.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=422, detail="Task title cannot be empty")
        payload_data["title"] = title
        payload_data["due_at"] = _ensure_utc(payload_data.get("due_at"))
        payload_data["window_start"] = _ensure_utc(payload_data.get("window_start"))
        payload_data["window_end"] = _ensure_utc(payload_data.get("window_end"))
        if payload_data["window_start"] and payload_data["window_end"] and payload_data["window_start"] >= payload_data["window_end"]:
            raise HTTPException(status_code=422, detail="window_start must be before window_end")

        signature = (
            title.lower(),
            payload_data["due_at"].isoformat() if payload_data["due_at"] else None,
            payload_data["window_start"].isoformat() if payload_data["window_start"] else None,
            payload_data["window_end"].isoformat() if payload_data["window_end"] else None,
        )
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)

        existing = db.execute(
            select(Task).where(
                Task.status == "active",
                Task.title == title,
                Task.due_at == payload_data["due_at"],
                Task.window_start == payload_data["window_start"],
                Task.window_end == payload_data["window_end"],
            )
        ).scalars().first()
        if existing:
            continue

        if payload_data.get("priority") not in {"low", "med", "high"}:
            payload_data["priority"] = infer_priority(title, payload_data.get("notes"))
        payload_data["task_type"] = infer_task_type(title, payload_data.get("notes"))

        task = Task(**payload_data)
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
    updates = payload.model_dump(exclude_unset=True)
    previous_status = task.status
    for field, value in updates.items():
        if field in {"due_at", "window_start", "window_end"}:
            value = _ensure_utc(value)
        if field == "title" and isinstance(value, str):
            value = value.strip()
            if not value:
                raise HTTPException(status_code=422, detail="Task title cannot be empty")
        setattr(task, field, value)
    if task.window_start and task.window_end and task.window_start >= task.window_end:
        raise HTTPException(status_code=422, detail="window_start must be before window_end")
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
    now = datetime.now(timezone.utc)
    next_window = now + timedelta(hours=6)
    end_of_day = datetime.combine(now.date(), datetime.max.time(), tzinfo=timezone.utc)
    tasks = db.execute(select(Task).where(Task.status == "active")).scalars().all()
    settings = get_settings(db)
    actionable = [task for task in tasks if is_actionable_now(task, now, settings)]
    next_action: NowAction | None = None
    if actionable:
        best = max(actionable, key=lambda task: urgency_score(task, now))
        created_reminder = False
        reminder = (
            db.execute(
                select(Reminder)
                .where(Reminder.task_id == best.id, Reminder.state == "scheduled")
                .order_by(Reminder.scheduled_for.asc())
            )
            .scalars()
            .first()
        )
        if not reminder:
            reminder = Reminder(task_id=best.id, scheduled_for=now)
            db.add(reminder)
            db.flush()
            created_reminder = True
        next_action = NowAction(
            reminder_id=reminder.id if reminder else None,
            task_id=best.id,
            title=best.title,
            scheduled_for=best.due_at or best.window_start,
            window_start=best.window_start,
            window_end=best.window_end,
            priority=best.priority,
            why_now=build_explanation(best, now),
        )
        if created_reminder:
            db.commit()

    upcoming_tasks: list[Task] = []
    later_tasks: list[Task] = []
    for task in tasks:
        target = _ensure_utc(task.due_at) or _ensure_utc(task.window_start)
        if not target:
            continue
        if now <= target <= next_window:
            upcoming_tasks.append(task)
        elif next_window < target <= end_of_day:
            later_tasks.append(task)

    def _task_payload(task: Task) -> dict[str, Any]:
        return {
            "task_id": task.id,
            "title": task.title,
            "scheduled_for": task.due_at or task.window_start,
            "window_start": task.window_start,
            "window_end": task.window_end,
            "priority": task.priority,
            "why_now": build_explanation(task, now),
        }

    return NowResponse(
        next_best_action=next_action,
        next_6_hours=[UpcomingTask.model_validate(_task_payload(task)) for task in upcoming_tasks],
        later_today=[UpcomingTask.model_validate(_task_payload(task)) for task in later_tasks],
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
    now = datetime.now(timezone.utc)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    latency_seconds = int((now - reminder.scheduled_for).total_seconds()) if reminder.scheduled_for else None

    if payload.action == "done":
        reminder.state = "done"
        task.status = "completed"
        db.add(Event(type="task_done", task_id=task.id, reminder_id=reminder.id))
        if task.recurrence and task.recurrence != "none" and roll_task_forward(task):
            schedule_reminder(db, task)
    elif payload.action == "snooze":
        reminder.state = "snoozed"
        settings = get_settings(db)
        db.add(Reminder(task_id=reminder.task_id, scheduled_for=now + timedelta(minutes=settings.lead_time_minutes)))
        db.add(Event(type="reminder_snoozed", task_id=task.id, reminder_id=reminder.id))
    elif payload.action == "ignore":
        reminder.state = "dismissed"
        ignores = db.execute(select(NudgeEvent).where(NudgeEvent.task_id == task.id, NudgeEvent.action == "ignore")).scalars().all()
        if len(ignores) < 1:
            db.add(Reminder(task_id=reminder.task_id, scheduled_for=now + timedelta(minutes=15)))
        db.add(Event(type="reminder_ignored", task_id=task.id, reminder_id=reminder.id))
    elif payload.action == "lazy":
        reminder.state = "dismissed"
        db.add(Event(type="reminder_lazy", task_id=task.id, reminder_id=reminder.id, payload_json={"reason": payload.reason}))
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

    db.add(
        NudgeEvent(
            task_id=task.id,
            action=payload.action,
            reason=payload.reason,
            latency_seconds=latency_seconds,
            timestamp=now,
        )
    )
    db.commit()
    db.refresh(reminder)
    return ReminderOut.model_validate(reminder)


@app.get("/insights", response_model=InsightsResponse)
async def insights(db: Session = Depends(get_db)) -> InsightsResponse:
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    events = db.execute(select(NudgeEvent).where(NudgeEvent.timestamp >= cutoff)).scalars().all()

    baseline_events = [e for e in events if e.reason != "adaptive"]
    adaptive_events = [e for e in events if e.reason == "adaptive"]

    def _completion_rate(collection: list[NudgeEvent]) -> float:
        if not collection:
            return 0.0
        done = sum(1 for event in collection if event.action == "done")
        return round(done / len(collection), 3)

    done_hours: dict[int, list[str]] = {}
    wasted_by_hour: dict[int, int] = {}
    for event in events:
        hour = event.timestamp.hour
        if event.action == "done":
            done_hours.setdefault(hour, []).append(event.action)
        if event.action == "ignore" and hour >= 20:
            wasted_by_hour[hour] = wasted_by_hour.get(hour, 0) + 1

    best_hours = sorted(
        [{"hour": hour, "completion_rate": len(actions)} for hour, actions in done_hours.items()],
        key=lambda item: item["completion_rate"],
        reverse=True,
    )[:3]
    wasted_nudges = [{"hour": hour, "count": count} for hour, count in sorted(wasted_by_hour.items())]

    recommendations: list[str] = []
    if wasted_nudges:
        recommendations.append("Reduce evening reminders after 20:00; ignores spike late.")
    if best_hours:
        recommendations.append(f"Schedule important nudges around {best_hours[0]['hour']:02d}:00 when completion is strongest.")
    if _completion_rate(adaptive_events) < _completion_rate(baseline_events):
        recommendations.append("Adaptive mode is underperforming baseline; increase exploration and fallback to baseline lead times.")
    else:
        recommendations.append("Adaptive mode is meeting or beating baseline; keep adaptive enabled.")

    return InsightsResponse(
        completion_rate_baseline=_completion_rate(baseline_events),
        completion_rate_adaptive=_completion_rate(adaptive_events),
        best_hours=best_hours,
        wasted_nudges=wasted_nudges,
        recommendations=recommendations[:3],
    )


@app.get("/insights/summary", response_model=InsightsSummaryResponse)
async def insights_summary(db: Session = Depends(get_db)) -> InsightsSummaryResponse:
    insights_payload = await insights(db)
    completion_rate = insights_payload.completion_rate_adaptive
    baseline_rate = insights_payload.completion_rate_baseline
    metrics = {
        "completion_rate": round(completion_rate, 2),
        "notifications_per_day": 0.0,
        "notifications_per_completion": 0.0,
        "missed_rate_proxy": 0.0,
        "stale_reminder_rate": 0.0,
        "median_completion_delay": 0.0,
    }
    narrative = (
        f"Adaptive completion is {completion_rate*100:.0f}% vs baseline {baseline_rate*100:.0f}%. "
        "Focus reminders on your best hours and reduce low-value late nudges."
    )
    return InsightsSummaryResponse(
        narrative=narrative,
        recommendations=insights_payload.recommendations,
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
    base_day = datetime.now(timezone.utc).date() - timedelta(days=6)
    sample_tasks = []
    for idx in range(7):
        day = base_day + timedelta(days=idx)
        sample_tasks.append(
            Task(
                title=f"Daily review {day.isoformat()}",
                priority="med",
                due_at=datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
                + timedelta(hours=18),
            )
        )
    for task in sample_tasks:
        db.add(task)
        db.flush()
        db.add(Event(type="task_created", task_id=task.id, reminder_id=None))
        db.add(Event(type="reminder_sent", task_id=task.id, reminder_id=None, ts=task.due_at))
        if task.due_at and task.due_at.date() <= datetime.now(timezone.utc).date():
            db.add(Event(type="task_done", task_id=task.id, reminder_id=None, ts=task.due_at))
        schedule_reminder(db, task)
    db.commit()
    return {"ok": True, "tasks": len(sample_tasks)}
