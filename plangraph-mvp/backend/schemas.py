from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ParseRequest(BaseModel):
    text: str


class ParsedItem(BaseModel):
    title: str
    date: str | None = None
    due_time: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    priority: Literal["low", "med", "high"]
    recurrence: Literal["none", "daily", "weekly", "every_2_days", "custom"]
    recurrence_detail: str | None = None
    confidence: float = Field(ge=0, le=1)
    notes: str | None = None


class ParseResponse(BaseModel):
    items: list[ParsedItem]


class TaskCreate(BaseModel):
    title: str
    notes: str | None = None
    date: str | None = None
    due_time: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    priority: Literal["low", "med", "high"] = "med"
    status: Literal["active", "completed", "archived"] = "active"
    recurrence: Literal["none", "daily", "weekly", "every_2_days", "custom"] = "none"
    recurrence_detail: str | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    notes: str | None = None
    date: str | None = None
    due_time: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    priority: Literal["low", "med", "high"] | None = None
    status: Literal["active", "completed", "archived"] | None = None
    recurrence: Literal["none", "daily", "weekly", "every_2_days", "custom"] | None = None
    recurrence_detail: str | None = None


class TaskOut(BaseModel):
    id: int
    title: str
    notes: str | None
    due_at: datetime | None
    window_start: datetime | None
    window_end: datetime | None
    priority: str
    status: str
    recurrence: str | None
    recurrence_detail: str | None
    created_at: datetime
    updated_at: datetime


class SettingsOut(BaseModel):
    policy_mode: Literal["baseline", "adaptive"]
    daily_budget: int
    quiet_hours_start: str | None
    quiet_hours_end: str | None
    lead_time_min: int


class SettingsUpdate(BaseModel):
    policy_mode: Literal["baseline", "adaptive"] | None = None
    daily_budget: int | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    lead_time_min: int | None = None


class ReminderActionRequest(BaseModel):
    action: Literal["done", "snooze_10", "snooze_30", "dismiss"]


class ReminderOut(BaseModel):
    id: int
    task_id: int
    title: str
    scheduled_for: datetime
    state: str


class NowResponse(BaseModel):
    next_best_action: ReminderOut | None
    next_6_hours: list[ReminderOut]
    later_today: list[ReminderOut]
    why_now: str


class InsightSeriesPoint(BaseModel):
    date: str
    value: int


class InsightsResponse(BaseModel):
    notifications_per_day: list[InsightSeriesPoint]
    completions_per_day: list[InsightSeriesPoint]
    notifications_per_completion: list[InsightSeriesPoint]
    missed_rate_proxy: list[InsightSeriesPoint]
