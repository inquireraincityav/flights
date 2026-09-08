"""Currency conversion with caching."""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional, Tuple

import httpx

from config import CURRENCY_API_URL

logger = logging.getLogger("flight_monitor")

_cache: Dict[str, float] = {}
_cache_timestamp: float = 0
_CACHE_TTL = 3600  # 1 hour


async def get_exchange_rates() -> Dict[str, float]:
    """Fetch exchange rates with CAD as base. Returns {currency: rate_from_cad}."""
    global _cache, _cache_timestamp

    if _cache and (time.time() - _cache_timestamp) < _CACHE_TTL:
        return _cache

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(CURRENCY_API_URL)
            resp.raise_for_status()
            data = resp.json()
            _cache = data.get("rates", {})
            _cache["CAD"] = 1.0
            _cache_timestamp = time.time()
            logger.info("Currency rates updated (%d currencies)", len(_cache))
            return _cache
    except Exception as e:
        logger.warning("Currency API error: %s — using cached/defaults", e)
        if _cache:
            return _cache
        return {"CAD": 1.0, "USD": 1.36, "INR": 0.016, "GBP": 1.72, "HKD": 0.17, "EUR": 1.50}


async def convert_to_cad(
    amount: float, currency: str
) -> Tuple[float, float, str]:
    """Convert an amount to CAD.

    Returns (cad_amount, exchange_rate, source).
    """
    currency = currency.upper()
    if currency == "CAD":
        return amount, 1.0, "identity"

    rates = await get_exchange_rates()

    if currency in rates:
        rate_from_cad = rates[currency]
        cad_amount = amount / rate_from_cad
        return round(cad_amount, 2), round(1.0 / rate_from_cad, 6), "exchangerate-api"

    logger.warning("Unknown currency %s — returning original amount", currency)
    return amount, 1.0, "unknown"
