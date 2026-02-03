from __future__ import annotations

import threading
import time
from datetime import datetime

from sqlalchemy.orm import Session

from database import SessionLocal
from models import Event, Reminder


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
            due = (
                session.query(Reminder)
                .filter(Reminder.state == "scheduled", Reminder.scheduled_for <= now)
                .all()
            )
            for reminder in due:
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
            if due:
                session.commit()
        finally:
            session.close()
