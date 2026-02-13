from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="med")
    task_type: Mapped[str] = mapped_column(String(32), default="other")
    status: Mapped[str] = mapped_column(String(16), default="active")
    recurrence: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recurrence_detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    reminders: Mapped[list[Reminder]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="scheduled")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    task: Mapped[Task] = relationship(back_populates="reminders")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    reminder_id: Mapped[int | None] = mapped_column(
        ForeignKey("reminders.id"), nullable=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_mode: Mapped[str] = mapped_column(String(16), default="adaptive")
    daily_budget: Mapped[int] = mapped_column(Integer, default=6)
    quiet_hours_start: Mapped[str | None] = mapped_column(String(5), default="23:30")
    quiet_hours_end: Mapped[str | None] = mapped_column(String(5), default="07:00")
    lead_time_minutes: Mapped[int] = mapped_column(Integer, default=20)


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    default_duration_min: Mapped[int] = mapped_column(Integer, default=30)
    default_type: Mapped[str] = mapped_column(String(32), default="other")
    default_priority: Mapped[str] = mapped_column(String(16), default="med")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class NudgeEvent(Base):
    __tablename__ = "nudge_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
