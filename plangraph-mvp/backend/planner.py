from __future__ import annotations

from typing import List, Tuple

from models import PlannedItem, ScheduleItem


def to_minutes(value: str) -> int:
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def to_time(value: int) -> str:
    hours = value // 60
    minutes = value % 60
    return f"{hours:02d}:{minutes:02d}"


def default_duration(item: ScheduleItem) -> int:
    if item.duration_min > 0:
        return item.duration_min
    if item.type == "event":
        return 60
    if item.type == "task":
        return 30
    return 5


def plan_items(
    items: List[ScheduleItem],
    day_start: str,
    day_end: str,
) -> Tuple[List[PlannedItem], List[str]]:
    day_start_min = to_minutes(day_start)
    day_end_min = to_minutes(day_end)
    conflicts: List[str] = []
    planned: List[PlannedItem] = []
    occupied: List[Tuple[int, int]] = []

    fixed_items = [item for item in items if item.start_time]
    flexible_items = [item for item in items if not item.start_time]

    for item in fixed_items:
        duration = default_duration(item)
        start = to_minutes(item.start_time)
        end = to_minutes(item.end_time) if item.end_time else start + duration
        status = "scheduled"
        reason = None
        if start < day_start_min or end > day_end_min:
            conflicts.append(f"{item.title} is outside day bounds")
            reason = "Outside day bounds"
        for occupied_start, occupied_end in occupied:
            if start < occupied_end and end > occupied_start:
                conflicts.append(f"{item.title} overlaps another fixed item")
                reason = "Overlaps another fixed item"
                break
        occupied.append((start, end))
        planned.append(
            PlannedItem(
                **item.model_dump(),
                planned_start=to_time(start),
                planned_end=to_time(end),
                status=status,
                reason=reason,
            )
        )

    occupied.sort()

    flexible_items.sort(key=lambda item: item.priority, reverse=True)

    for item in flexible_items:
        duration = default_duration(item)
        slot_start = day_start_min
        scheduled = False
        for occupied_start, occupied_end in occupied:
            if slot_start + duration <= occupied_start:
                scheduled = True
                break
            slot_start = max(slot_start, occupied_end)
        if not scheduled and slot_start + duration <= day_end_min:
            scheduled = True

        if scheduled and slot_start + duration <= day_end_min:
            planned_start = slot_start
            planned_end = slot_start + duration
            occupied.append((planned_start, planned_end))
            occupied.sort()
            planned.append(
                PlannedItem(
                    **item.model_dump(),
                    planned_start=to_time(planned_start),
                    planned_end=to_time(planned_end),
                    status="scheduled",
                    reason="Scheduled in earliest available slot",
                )
            )
        else:
            planned.append(
                PlannedItem(
                    **item.model_dump(),
                    planned_start=None,
                    planned_end=None,
                    status="unscheduled",
                    reason="No available slot",
                )
            )

    planned.sort(key=lambda item: (item.planned_start or "99:99"))

    return planned, conflicts
