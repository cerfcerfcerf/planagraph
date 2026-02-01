from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import Any, List

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

import db
import reminders
from models import (
    EntryResponse,
    HabitRuleIn,
    HabitRulesResponse,
    HistoryResponse,
    ParseRequest,
    ParseResponse,
    PlanRequest,
    PlanResponse,
    ReminderAckRequest,
    RemindersDueResponse,
    ScheduleItem,
    TaskCreate,
    TaskListResponse,
    TaskUpdate,
)
from planner import plan_items

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

app = FastAPI(title="Plangraph MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def extract_first_json(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start == -1:
        raise ValueError("No JSON object found")
    depth = 0
    for idx in range(start, len(text)):
        char = text[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                chunk = text[start : idx + 1]
                return json.loads(chunk)
    raise ValueError("Incomplete JSON object")


def build_system_prompt(today_value: str) -> str:
    return (
        "You are a strict JSON generator. Return ONLY valid JSON. "
        "Extract schedule items from the text. Use this schema: "
        "{items:[{title,type,date,start_time,end_time,duration_min,priority,location,notes}]}. "
        "type must be one of event, task, reminder. "
        "Use date in YYYY-MM-DD if a date is implied; today is "
        f"{today_value}. For times, use 24h HH:MM. "
        "duration_min must be an integer; if unknown use 0. "
        "priority is integer (higher is more important); default 0. "
        "If a field is unknown, use null."
    )


def parse_with_ollama(text: str, today_value: str) -> List[ScheduleItem]:
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": build_system_prompt(today_value)},
            {"role": "user", "content": text},
        ],
    }
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail="Invalid JSON from Ollama") from exc

    content = data.get("message", {}).get("content", "")
    try:
        json_obj = extract_first_json(content)
        parsed = ParseResponse.model_validate(json_obj)
        normalized_items = [
            ScheduleItem(
                **{
                    **item.model_dump(),
                    "duration_min": int(item.duration_min or 0),
                    "priority": int(item.priority or 0),
                }
            )
            for item in parsed.items
        ]
        return normalized_items
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"Unable to parse model output: {exc}") from exc


@app.on_event("startup")
async def startup() -> None:
    db.init_db()


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "model": OLLAMA_MODEL}


@app.post("/parse", response_model=ParseResponse)
async def parse_text(request: ParseRequest) -> ParseResponse:
    today_value = request.today or date.today().isoformat()
    items = parse_with_ollama(request.text, today_value)
    return ParseResponse(items=items)


@app.post("/entry", response_model=EntryResponse)
async def create_entry(request: ParseRequest) -> EntryResponse:
    today_value = request.today or date.today().isoformat()
    items = parse_with_ollama(request.text, today_value)
    entry_id = db.insert_entry(request.text, today_value)
    item_payloads = [item.model_dump() for item in items]
    item_ids = db.insert_items(entry_id, item_payloads)
    stored_items = []
    for item, item_id in zip(items, item_ids):
        stored_items.append(ScheduleItem(**{**item.model_dump(), "id": item_id}))
    return EntryResponse(entry_id=entry_id, items=stored_items)


@app.post("/plan", response_model=PlanResponse)
async def plan_day(request: PlanRequest) -> PlanResponse:
    normalized_items = []
    for item in request.items:
        normalized_items.append(
            ScheduleItem(
                **{
                    **item.model_dump(),
                    "date": item.date or request.day,
                    "duration_min": int(item.duration_min or 0),
                    "priority": int(item.priority or 0),
                }
            )
        )
    planned_items, conflicts = plan_items(
        normalized_items,
        day_start=request.day_start,
        day_end=request.day_end,
    )
    plan_id = db.insert_plan(request.day, request.day_start, request.day_end)
    db.insert_planned_items(plan_id, [item.model_dump() for item in planned_items])

    reminders.generate_event_reminders(plan_id, planned_items)
    reminders.attach_contextual_reminders(
        plan_id,
        request.day,
        request.day_start,
        planned_items,
        normalized_items,
    )
    reminders.generate_habit_reminders(request.day)
    return PlanResponse(day=request.day, planned=planned_items, conflicts=conflicts)


@app.get("/reminders/due", response_model=RemindersDueResponse)
async def reminders_due(now: str | None = None) -> RemindersDueResponse:
    now_value = now or datetime.utcnow().replace(microsecond=0).isoformat()
    rows = db.list_due_reminders(now_value)
    reminders_out = []
    for row in rows:
        reminders_out.append(
            {
                "id": row["id"],
                "due_at": row["due_at"],
                "kind": row["kind"],
                "title": row["title"],
                "body": row["body"],
                "status": row["status"],
                "reason": row["reason"],
                "related_item_title": row["related_item_title"],
            }
        )
    return RemindersDueResponse(now=now_value, reminders=reminders_out)


