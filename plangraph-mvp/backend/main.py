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
    NowResponse,
    PlannedItemOut,
    ScheduleItem,
    TaskActionRequest,
    TaskCreate,
    TaskListResponse,
    TaskQuickAdd,
    TaskUpdate,
)
from planner import derive_placement_hint, plan_items

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")

app = FastAPI(title="Plangraph")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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
    for payload in item_payloads:
        placement_hint = payload.get("placement_hint") or derive_placement_hint(ScheduleItem(**payload))
        payload["placement_hint"] = placement_hint
        payload["task_state"] = payload.get("task_state") or "pending"
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
                    "placement_hint": item.placement_hint or derive_placement_hint(item),
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
                "context": row["body"] or row["related_item_title"],
            }
        )
    return RemindersDueResponse(now=now_value, reminders=reminders_out)


@app.get("/now", response_model=NowResponse)
async def now_view(now: str | None = None) -> NowResponse:
    now_dt = datetime.utcnow().replace(microsecond=0)
    if now:
        now_dt = datetime.fromisoformat(now)
    now_value = now_dt.isoformat()
    today = now_dt.date().isoformat()
    plan = db.latest_plan_for_day(today)
    if not plan:
        return NowResponse(
            now=now_value,
            message="No plan yet. Add an activity to start.",
            due_reminders=[],
            next_items=[],
            later_today=[],
        )
    due_rows = db.list_due_reminders(now_value)
    planned_rows = db.list_planned_items(plan["id"], today, today, "pending", None, None)
    next_items: list[PlannedItemOut] = []
    later_today: list[PlannedItemOut] = []
    six_hours = now_dt + timedelta(hours=6)
    for row in planned_rows:
        planned_start = row["planned_start"]
        if not planned_start:
            continue
        planned_time = datetime.fromisoformat(f"{row['date']}T{planned_start}:00")
        if planned_time < now_dt:
            continue
        target = next_items if planned_time <= six_hours else later_today
        target.append(
            PlannedItemOut(
                id=row["id"],
                item_id=row["item_id"],
                title=row["title"],
                type=row["type"],
                date=row["date"],
                planned_start=row["planned_start"],
                planned_end=row["planned_end"],
                status=row["status"],
                reason=row["reason"],
            )
        )

    return NowResponse(
        now=now_value,
        due_reminders=[
            {
                "id": row["id"],
                "due_at": row["due_at"],
                "kind": row["kind"],
                "title": row["title"],
                "body": row["body"],
                "status": row["status"],
                "reason": row["reason"],
                "related_item_title": row["related_item_title"],
                "context": row["body"] or row["related_item_title"],
            }
            for row in due_rows
        ],
        next_items=next_items,
        later_today=later_today,
    )


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
        db.update_reminder_schedule(reminder_id, snoozed_until, "pending")
    elif request.action == "done":
        db.update_reminder_status(reminder_id, "done", now_value, None)
        db.insert_completion(reminder["item_id"], reminder["rule_id"], {"source": "reminder"})
        if reminder["item_id"]:
            db.update_item_state(reminder["item_id"], "completed")
    elif request.action == "cancel_forever":
        db.update_reminder_status(reminder_id, "cancelled_forever", now_value, None)
        suppression_key = reminders.build_suppression_key(
            reminder["rule_id"],
            reminder["item_id"],
            suppression_signature(reminder),
        )
        db.insert_suppression(suppression_key, reminder["rule_id"])
        if reminder["item_id"]:
            db.suppress_item_reminders(reminder["item_id"])
    elif request.action == "move":
        if request.move_to:
            move_to = request.move_to
        else:
            move_to = (datetime.utcnow() + timedelta(minutes=30)).replace(microsecond=0).isoformat()
        db.update_reminder_schedule(reminder_id, move_to, "pending")
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
    range: str | None = None,
    status: str | None = None,
    item_type: str | None = Query(default=None, alias="type"),
    q: str | None = None,
) -> TaskListResponse:
    today = date.today().isoformat()
    date_from = None
    date_to = None
    if range == "today":
        date_from = today
        date_to = today
    elif range == "week":
        date_from = today
        date_to = (date.today() + timedelta(days=7)).isoformat()
    plans = db.list_latest_plans(date_from, date_to)
    items: list[PlannedItemOut] = []
    status_filter = None if status in (None, "all") else status
    type_filter = None if item_type in (None, "all") else item_type
    for plan in plans:
        rows = db.list_planned_items(plan["id"], date_from, date_to, status_filter, type_filter, q)
        for row in rows:
            items.append(
                PlannedItemOut(
                    id=row["id"],
                    item_id=row["item_id"],
                    title=row["title"],
                    type=row["type"],
                    date=row["date"],
                    planned_start=row["planned_start"],
                    planned_end=row["planned_end"],
                    status=row["status"],
                    reason=row["reason"],
                )
            )
    return TaskListResponse(items=items)


