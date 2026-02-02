from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ParseRequest(BaseModel):
    text: str
    today: Optional[str] = None


class ScheduleItem(BaseModel):
    id: Optional[int] = None
    title: str
    type: str = Field(pattern="^(event|task|reminder)$")
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_min: int = 0
    priority: int = 0
    location: Optional[str] = None
    notes: Optional[str] = None
    status: str = "pending"
    task_state: Optional[str] = "pending"
    time_pref: Optional[str] = None
    placement_hint: Optional[str] = None
    next_reminder_at: Optional[str] = None
    created_at: Optional[str] = None


class ParseResponse(BaseModel):
    items: List[ScheduleItem]


class EntryResponse(BaseModel):
    entry_id: int
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


class ReminderAckRequest(BaseModel):
    action: str = Field(pattern="^(dismiss|snooze|done|cancel_forever|move)$")
    snooze_min: Optional[int] = None
    move_to: Optional[str] = None


class ReminderOut(BaseModel):
    id: int
    due_at: str
    kind: str
    title: str
    body: Optional[str]
    status: str
    reason: Optional[str]
    related_item_title: Optional[str] = None
    context: Optional[str] = None


class RemindersDueResponse(BaseModel):
    now: str
    reminders: List[ReminderOut]


class NowResponse(BaseModel):
    now: str
    has_plan: bool
    due_now: List[ReminderOut]
    next_six_hours: List[ReminderOut]
    later_today: List[ReminderOut]
    overlap_message: Optional[str] = None
    overlap_move_id: Optional[int] = None
    overlap_move_to: Optional[str] = None


class HabitRuleIn(BaseModel):
    key: str
    title: str
    lead_min: int = 10
    enabled: bool = True
    default_time: Optional[str] = None
    target_per_week: Optional[int] = None


class HabitRuleOut(BaseModel):
    id: int
    key: str
    title: str
    lead_min: int
    enabled: bool
    default_time: Optional[str]
    target_per_week: Optional[int]
    typical_time: Optional[str]


class HabitRulesResponse(BaseModel):
    rules: List[HabitRuleOut]


class HistoryEntry(BaseModel):
    id: int
    text: str
    today: Optional[str]
    created_at: str
    item_count: int


class HistoryPlan(BaseModel):
    id: int
    day: str
    day_start: str
    day_end: str
    created_at: str
    planned_count: int
    unscheduled_count: int


class HistoryResponse(BaseModel):
    entries: List[HistoryEntry]
    plans: List[HistoryPlan]


class TaskCreate(BaseModel):
    title: str
    type: str = Field(pattern="^(event|task|reminder)$")
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_min: int = 0
    priority: int = 0
    location: Optional[str] = None
    notes: Optional[str] = None
    status: str = "pending"
    task_state: Optional[str] = "pending"
    time_pref: Optional[str] = None
    placement_hint: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[str] = Field(default=None, pattern="^(event|task|reminder)$")
    date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_min: Optional[int] = None
    priority: Optional[int] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    task_state: Optional[str] = None
    time_pref: Optional[str] = None
    placement_hint: Optional[str] = None


class TaskQuickAdd(BaseModel):
    title: str
    date: Optional[str] = None
    time: Optional[str] = None
    priority: Optional[int] = 1
    type: str = Field(default="task", pattern="^(event|task|reminder)$")
    notes: Optional[str] = None


class TaskListResponse(BaseModel):
    items: List[ScheduleItem]
