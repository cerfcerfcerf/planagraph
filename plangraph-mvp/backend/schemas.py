from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class ParseRequest(BaseModel):
    text: str


class ParsedItem(BaseModel):
    title: str
    date: Optional[str] = None
    due_time: Optional[str] = None
    window_start: Optional[str] = None
    window_end: Optional[str] = None
    priority: Literal["low", "med", "high"] = "med"
    recurrence: Literal["none", "daily", "weekly", "every_2_days", "custom"] = "none"
    recurrence_detail: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    notes: Optional[str] = None


class ParseResponse(BaseModel):
    items: list[ParsedItem]


class TaskBase(BaseModel):
    title: str
    notes: Optional[str] = None
    due_at: Optional[datetime] = None
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    priority: Literal["low", "med", "high"] = "med"
    status: Literal["active", "completed", "archived"] = "active"
    recurrence: Optional[str] = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    due_at: Optional[datetime] = None
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    priority: Optional[Literal["low", "med", "high"]] = None
    status: Optional[Literal["active", "completed", "archived"]] = None
    recurrence: Optional[str] = None


class TaskOut(TaskBase):
    id: int
    created_at: datetime
    updated_at: datetime


class TasksResponse(BaseModel):
    items: list[TaskOut]


class SettingsOut(BaseModel):
    policy_mode: Literal["baseline", "adaptive"]
    daily_budget: int
    quiet_hours_start: str
    quiet_hours_end: str
    lead_time_min: int


class SettingsIn(SettingsOut):
    pass


class ReminderAction(BaseModel):
    action: Literal["done", "snooze_10", "snooze_30", "dismiss"]


class ReminderOut(BaseModel):
    id: int
    task_id: int
    scheduled_for: datetime
    state: str


class NowItem(BaseModel):
    task_id: int
    title: str
    due_at: Optional[datetime] = None
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None
    priority: str


class NowResponse(BaseModel):
    next_best_action: Optional[NowItem] = None
    next_reminder_id: Optional[int] = None
    why_now: str
    next_6_hours: list[NowItem]
    later_today: list[NowItem]


class InsightsSeriesPoint(BaseModel):
    date: str
    count: int


class InsightsResponse(BaseModel):
    notifications_per_day: list[InsightsSeriesPoint]
    completions_per_day: list[InsightsSeriesPoint]
    missed_rate_proxy: float
    notifications_per_completion: float
    totals: dict[str, Any]
