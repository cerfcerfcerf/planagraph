from __future__ import annotations

import threading
import time
from datetime import datetime

from sqlalchemy.orm import Session

from database import SessionLocal
from models import Event, Reminder
from policy import (
    get_settings,
    is_actionable_now,
    is_occurrence_expired,
    roll_task_forward,
    schedule_reminder,
    schedule_upcoming_reminders,
    should_fire,
)
from models import Task


class ReminderScheduler:
    def __init__(self, interval_seconds: int = 45) -> None:
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._process_due_reminders()
            self._stop_event.wait(self.interval_seconds)

    def _process_due_reminders(self) -> None:
        session: Session = SessionLocal()
        try:
            now = datetime.utcnow()
            settings = get_settings(session)
            scheduled = session.query(Reminder).filter(Reminder.state == "scheduled").all()
            for reminder in scheduled:
                task = session.get(Task, reminder.task_id)
                if not task:
                    continue
                if reminder.scheduled_for <= now and not is_actionable_now(task, now, settings):
                    reminder.state = "expired"
                    session.add(
                        Event(
                            type="reminder_expired",
                            task_id=task.id,
                            reminder_id=reminder.id,
                            ts=now,
                            payload_json=None,
                        )
                    )
                    if is_occurrence_expired(task, now, settings) and roll_task_forward(task):
                        schedule_reminder(session, task)
                    continue
                if should_fire(reminder, task, now, settings):
                    reminder.state = "sent"
                    session.add(
                        Event(
                            type="reminder_sent",
                            task_id=reminder.task_id,
                            reminder_id=reminder.id,
                            ts=now,
                            payload_json=None,
                        )
                    )
                elif is_occurrence_expired(task, now, settings):
                    reminder.state = "expired"
                    session.add(
                        Event(
                            type="reminder_expired",
                            task_id=task.id,
                            reminder_id=reminder.id,
                            ts=now,
                            payload_json=None,
                        )
                    )
                    if roll_task_forward(task):
                        schedule_reminder(session, task)
            schedule_upcoming_reminders(session, now)
            session.commit()
        finally:
            session.close()
