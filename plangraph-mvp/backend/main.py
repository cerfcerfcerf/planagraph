from __future__ import annotations

import json
import os
from datetime import date
from typing import Any, List, Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError

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


class ParseRequest(BaseModel):
    text: str
    today: Optional[str] = None


class ScheduleItem(BaseModel):
    title: str
    type: str = Field(pattern="^(event|task|reminder)$")
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_min: int = 0
    priority: int = 0
    location: Optional[str] = None
    notes: Optional[str] = None


class ParseResponse(BaseModel):
    items: List[ScheduleItem]


class PlanRequest(BaseModel):
    day: str
    day_start: str
    day_end: str
    items: List[ScheduleItem]


class PlannedItem(ScheduleItem):
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None
    status: str
    reason: Optional[str] = None


class PlanResponse(BaseModel):
    day: str
    planned: List[PlannedItem]
    conflicts: List[str]


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "model": OLLAMA_MODEL}


def to_minutes(value: str) -> int:
    return int(value.split(":")[0]) * 60 + int(value.split(":")[1])


def to_time(value: int) -> str:
    hours = value // 60
    minutes = value % 60
    return f"{hours:02d}:{minutes:02d}"


def default_duration(item: ScheduleItem) -> int:
    if item.duration_min > 0:
        return item.duration_min
    if item.type == "event":
        return 60
    if item.type == "task":
        return 30
    return 5


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


@app.post("/parse", response_model=ParseResponse)
async def parse_text(request: ParseRequest) -> ParseResponse:
    today_value = request.today or date.today().isoformat()
    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "messages": [
            {"role": "system", "content": build_system_prompt(today_value)},
            {"role": "user", "content": request.text},
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
        return ParseResponse(items=normalized_items)
    except (ValueError, ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=f"Unable to parse model output: {exc}") from exc


@app.post("/plan", response_model=PlanResponse)
async def plan_day(request: PlanRequest) -> PlanResponse:
    day_start_min = to_minutes(request.day_start)
    day_end_min = to_minutes(request.day_end)
    conflicts: List[str] = []
    planned: List[PlannedItem] = []
    occupied: List[tuple[int, int]] = []

    fixed_items = [item for item in request.items if item.start_time]
    flexible_items = [item for item in request.items if not item.start_time]

    for item in fixed_items:
        duration = default_duration(item)
        start = to_minutes(item.start_time)
        end = to_minutes(item.end_time) if item.end_time else start + duration
        status = "scheduled"
        reason = None
        if start < day_start_min or end > day_end_min:
            conflicts.append(f"{item.title} is outside day bounds")
            status = "scheduled"
            reason = "Outside day bounds"
        for occupied_start, occupied_end in occupied:
            if start < occupied_end and end > occupied_start:
                conflicts.append(f"{item.title} overlaps another fixed item")
                status = "scheduled"
                reason = "Overlaps another fixed item"
                break
        occupied.append((start, end))
        planned.append(
            PlannedItem(
                **item.model_dump(),
                planned_start=to_time(start),
                planned_end=to_time(end),
                status=status,
                reason=reason,
            )
        )

    occupied.sort()

    flexible_items.sort(key=lambda item: item.priority, reverse=True)

    for item in flexible_items:
        duration = default_duration(item)
        slot_start = day_start_min
        scheduled = False
        for occupied_start, occupied_end in occupied:
            if slot_start + duration <= occupied_start:
                scheduled = True
                break
            slot_start = max(slot_start, occupied_end)
        if not scheduled and slot_start + duration <= day_end_min:
            scheduled = True

        if scheduled and slot_start + duration <= day_end_min:
            planned_start = slot_start
            planned_end = slot_start + duration
            occupied.append((planned_start, planned_end))
            occupied.sort()
            planned.append(
                PlannedItem(
                    **item.model_dump(),
                    planned_start=to_time(planned_start),
                    planned_end=to_time(planned_end),
                    status="scheduled",
                    reason="Scheduled in earliest available slot",
                )
            )
        else:
            planned.append(
                PlannedItem(
                    **item.model_dump(),
                    planned_start=None,
                    planned_end=None,
                    status="unscheduled",
                    reason="No available slot",
                )
            )

    planned.sort(key=lambda item: (item.planned_start or "99:99"))

    return PlanResponse(day=request.day, planned=planned, conflicts=conflicts)


@app.get("/")
async def root() -> dict[str, Any]:
    return {"message": "Plangraph MVP backend"}
