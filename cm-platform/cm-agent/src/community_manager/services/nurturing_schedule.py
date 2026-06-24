"""Nurturing schedule logic.

Ported from NurturingSchedule.cs.
Two-cycle monthly system:
- Cycle 1: Generation on Friday before 2nd Wednesday, Send on 2nd Wednesday
- Cycle 2: Generation on Friday before 4th Wednesday, Send on 4th Wednesday
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

BUENOS_AIRES = ZoneInfo("America/Buenos_Aires")


@dataclass(frozen=True)
class NurturingCycleSlot:
    year: int
    month: int
    cycle_number: int
    generation_date: date
    send_date: date

    @property
    def cycle_key(self) -> str:
        return f"{self.year}-{self.month:02d}-c{self.cycle_number}"


def get_nth_wednesday(year: int, month: int, occurrence: int) -> date:
    """Get the Nth Wednesday of a month."""
    if occurrence < 1 or occurrence > 5:
        raise ValueError(f"Occurrence must be 1-5, got {occurrence}")

    # First day of month
    first_day = date(year, month, 1)

    # Find first Wednesday (weekday 2 = Wednesday)
    days_until_wednesday = (2 - first_day.weekday()) % 7
    first_wednesday = first_day + timedelta(days=days_until_wednesday)

    # Get the Nth Wednesday
    nth_wednesday = first_wednesday + timedelta(weeks=occurrence - 1)

    # Verify it's still in the same month
    if nth_wednesday.month != month:
        raise ValueError(f"No {occurrence}th Wednesday in {year}-{month:02d}")

    return nth_wednesday


def get_previous_friday(d: date) -> date:
    """Get the Friday before a given date."""
    days_since_friday = (d.weekday() - 4) % 7
    if days_since_friday == 0:
        days_since_friday = 7
    return d - timedelta(days=days_since_friday)


def get_cycle_slot(year: int, month: int, cycle_number: int) -> NurturingCycleSlot:
    """Get the cycle slot for a given cycle number (1 or 2)."""
    if cycle_number not in (1, 2):
        raise ValueError(f"Cycle number must be 1 or 2, got {cycle_number}")

    if cycle_number == 1:
        send_date = get_nth_wednesday(year, month, 2)  # 2nd Wednesday
    else:
        send_date = get_nth_wednesday(year, month, 4)  # 4th Wednesday

    generation_date = get_previous_friday(send_date)

    return NurturingCycleSlot(
        year=year,
        month=month,
        cycle_number=cycle_number,
        generation_date=generation_date,
        send_date=send_date,
    )


def is_business_day(d: date) -> bool:
    """Check if a date is a business day (Mon-Fri)."""
    return d.weekday() < 5


def today_in_buenos_aires() -> date:
    """Get today's date in Buenos Aires timezone."""
    return datetime.now(BUENOS_AIRES).date()


def now_in_buenos_aires() -> datetime:
    """Get current datetime in Buenos Aires timezone."""
    return datetime.now(BUENOS_AIRES)


def is_automatic_dispatch_time(local_dt: datetime, window_minutes: int = 15) -> bool:
    """Check if the time is within the 11:00 AM Buenos Aires dispatch window."""
    return local_dt.hour == 11 and local_dt.minute < window_minutes


def try_get_generation_cycle(today: date) -> NurturingCycleSlot | None:
    """Check if today is a generation day (Friday before send)."""
    for cycle_num in (1, 2):
        try:
            slot = get_cycle_slot(today.year, today.month, cycle_num)
            if today == slot.generation_date:
                return slot
        except ValueError:
            continue
    return None


def try_get_send_cycle(today: date) -> NurturingCycleSlot | None:
    """Check if today is a send day (the Wednesday)."""
    for cycle_num in (1, 2):
        try:
            slot = get_cycle_slot(today.year, today.month, cycle_num)
            if today == slot.send_date:
                return slot
        except ValueError:
            continue
    return None


def try_get_validation_cycle(today: date) -> NurturingCycleSlot | None:
    """Check if today is within a validation window (generation date through send date)."""
    for cycle_num in (1, 2):
        try:
            slot = get_cycle_slot(today.year, today.month, cycle_num)
            if slot.generation_date <= today <= slot.send_date and is_business_day(today):
                return slot
        except ValueError:
            continue
    return None


def get_upcoming_cycles(today: date, count: int = 4) -> list[NurturingCycleSlot]:
    """Get upcoming newsletter cycles."""
    cycles = []
    year, month = today.year, today.month

    while len(cycles) < count:
        for cycle_num in (1, 2):
            try:
                slot = get_cycle_slot(year, month, cycle_num)
                if slot.send_date >= today:
                    cycles.append(slot)
                    if len(cycles) >= count:
                        break
            except ValueError:
                continue

        # Move to next month
        month += 1
        if month > 12:
            month = 1
            year += 1

    return cycles


def resolve_next_cycle_for_draft(today: date) -> NurturingCycleSlot | None:
    """Resolve the next cycle that should be drafted.

    Returns the cycle that hasn't been sent yet and is closest to today.
    """
    # Check current month cycles
    for cycle_num in (1, 2):
        try:
            slot = get_cycle_slot(today.year, today.month, cycle_num)
            if slot.send_date >= today:
                return slot
        except ValueError:
            continue

    # Check next month
    next_month = today.month + 1
    next_year = today.year
    if next_month > 12:
        next_month = 1
        next_year += 1

    try:
        return get_cycle_slot(next_year, next_month, 1)
    except ValueError:
        return None


def resolve_next_pending_cycle(today: date) -> NurturingCycleSlot | None:
    """Resolve the next pending cycle (for send or validation)."""
    return resolve_next_cycle_for_draft(today)
