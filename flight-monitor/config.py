"""Centralized configuration loaded from environment / .env file."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Tuple
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def _bool(val: str) -> bool:
    return val.strip().lower() in ("true", "1", "yes")


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


# --- Trip ---
ORIGIN: str = os.getenv("ORIGIN", "YVR")
DESTINATION: str = os.getenv("DESTINATION", "BOM")
DEPARTURE_START: date = date.fromisoformat(os.getenv("DEPARTURE_START", "2026-12-11"))
DEPARTURE_END: date = date.fromisoformat(os.getenv("DEPARTURE_END", "2026-12-15"))
RETURN_START: date = date.fromisoformat(os.getenv("RETURN_START", "2027-01-03"))
RETURN_END: date = date.fromisoformat(os.getenv("RETURN_END", "2027-01-05"))
PASSENGERS: int = _int("PASSENGERS", 1)
CABIN_CLASS: str = os.getenv("CABIN_CLASS", "economy")

# --- Prices (CAD) ---
MIN_TARGET_PRICE_CAD: float = _float("MIN_TARGET_PRICE_CAD", 1800)
MAX_TARGET_PRICE_CAD: float = _float("MAX_TARGET_PRICE_CAD", 2600)
INSANE_DEAL_MAX_CAD: float = _float("INSANE_DEAL_MAX_CAD", 1799)
EXCELLENT_DEAL_MAX_CAD: float = _float("EXCELLENT_DEAL_MAX_CAD", 2099)
GREAT_DEAL_MAX_CAD: float = _float("GREAT_DEAL_MAX_CAD", 2299)
GOOD_DEAL_MAX_CAD: float = _float("GOOD_DEAL_MAX_CAD", 2600)

# --- Alerts ---
PRICE_DROP_ALERT_CAD: float = _float("PRICE_DROP_ALERT_CAD", 150)
SECONDARY_PRICE_DROP_ALERT_CAD: float = _float("SECONDARY_PRICE_DROP_ALERT_CAD", 50)
CHECK_INTERVAL_HOURS: int = _int("CHECK_INTERVAL_HOURS", 4)
ALERT_COOLDOWN_HOURS: int = _int("ALERT_COOLDOWN_HOURS", 24)

# --- Baggage ---
CHECKED_BAGS_PER_PASSENGER: int = _int("CHECKED_BAGS_PER_PASSENGER", 1)
REQUIRE_CHECKED_BAG: bool = _bool(os.getenv("REQUIRE_CHECKED_BAG", "true"))

# --- Itinerary ---
MAX_STOPS: int = _int("MAX_STOPS", 3)
MAX_PREFERRED_DURATION_HOURS: int = _int("MAX_PREFERRED_DURATION_HOURS", 48)
MAX_PREFERRED_LAYOVER_HOURS: int = _int("MAX_PREFERRED_LAYOVER_HOURS", 24)
MIN_CONNECTION_MINUTES: int = _int("MIN_CONNECTION_MINUTES", 60)
DIRECT_BOOKING_PREMIUM_CAD: float = _float("DIRECT_BOOKING_PREMIUM_CAD", 100)
PREFER_CHEAPEST_OVER_FASTEST: bool = _bool(os.getenv("PREFER_CHEAPEST_OVER_FASTEST", "true"))

# --- Timezone ---
TIMEZONE_NAME: str = os.getenv("TIMEZONE", "America/Vancouver")
TZ = ZoneInfo(TIMEZONE_NAME)

# --- Telegram ---
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# --- Browser ---
HEADLESS: bool = _bool(os.getenv("HEADLESS", "true"))

# --- Dashboard ---
DASHBOARD_HOST: str = os.getenv("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT: int = _int("DASHBOARD_PORT", 8080)

# --- Currency ---
CURRENCY_API_URL: str = os.getenv(
    "CURRENCY_API_URL", "https://api.exchangerate-api.com/v4/latest/CAD"
)

# --- Deal Scoring Weights ---
# Price-dominant: user prefers cheapest flights, comfortable with long layovers
SCORE_WEIGHT_PRICE: float = _float("SCORE_WEIGHT_PRICE", 0.60)
SCORE_WEIGHT_STOPS: float = _float("SCORE_WEIGHT_STOPS", 0.05)
SCORE_WEIGHT_DURATION: float = _float("SCORE_WEIGHT_DURATION", 0.02)
SCORE_WEIGHT_BAGGAGE: float = _float("SCORE_WEIGHT_BAGGAGE", 0.15)
SCORE_WEIGHT_DIRECT_BOOKING: float = _float("SCORE_WEIGHT_DIRECT_BOOKING", 0.08)
SCORE_WEIGHT_CONFIDENCE: float = _float("SCORE_WEIGHT_CONFIDENCE", 0.05)
SCORE_WEIGHT_CONNECTION: float = _float("SCORE_WEIGHT_CONNECTION", 0.05)

# --- Dynamic Intervals ---
DYNAMIC_CHECK_ENABLED: bool = _bool(os.getenv("DYNAMIC_CHECK_ENABLED", "true"))
CHECK_INTERVAL_60PLUS_DAYS: int = _int("CHECK_INTERVAL_60PLUS_DAYS", 6)
CHECK_INTERVAL_30_60_DAYS: int = _int("CHECK_INTERVAL_30_60_DAYS", 4)
CHECK_INTERVAL_14_30_DAYS: int = _int("CHECK_INTERVAL_14_30_DAYS", 2)
CHECK_INTERVAL_UNDER_14_DAYS: int = _int("CHECK_INTERVAL_UNDER_14_DAYS", 1)

# --- Daily Summary ---
DAILY_SUMMARY_HOUR: int = _int("DAILY_SUMMARY_HOUR", 20)
DAILY_SUMMARY_MINUTE: int = _int("DAILY_SUMMARY_MINUTE", 0)

# --- Paths ---
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "flights.db"
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def get_date_combinations() -> List[Tuple[date, date]]:
    """Generate all departure/return date combinations."""
    combos = []
    dep = DEPARTURE_START
    while dep <= DEPARTURE_END:
        ret = RETURN_START
        while ret <= RETURN_END:
            combos.append((dep, ret))
            ret += timedelta(days=1)
        dep += timedelta(days=1)
    return combos


def get_deal_tier(price_cad: float) -> str:
    """Return the deal tier label for a given baggage-inclusive CAD price."""
    if price_cad < MIN_TARGET_PRICE_CAD:
        return "INSANE"
    if price_cad <= EXCELLENT_DEAL_MAX_CAD:
        return "EXCELLENT"
    if price_cad <= GREAT_DEAL_MAX_CAD:
        return "GREAT"
    if price_cad <= GOOD_DEAL_MAX_CAD:
        return "GOOD"
    return "ABOVE_TARGET"


def get_deal_emoji(tier: str) -> str:
    emojis = {
        "INSANE": "\U0001f525",
        "EXCELLENT": "\U0001f7e3",
        "GREAT": "\U0001f7e2",
        "GOOD": "\U0001f535",
        "ABOVE_TARGET": "⚪",
    }
    return emojis.get(tier, "")


def get_check_interval_hours() -> int:
    """Return the appropriate check interval based on days until departure."""
    if not DYNAMIC_CHECK_ENABLED:
        return CHECK_INTERVAL_HOURS
    now = datetime.now(TZ).date()
    days_until = (DEPARTURE_START - now).days
    if days_until > 60:
        return CHECK_INTERVAL_60PLUS_DAYS
    if days_until > 30:
        return CHECK_INTERVAL_30_60_DAYS
    if days_until > 14:
        return CHECK_INTERVAL_14_30_DAYS
    return CHECK_INTERVAL_UNDER_14_DAYS
