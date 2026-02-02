from __future__ import annotations

from typing import List, Tuple

from models import PlannedItem, ScheduleItem


KEYWORDS_EVENING = ["buy", "groceries", "shop", "store", "mall"]
KEYWORDS_AFTERNOON = ["homework", "study", "assignment"]
KEYWORDS_REMINDER = ["keys", "wallet", "headphones", "passport", "charger"]
KEYWORDS_ERRAND = ["groceries", "grocery", "shopping", "errand", "store"]
KEYWORDS_STUDY = ["homework", "study", "assignment", "reading"]
KEYWORDS_HEALTH = ["gym", "workout", "doctor", "dentist", "run"]
KEYWORDS_ADMIN = ["email", "paperwork", "bills", "forms"]
KEYWORDS_PREP = ["prep", "prepare", "pack", "charge"]
KEYWORDS_SOCIAL = ["dinner", "friends", "hangout", "party"]


def derive_placement_hint(item: ScheduleItem) -> str:
    text = f"{item.title} {item.notes or ''}".lower()
    if any(keyword in text for keyword in KEYWORDS_ERRAND):
        return "errand"
    if any(keyword in text for keyword in KEYWORDS_STUDY):
        return "study"
    if any(keyword in text for keyword in KEYWORDS_HEALTH):
        return "health"
    if any(keyword in text for keyword in KEYWORDS_ADMIN):
        return "admin"
    if any(keyword in text for keyword in KEYWORDS_PREP):
        return "prep"
    if any(keyword in text for keyword in KEYWORDS_SOCIAL):
        return "social"
    return "general"


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


def infer_time_pref(item: ScheduleItem, fixed_items: List[ScheduleItem]) -> str:
    if item.time_pref:
        return item.time_pref
    text = f"{item.title} {item.notes or ''}".lower()
    if item.type == "reminder" and not item.start_time:
        return "after_event:first"
    placement_hint = item.placement_hint or derive_placement_hint(item)
    if item.type == "task" and placement_hint == "errand":
        if any("gym" in (fixed.title or "").lower() for fixed in fixed_items):
            return "after_event:gym"
        return "after_event:last"
    if placement_hint == "study":
        return "afternoon"
    if placement_hint == "social":
        return "evening"
    if placement_hint == "admin":
        return "morning"
    if placement_hint == "prep":
        return "morning"
    if any(keyword in text for keyword in KEYWORDS_EVENING):
        return "evening"
    if any(keyword in text for keyword in KEYWORDS_AFTERNOON):
        return "afternoon"
    if any(keyword in text for keyword in KEYWORDS_REMINDER):
        return "after_event:first"
    return "any"


def preferred_windows(
    pref: str,
    fixed_items: List[ScheduleItem],
    day_start_min: int,
    day_end_min: int,
) -> List[Tuple[int, int]]:
    if pref.startswith("after_event"):
        anchor = None
        sorted_fixed = sorted(fixed_items, key=lambda fixed: fixed.start_time or "99:99")
        if pref == "after_event:last":
            anchor = sorted_fixed[-1] if sorted_fixed else None
        elif pref == "after_event:gym":
            for item in sorted_fixed:
                if "gym" in (item.title or "").lower():
                    anchor = item
            if anchor is None and sorted_fixed:
                anchor = sorted_fixed[-1]
        else:
            anchor = sorted_fixed[0] if sorted_fixed else None
        if anchor and anchor.start_time:
            anchor_start = to_minutes(anchor.start_time)
            anchor_end = to_minutes(anchor.end_time) if anchor.end_time else anchor_start + default_duration(anchor)
            return [(max(day_start_min, anchor_end + 10), day_end_min)]
        return [(day_start_min, day_end_min)]
    if pref == "morning":
        return [(max(day_start_min, 6 * 60), min(day_end_min, 12 * 60))]
    if pref == "afternoon":
        return [(max(day_start_min, 12 * 60), min(day_end_min, 17 * 60))]
    if pref == "evening":
        return [(max(day_start_min, 17 * 60), min(day_end_min, 21 * 60))]
    return [(day_start_min, day_end_min)]


def available_slots(occupied: List[Tuple[int, int]], day_start_min: int, day_end_min: int) -> List[Tuple[int, int]]:
    slots: List[Tuple[int, int]] = []
    cursor = day_start_min
    for start, end in sorted(occupied):
        if cursor < start:
            slots.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < day_end_min:
        slots.append((cursor, day_end_min))
    return slots


def find_slot(
    occupied: List[Tuple[int, int]],
    day_start_min: int,
    day_end_min: int,
    duration: int,
    windows: List[Tuple[int, int]],
) -> int | None:
    slots = available_slots(occupied, day_start_min, day_end_min)
    for window_start, window_end in windows:
        for slot_start, slot_end in slots:
            start = max(slot_start, window_start)
            end = min(slot_end, window_end)
            if start + duration <= end:
                return start
    for slot_start, slot_end in slots:
        if slot_start + duration <= slot_end:
            return slot_start
    return None


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
        placement_hint = item.placement_hint or derive_placement_hint(item)
        time_pref = infer_time_pref(item, fixed_items)
        item_payload = item.model_copy(update={"time_pref": time_pref, "placement_hint": placement_hint})
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
                **item_payload.model_dump(),
                planned_start=to_time(start),
                planned_end=to_time(end),
                status=status,
                reason=reason,
            )
        )

    occupied.sort()

    flexible_items.sort(key=lambda item: item.priority, reverse=True)

    for item in flexible_items:
        placement_hint = item.placement_hint or derive_placement_hint(item)
        time_pref = infer_time_pref(item, fixed_items)
        item_payload = item.model_copy(update={"time_pref": time_pref, "placement_hint": placement_hint})
        if item.type == "reminder":
            planned.append(
                PlannedItem(
                    **item_payload.model_dump(),
                    planned_start=None,
                    planned_end=None,
                    status="unscheduled",
                    reason="Reminder is anchored to events, not scheduled as a task.",
                )
            )
            continue
        duration = default_duration(item)
        pref_windows = preferred_windows(time_pref, fixed_items, day_start_min, day_end_min)
        slot_start = find_slot(occupied, day_start_min, day_end_min, duration, pref_windows)

        if slot_start is not None and slot_start + duration <= day_end_min:
            planned_start = slot_start
            planned_end = slot_start + duration
            occupied.append((planned_start, planned_end))
            occupied.sort()
            planned.append(
                PlannedItem(
                    **item_payload.model_dump(),
                    planned_start=to_time(planned_start),
                    planned_end=to_time(planned_end),
                    status="scheduled",
                    reason=f"Scheduled using preference: {time_pref}.",
                )
            )
        else:
            planned.append(
                PlannedItem(
                    **item_payload.model_dump(),
                    planned_start=None,
                    planned_end=None,
                    status="unscheduled",
                    reason="No available slot",
                )
            )

    planned.sort(key=lambda item: (item.planned_start or "99:99"))

    return planned, conflicts
