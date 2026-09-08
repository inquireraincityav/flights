"""Price trend analysis and drop detection."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from database.database import (
    get_historical_low,
    get_overall_historical_low,
    get_price_trend,
    get_session,
)
from config import PRICE_DROP_ALERT_CAD

logger = logging.getLogger("flight_monitor")


def get_trend_label(current: float, seven_day: Optional[float]) -> str:
    if seven_day is None or current is None:
        return "UNKNOWN"
    diff = current - seven_day
    pct = (diff / seven_day) * 100 if seven_day > 0 else 0
    if pct < -3:
        return "FALLING"
    if pct > 3:
        return "RISING"
    return "STABLE"


def get_trend_emoji(label: str) -> str:
    return {
        "FALLING": "\U0001f4c9",
        "STABLE": "➡️",
        "RISING": "\U0001f4c8",
        "UNKNOWN": "❓",
    }.get(label, "❓")


def detect_price_drop(
    departure_date: str,
    return_date: str,
    current_price: float,
) -> Optional[dict]:
    """Detect if a meaningful price drop occurred."""
    with get_session() as session:
        trend = get_price_trend(session, departure_date, return_date)

    prev_24h = trend.get("24h_low")
    if prev_24h is None:
        return None

    drop = prev_24h - current_price
    if drop >= PRICE_DROP_ALERT_CAD:
        return {
            "old_price": prev_24h,
            "new_price": current_price,
            "drop": drop,
            "departure_date": departure_date,
            "return_date": return_date,
        }
    return None


def is_historical_low(
    departure_date: str,
    return_date: str,
    current_price: float,
) -> tuple[bool, Optional[float]]:
    """Check if current price is a new historical low."""
    with get_session() as session:
        hist_low = get_historical_low(session, departure_date, return_date)

    if hist_low is None:
        return True, None
    if current_price < hist_low:
        return True, hist_low
    return False, hist_low


def build_trend_summary(departure_date: str, return_date: str) -> dict:
    with get_session() as session:
        trend = get_price_trend(session, departure_date, return_date)

    current = trend.get("current")
    seven_day = trend.get("7d_low")
    label = get_trend_label(current, seven_day)

    return {
        "current": current,
        "24h_low": trend.get("24h_low"),
        "3d_low": trend.get("3d_low"),
        "7d_low": seven_day,
        "historical_low": trend.get("historical_low"),
        "trend": label,
        "trend_emoji": get_trend_emoji(label),
        "7d_change": round(current - seven_day, 2) if current and seven_day else None,
    }
