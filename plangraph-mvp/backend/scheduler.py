from __future__ import annotations

import threading
import time
from datetime import datetime

from sqlalchemy.orm import Session

from database import SessionLocal, now_utc
from models import Event, Reminder


class ReminderScheduler:
    def __init__(self, interval_seconds: int = 30) -> None:
        self.interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._tick()
            self._stop.wait(self.interval_seconds)

    def _tick(self) -> None:
        session: Session = SessionLocal()
        try:
            now = now_utc()
            due_reminders = (
                session.query(Reminder)
                .filter(Reminder.state == "scheduled", Reminder.scheduled_for <= now)
                .all()
            )
            for reminder in due_reminders:
                reminder.state = "sent"
                event = Event(
                    type="reminder_sent",
                    task_id=reminder.task_id,
                    reminder_id=reminder.id,
                    ts=datetime.utcnow(),
                )
                session.add(event)
            session.commit()
        finally:
            session.close()
