from datetime import datetime, timedelta

from models import Settings, Task
from policy import is_actionable_now, roll_task_forward, urgency_score


def test_actionability_gating_window_and_due() -> None:
    settings = Settings(lead_time_minutes=20)
    window_start = datetime(2024, 1, 1, 10, 0)
    window_end = datetime(2024, 1, 1, 11, 0)
    task = Task(status="active", window_start=window_start, window_end=window_end)

    assert not is_actionable_now(task, datetime(2024, 1, 1, 9, 30), settings)
    assert is_actionable_now(task, datetime(2024, 1, 1, 9, 45), settings)
    assert not is_actionable_now(task, datetime(2024, 1, 1, 11, 1), settings)

    due_task = Task(status="active", due_at=datetime(2024, 1, 1, 10, 0))
    assert not is_actionable_now(due_task, datetime(2024, 1, 1, 9, 39), settings)
    assert is_actionable_now(due_task, datetime(2024, 1, 1, 10, 15), settings)
    assert not is_actionable_now(due_task, datetime(2024, 1, 1, 10, 31), settings)


def test_actionability_no_time_today_only() -> None:
    settings = Settings(lead_time_minutes=15)
    task = Task(status="active", created_at=datetime(2024, 1, 1, 8, 0))
    assert is_actionable_now(task, datetime(2024, 1, 1, 12, 0), settings)
    assert not is_actionable_now(task, datetime(2024, 1, 2, 9, 0), settings)


def test_cross_midnight_window_roll_forward() -> None:
    start = datetime(2024, 1, 1, 22, 0)
    end = datetime(2024, 1, 2, 6, 0)
    task = Task(
        status="active",
        recurrence="daily",
        window_start=start,
        window_end=end,
    )
    assert roll_task_forward(task)
    assert task.window_start == start + timedelta(days=1)
    assert task.window_end == end + timedelta(days=1)


def test_urgency_score_monotonicity() -> None:
    now = datetime(2024, 1, 1, 9, 0)
    far_task = Task(
        status="active",
        priority="med",
        due_at=now + timedelta(minutes=120),
    )
    near_task = Task(
        status="active",
        priority="med",
        due_at=now + timedelta(minutes=60),
    )
    assert urgency_score(near_task, now) > urgency_score(far_task, now)
