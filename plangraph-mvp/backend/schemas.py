from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ParseRequest(BaseModel):
    text: str


class ParseItem(BaseModel):
    title: str
    date: str | None = None
    due_time: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    priority: Literal["low", "med", "high"] = "med"
    recurrence: Literal["none", "daily", "weekly", "every_2_days", "custom"] = "none"
    recurrence_detail: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.6)
    notes: str | None = None
    recurrence_suggestions: list[dict] | None = None
    task_type: str | None = None


class ParseResponse(BaseModel):
    items: list[ParseItem]


class TaskBase(BaseModel):
    title: str
    notes: str | None = None
    due_at: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    priority: Literal["low", "med", "high"] = "med"
    task_type: Literal["routine", "appointment", "study", "exercise", "other"] = "other"
    recurrence: str | None = None
    recurrence_detail: str | None = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: str | None = None
    notes: str | None = None
    due_at: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    priority: Literal["low", "med", "high"] | None = None
    task_type: Literal["routine", "appointment", "study", "exercise", "other"] | None = None
    status: Literal["active", "completed", "archived"] | None = None
    recurrence: str | None = None
    recurrence_detail: str | None = None


class TaskOut(TaskBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    created_at: datetime
    updated_at: datetime


class TaskListResponse(BaseModel):
    tasks: list[TaskOut]


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    policy_mode: Literal["baseline", "adaptive"]
    daily_budget: int
    quiet_hours_start: str | None
    quiet_hours_end: str | None
    lead_time_minutes: int


class SettingsUpdate(BaseModel):
    policy_mode: Literal["baseline", "adaptive"] | None = None
    daily_budget: int | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    lead_time_minutes: int | None = None


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    scheduled_for: datetime
    state: str
    title: str | None = None


class NowAction(BaseModel):
    reminder_id: int | None
    task_id: int | None
    title: str
    scheduled_for: datetime | None
    window_start: datetime | None
    window_end: datetime | None
    priority: str
    why_now: str


class NowResponse(BaseModel):
    next_best_action: NowAction | None
    next_6_hours: list[ReminderOut]
    later_today: list[ReminderOut]


class ReminderActionRequest(BaseModel):
    action: Literal["done", "snooze_10", "snooze_30", "dismiss"]


class InsightSeries(BaseModel):
    label: str
    points: list[dict]


class InsightsResponse(BaseModel):
    notifications_per_day: list[dict]
    completions_per_day: list[dict]
    missed_rate_proxy: list[dict]
    notifications_per_completion: list[dict]


class InsightsSummaryResponse(BaseModel):
    narrative: str
    recommendations: list[str]
    metrics: dict[str, float]


class LazySuggestionRequest(BaseModel):
    title: str
    notes: str | None = None


class LazySuggestionResponse(BaseModel):
    suggestions: list[str]


class TemplateCreate(BaseModel):
    title: str
    default_duration_min: int = 30
    default_type: Literal["routine", "appointment", "study", "exercise", "other"] = "other"
    default_priority: Literal["low", "med", "high"] = "med"
    pinned: bool = False


class TemplateOut(TemplateCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    used_count: int
    last_used: datetime | None
