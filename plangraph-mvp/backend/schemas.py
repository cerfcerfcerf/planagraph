from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

JSON_ENCODERS = {
    datetime: lambda dt: dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
}


class APIModel(BaseModel):
    model_config = ConfigDict(json_encoders=JSON_ENCODERS)


class ParseRequest(APIModel):
    text: str


class ParseItem(APIModel):
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
    parse_error: str | None = None


class ParseResponse(APIModel):
    items: list[ParseItem]


class TaskBase(APIModel):
    title: str
    notes: str | None = None
    due_at: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    priority: Literal["low", "med", "high"] = "med"
    task_type: Literal[
        "meal",
        "sleep",
        "medication",
        "hygiene",
        "class",
        "exercise",
        "other",
    ] = "other"
    recurrence: str | None = None
    recurrence_detail: str | None = None


class TaskCreate(TaskBase):
    pass


class TaskUpdate(APIModel):
    title: str | None = None
    notes: str | None = None
    due_at: datetime | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    priority: Literal["low", "med", "high"] | None = None
    task_type: Literal[
        "meal",
        "sleep",
        "medication",
        "hygiene",
        "class",
        "exercise",
        "other",
    ] | None = None
    status: Literal["active", "completed", "archived"] | None = None
    recurrence: str | None = None
    recurrence_detail: str | None = None


class TaskOut(TaskBase):
    model_config = ConfigDict(from_attributes=True, json_encoders=JSON_ENCODERS)

    id: int
    status: str
    created_at: datetime
    updated_at: datetime


class TaskListResponse(APIModel):
    tasks: list[TaskOut]


class SettingsOut(APIModel):
    model_config = ConfigDict(from_attributes=True, json_encoders=JSON_ENCODERS)

    policy_mode: Literal["baseline", "adaptive"]
    daily_budget: int
    quiet_hours_start: str | None
    quiet_hours_end: str | None
    lead_time_minutes: int


class SettingsUpdate(APIModel):
    policy_mode: Literal["baseline", "adaptive"] | None = None
    daily_budget: int | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    lead_time_minutes: int | None = None


class WhyNow(APIModel):
    reasons: list[str]
    score: float


class ReminderOut(APIModel):
    model_config = ConfigDict(from_attributes=True, json_encoders=JSON_ENCODERS)

    id: int
    task_id: int
    scheduled_for: datetime
    state: str
    title: str | None = None
    why_now: WhyNow | None = None


class NowAction(APIModel):
    reminder_id: int | None
    task_id: int | None
    title: str
    scheduled_for: datetime | None
    window_start: datetime | None
    window_end: datetime | None
    priority: str
    why_now: WhyNow


class UpcomingTask(APIModel):
    task_id: int
    title: str
    scheduled_for: datetime | None
    window_start: datetime | None
    window_end: datetime | None
    priority: str
    why_now: WhyNow


class NowResponse(APIModel):
    next_best_action: NowAction | None
    next_6_hours: list[UpcomingTask]
    later_today: list[UpcomingTask]


class ReminderActionRequest(APIModel):
    action: Literal["done", "snooze", "ignore", "lazy"]
    reason: str | None = None


class InsightSeries(APIModel):
    label: str
    points: list[dict]


class InsightsResponse(APIModel):
    completion_rate_baseline: float
    completion_rate_adaptive: float
    best_hours: list[dict]
    wasted_nudges: list[dict]
    recommendations: list[str]


class InsightsSummaryResponse(APIModel):
    narrative: str
    recommendations: list[str]
    metrics: dict[str, float]


class LazySuggestionRequest(APIModel):
    title: str
    notes: str | None = None


class LazySuggestionResponse(APIModel):
    suggestions: list[str]


class TemplateCreate(APIModel):
    title: str
    default_duration_min: int = 30
    default_type: Literal[
        "meal",
        "sleep",
        "medication",
        "hygiene",
        "class",
        "exercise",
        "other",
    ] = "other"
    default_priority: Literal["low", "med", "high"] = "med"
    pinned: bool = False


class TemplateOut(TemplateCreate):
    model_config = ConfigDict(from_attributes=True, json_encoders=JSON_ENCODERS)

    id: int
    used_count: int
    last_used: datetime | None
