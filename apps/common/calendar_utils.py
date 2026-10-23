"""Small helpers that build month grids of tasks for the calendar widgets."""
import calendar
from collections import defaultdict
from datetime import date

from django.utils import timezone


def parse_month(value):
    """'2026-10' -> date(2026, 10, 1). Falls back to the current month."""
    today = timezone.localdate()
    try:
        year, month = (int(x) for x in str(value).split("-")[:2])
        return date(year, month, 1)
    except (ValueError, TypeError):
        return today.replace(day=1)


def shift_month(first_day, delta):
    month_index = first_day.year * 12 + (first_day.month - 1) + delta
    return date(month_index // 12, month_index % 12 + 1, 1)


def month_grid(first_day, tasks_qs):
    """
    Returns (weeks, prev_month, next_month).
    weeks -> list of 7-day rows; each cell is a dict with the date, whether it
    belongs to the displayed month, whether it's today and the tasks due that day.
    """
    weeks_dates = calendar.Calendar(firstweekday=0).monthdatescalendar(
        first_day.year, first_day.month
    )
    start, end = weeks_dates[0][0], weeks_dates[-1][-1]

    by_day = defaultdict(list)
    for task in tasks_qs.filter(
        deadline__date__gte=start, deadline__date__lte=end
    ).select_related("project", "assigned_to"):
        by_day[timezone.localtime(task.deadline).date()].append(task)

    today = timezone.localdate()
    weeks = []
    for week in weeks_dates:
        weeks.append(
            [
                {
                    "date": d,
                    "in_month": d.month == first_day.month,
                    "is_today": d == today,
                    "tasks": by_day.get(d, []),
                }
                for d in week
            ]
        )
    return weeks, shift_month(first_day, -1), shift_month(first_day, 1)
