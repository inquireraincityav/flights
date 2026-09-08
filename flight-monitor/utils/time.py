"""Timezone-aware time helpers."""

from __future__ import annotations

from datetime import datetime

from config import TZ, TIMEZONE_NAME


def now_local() -> datetime:
    return datetime.now(TZ)


def now_utc() -> datetime:
    return datetime.utcnow()


def format_local(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ).strftime("%B %d, %Y — %I:%M %p") + f" {TIMEZONE_NAME}"


def format_local_short(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ).strftime("%I:%M %p")