@app.post("/reminders/{reminder_id}/ack")
async def ack_reminder(reminder_id: int, request: ReminderAckRequest) -> dict[str, Any]:
    reminder = db.fetch_reminder(reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    now_value = datetime.utcnow().replace(microsecond=0).isoformat()
    if request.action == "dismiss":
        db.update_reminder_status(reminder_id, "dismissed", now_value, None)
    elif request.action == "snooze":
        snooze_min = request.snooze_min or 10
        snoozed_until = (datetime.utcnow() + timedelta(minutes=snooze_min)).replace(microsecond=0).isoformat()
        db.update_reminder_status(reminder_id, "pending", reminder["delivered_at"], snoozed_until)
    elif request.action == "done":
        db.update_reminder_status(reminder_id, "done", now_value, None)
        db.insert_completion(reminder["item_id"], reminder["rule_id"], {"source": "reminder"})
        if reminder["item_id"]:
            db.update_item_status(reminder["item_id"], "done")
    return {"ok": True}


@app.get("/history", response_model=HistoryResponse)
async def history(limit: int = 50) -> HistoryResponse:
    entries = db.history_entries(limit)
    plans = db.history_plans(limit)
    entry_items = [
        {
            "id": row["id"],
            "text": row["text"],
            "today": row["today"],
            "created_at": row["created_at"],
            "item_count": row["item_count"],
        }
        for row in entries
    ]
    plan_items = [
        {
            "id": row["id"],
            "day": row["day"],
            "day_start": row["day_start"],
            "day_end": row["day_end"],
            "created_at": row["created_at"],
            "planned_count": row["planned_count"] or 0,
            "unscheduled_count": row["unscheduled_count"] or 0,
        }
        for row in plans
    ]
    return HistoryResponse(entries=entry_items, plans=plan_items)


@app.get("/tasks", response_model=TaskListResponse)
async def list_tasks(
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    status: str | None = None,
    item_type: str | None = Query(default=None, alias="type"),
    q: str | None = None,
) -> TaskListResponse:
    rows = db.list_tasks(date_from, date_to, status, item_type, q)
    items = [ScheduleItem(**dict(row)) for row in rows]
    return TaskListResponse(items=items)


@app.post("/tasks", response_model=ScheduleItem)
async def create_task(task: TaskCreate) -> ScheduleItem:
    task_id = db.insert_task(task.model_dump())
    row = db.fetch_task(task_id)
    if not row:
        raise HTTPException(status_code=500, detail="Task not found after insert")
    return ScheduleItem(**dict(row))


@app.patch("/tasks/{task_id}", response_model=ScheduleItem)
async def update_task(task_id: int, task: TaskUpdate) -> ScheduleItem:
    fields = {key: value for key, value in task.model_dump().items() if value is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields provided")
    db.update_task(task_id, fields)
    row = db.fetch_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return ScheduleItem(**dict(row))


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int) -> dict[str, Any]:
    db.delete_task(task_id)
    return {"ok": True}


@app.post("/tasks/{task_id}/complete")
async def complete_task(task_id: int) -> dict[str, Any]:
    db.complete_task(task_id)
    return {"ok": True}


@app.post("/habits/rules")
async def upsert_habit_rule(rule: HabitRuleIn) -> dict[str, Any]:
    rule_id = db.upsert_reminder_rule(rule.model_dump())
    return {"id": rule_id}


@app.get("/habits/rules", response_model=HabitRulesResponse)
async def list_habit_rules() -> HabitRulesResponse:
    rules = db.list_reminder_rules()
    rules_out = []
    for rule in rules:
        typical_minutes = reminders.compute_typical_time(rule["id"])
        typical_time = None
        if typical_minutes is not None:
            typical_time = reminders.format_time(typical_minutes)
        rules_out.append(
            {
                "id": rule["id"],
                "key": rule["key"],
                "title": rule["title"],
                "lead_min": rule["lead_min"],
                "enabled": bool(rule["enabled"]),
                "default_time": rule["default_time"],
                "target_per_week": rule["target_per_week"],
                "typical_time": typical_time,
            }
        )
    return HabitRulesResponse(rules=rules_out)


@app.post("/habits/generate")
async def generate_habits(day: str) -> dict[str, Any]:
    reminder_ids = reminders.generate_habit_reminders(day)
    return {"created": len(reminder_ids)}


@app.get("/")
async def root() -> dict[str, Any]:
    return {"message": "Plangraph MVP backend"}
