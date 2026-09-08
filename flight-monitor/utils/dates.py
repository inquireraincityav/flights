"""Date generation and formatting utilities."""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Tuple


def generate_date_range(start: date, end: date) -> List[date]:
    """Generate inclusive date range."""
    dates = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def generate_date_combinations(
    dep_start: date,
    dep_end: date,
    ret_start: date,
    ret_end: date,
) -> List[Tuple[date, date]]:
    """Generate all departure/return combinations."""
    departures = generate_date_range(dep_start, dep_end)
    returns = generate_date_range(ret_start, ret_end)
    return [(d, r) for d in departures for r in returns]


def format_date_short(d: date) -> str:
    return d.strftime("%b %d")


def format_date_full(d: date) -> str:
    return d.strftime("%B %d, %Y")


def format_duration(minutes: int) -> str:
    if minutes is None:
        return "N/A"
    h, m = divmod(minutes, 60)
    return f"{h}h {m:02d}m"