@app.post("/tasks", response_model=ScheduleItem)
async def create_task(task: TaskCreate) -> ScheduleItem:
    task_payload = task.model_dump()
    task_payload["placement_hint"] = task_payload.get("placement_hint") or derive_placement_hint(
        ScheduleItem(**{**task_payload, "task_state": task_payload.get("task_state") or "pending"})
    )
    task_id = db.insert_task(task_payload)
    row = db.fetch_task(task_id)
    if not row:
        raise HTTPException(status_code=500, detail="Task not found after insert")
    return ScheduleItem(**dict(row))


@app.patch("/tasks/{task_id}", response_model=ScheduleItem)
async def update_task(task_id: int, task: TaskUpdate) -> ScheduleItem:
    fields = {key: value for key, value in task.model_dump().items() if value is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields provided")
    if "placement_hint" not in fields and ("title" in fields or "notes" in fields):
        existing = db.fetch_task(task_id)
        if existing:
            merged = {**dict(existing), **fields}
            fields["placement_hint"] = derive_placement_hint(ScheduleItem(**merged))
    db.update_task(task_id, fields)
    row = db.fetch_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return ScheduleItem(**dict(row))


@app.delete("/tasks/{task_id}")
async def delete_task(task_id: int) -> dict[str, Any]:
    db.delete_task(task_id)
    return {"ok": True}


@app.post("/tasks/quick_add", response_model=ScheduleItem)
async def quick_add(task: TaskQuickAdd) -> ScheduleItem:
    payload = {
        "title": task.title,
        "type": task.type,
        "date": task.date,
        "start_time": task.time,
        "duration_min": 0,
        "priority": task.priority or 1,
        "notes": task.notes,
        "task_state": "pending",
    }
    payload["placement_hint"] = derive_placement_hint(ScheduleItem(**payload))
    task_id = db.insert_task(payload)
    row = db.fetch_task(task_id)
    if not row:
        raise HTTPException(status_code=500, detail="Task not found after insert")
    schedule_item = ScheduleItem(**dict(row))
    if schedule_item.date and schedule_item.start_time:
        reminders.generate_single_item_reminder(schedule_item)
    if schedule_item.date:
        replan_day(schedule_item.date)
    return schedule_item


@app.post("/tasks/{task_id}/edit", response_model=ScheduleItem)
async def edit_task(task_id: int, task: TaskUpdate) -> ScheduleItem:
    return await update_task(task_id, task)


@app.post("/tasks/{task_id}/delete")
async def remove_task(task_id: int) -> dict[str, Any]:
    db.delete_task(task_id)
    return {"ok": True}


@app.post("/tasks/{task_id}/disable_reminders")
async def disable_task_reminders(task_id: int) -> dict[str, Any]:
    suppression_key = reminders.build_suppression_key(None, task_id, "item")
    db.insert_suppression(suppression_key, None)
    for signature in ("upcoming", "ending", "contextual"):
        suppression_key = reminders.build_suppression_key(None, task_id, signature)
        db.insert_suppression(suppression_key, None)
    db.suppress_item_reminders(task_id)
    return {"ok": True}


@app.post("/tasks/{task_id}/complete")
async def complete_task(task_id: int) -> dict[str, Any]:
    db.complete_task(task_id)
    return {"ok": True}


@app.post("/tasks/{task_id}/action")
async def task_action(task_id: int, request: TaskActionRequest) -> dict[str, Any]:
    if request.target == "reminder":
        reminder_id = request.reminder_id or task_id
        if request.action == "done":
            await ack_reminder(reminder_id, ReminderAckRequest(action="done"))
        elif request.action == "dismiss":
            await ack_reminder(reminder_id, ReminderAckRequest(action="dismiss"))
        elif request.action == "snooze":
            await ack_reminder(reminder_id, ReminderAckRequest(action="snooze", snooze_min=10))
        elif request.action == "delete":
            await ack_reminder(reminder_id, ReminderAckRequest(action="cancel_forever"))
        elif request.action == "reschedule":
            move_to = request.reschedule_time
            if not move_to:
                move_to = (datetime.utcnow() + timedelta(minutes=30)).replace(microsecond=0).isoformat()
            await ack_reminder(
                reminder_id,
                ReminderAckRequest(action="move", move_to=move_to),
            )
        return {"ok": True}

    if request.action == "done":
        db.update_planned_item_status(task_id, "done")
        planned = db.fetch_planned_item(task_id)
        if planned and planned["item_id"]:
            db.insert_completion(planned["item_id"], None, {"source": "planned"})
            db.update_item_state(planned["item_id"], "completed")
    elif request.action == "dismiss":
        db.update_planned_item_status(task_id, "dismissed")
    elif request.action == "delete":
        db.update_planned_item_status(task_id, "deleted")
    elif request.action == "snooze":
        row = db.fetch_planned_item(task_id)
        if row and row["planned_start"] and row["date"]:
            start_dt = datetime.fromisoformat(f"{row['date']}T{row['planned_start']}:00")
            new_start_dt = start_dt + timedelta(minutes=10)
            new_end = row["planned_end"]
            if row["planned_end"]:
                end_dt = datetime.fromisoformat(f"{row['date']}T{row['planned_end']}:00")
                duration = end_dt - start_dt
                new_end = (new_start_dt + duration).time().strftime("%H:%M")
            db.update_planned_item_time(task_id, new_start_dt.time().strftime("%H:%M"), new_end)
            if row["item_id"]:
                update_item_reminders(row["item_id"], row["type"], row["date"], new_start_dt.time().strftime("%H:%M"), new_end)
    elif request.action == "reschedule" and request.reschedule_time:
        row = db.fetch_planned_item(task_id)
        new_end = None
        if row and row["planned_start"] and row["planned_end"] and row["date"]:
            start_dt = datetime.fromisoformat(f"{row['date']}T{row['planned_start']}:00")
            end_dt = datetime.fromisoformat(f"{row['date']}T{row['planned_end']}:00")
            duration = end_dt - start_dt
            new_end = (datetime.fromisoformat(f"{row['date']}T{request.reschedule_time}:00") + duration).time().strftime("%H:%M")
        db.update_planned_item_time(task_id, request.reschedule_time, new_end)
        if row and row["item_id"] and row["date"]:
            update_item_reminders(row["item_id"], row["type"], row["date"], request.reschedule_time, new_end)
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
    return {"message": "Plangraph backend"}


def suppression_signature(reminder_row: Any) -> str:
    if reminder_row["rule_id"]:
        day = datetime.fromisoformat(reminder_row["due_at"]).date()
        week_start = (day - timedelta(days=day.weekday())).isoformat()
        return f"habit:{week_start}"
    if reminder_row["item_id"]:
        return "item"
    return "general"


def replan_day(day: str) -> None:
    latest = db.latest_plan_for_day(day)
    day_start = "07:00"
    day_end = "21:00"
    if latest:
        plan_detail = db.fetch_plan(latest["id"])
        if plan_detail:
            day_start = plan_detail["day_start"]
            day_end = plan_detail["day_end"]
        db.delete_plan_reminders(latest["id"])
    rows = db.list_items_for_day(day)
    items = [ScheduleItem(**dict(row)) for row in rows]
    planned_items, conflicts = plan_items(items, day_start, day_end)
    plan_id = db.insert_plan(day, day_start, day_end)
    db.insert_planned_items(plan_id, [item.model_dump() for item in planned_items])
    reminders.generate_event_reminders(plan_id, planned_items)
    reminders.attach_contextual_reminders(plan_id, day, day_start, planned_items, items)
    reminders.generate_habit_reminders(day)


def update_item_reminders(item_id: int, item_type: str, day: str, planned_start: str, planned_end: Optional[str]) -> None:
    lead_min = reminders.DEFAULT_LEADS.get(item_type, 10)
    start_minutes = reminders.parse_time(planned_start)
    due_minutes = max(0, start_minutes - lead_min)
    due_at = reminders.combine_date_time(day, reminders.format_time(due_minutes))
    db.update_reminder_due_for_item(item_id, "upcoming", due_at)
    if planned_end:
        end_minutes = reminders.parse_time(planned_end)
        end_due_minutes = max(0, end_minutes - 10)
        end_due_at = reminders.combine_date_time(day, reminders.format_time(end_due_minutes))
        db.update_reminder_due_for_item(item_id, "ending", end_due_at)
