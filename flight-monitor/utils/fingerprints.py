"""Itinerary fingerprinting for deduplication."""

from __future__ import annotations

import hashlib
from typing import Optional


def make_fingerprint(
    airline: str,
    flight_numbers: str,
    departure_date: str,
    return_date: str,
    origin: str,
    destination: str,
    source: str,
    fare_class: Optional[str] = None,
    baggage_status: Optional[str] = None,
) -> str:
    """Create a stable fingerprint for an itinerary."""
    parts = [
        (airline or "").upper().strip(),
        (flight_numbers or "").upper().strip(),
        departure_date,
        return_date,
        origin.upper(),
        destination.upper(),
        (source or "").lower().strip(),
        (fare_class or "").upper().strip(),
        (baggage_status or "").upper().strip(),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
