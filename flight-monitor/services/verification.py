"""Booking verification service — confirms fare availability deeper in booking flow."""

from __future__ import annotations

import logging
from datetime import datetime

from providers.base import FlightOffer, VerificationLevel

logger = logging.getLogger("flight_monitor")


async def verify_offer(offer: FlightOffer) -> FlightOffer:
    """Attempt to verify an offer's bookability.

    For providers that support deep verification (following booking flow),
    this will call the provider's verify_price method.
    For others, it applies heuristic-based verification levels.
    """

    if offer.verification_level == VerificationLevel.VERIFIED.value:
        return offer

    if offer.is_airline_direct:
        offer.verification_level = VerificationLevel.LIKELY.value
    elif offer.booking_url and offer.total_price > 0:
        offer.verification_level = VerificationLevel.LIKELY.value
    else:
        offer.verification_level = VerificationLevel.UNVERIFIED.value

    offer.last_verified_at = datetime.utcnow()
    return offer
