from __future__ import annotations

import asyncio
from typing import Optional

from db import get_session
from policy import mark_due_reminders


class ReminderScheduler:
    def __init__(self, interval_s: int = 45) -> None:
        self.interval_s = interval_s
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        while self._running:
            with get_session() as session:
                mark_due_reminders(session)
            await asyncio.sleep(self.interval_s)


scheduler = ReminderScheduler()
