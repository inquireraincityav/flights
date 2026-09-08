"""Alert deduplication to prevent spamming."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from config import (
    ALERT_COOLDOWN_HOURS,
    SECONDARY_PRICE_DROP_ALERT_CAD,
)
from database.database import get_recent_alert, get_session

logger = logging.getLogger("flight_monitor")


def should_send_alert(
    fingerprint: str,
    price_cad: float,
    deal_tier: str,
    alert_type: str = "TARGET_PRICE",
    previous_price: Optional[float] = None,
    is_historical_low: bool = False,
    previous_verification: Optional[str] = None,
    current_verification: Optional[str] = None,
    is_nonstop: bool = False,
    is_direct_airline: bool = False,
) -> bool:
    """Decide whether to send a Telegram alert."""

    with get_session() as session:
        recent = get_recent_alert(session, fingerprint, ALERT_COOLDOWN_HOURS)

    if recent is None:
        return True

    # Bypass cooldown conditions
    if previous_price and (previous_price - price_cad) >= SECONDARY_PRICE_DROP_ALERT_CAD:
        logger.info("Cooldown bypass: price dropped by $%.0f", previous_price - price_cad)
        return True

    if deal_tier == "INSANE":
        logger.info("Cooldown bypass: INSANE deal tier")
        return True

    if is_historical_low:
        logger.info("Cooldown bypass: historical low")
        return True

    if is_nonstop and deal_tier in ("INSANE", "EXCELLENT", "GREAT"):
        logger.info("Cooldown bypass: nonstop fare in target range")
        return True

    if (
        previous_verification in ("UNVERIFIED", "LIKELY")
        and current_verification == "VERIFIED"
    ):
        logger.info("Cooldown bypass: verification improved")
        return True

    with get_session() as session:
        recent = get_recent_alert(session, fingerprint, ALERT_COOLDOWN_HOURS)

    if recent:
        old_tier_rank = {"INSANE": 0, "EXCELLENT": 1, "GREAT": 2, "GOOD": 3, "ABOVE_TARGET": 4}
        if old_tier_rank.get(deal_tier, 5) < old_tier_rank.get(recent.deal_tier, 5):
            logger.info("Cooldown bypass: tier improved from %s to %s", recent.deal_tier, deal_tier)
            return True

    logger.debug("Alert suppressed for %s (cooldown active)", fingerprint[:12])
    return False
