"""Deal scoring and ranking for flight offers."""

from __future__ import annotations

from config import (
    DIRECT_BOOKING_PREMIUM_CAD,
    MAX_PREFERRED_DURATION_HOURS,
    MAX_PREFERRED_LAYOVER_HOURS,
    MAX_STOPS,
    MAX_TARGET_PRICE_CAD,
    MIN_CONNECTION_MINUTES,
    MIN_TARGET_PRICE_CAD,
    SCORE_WEIGHT_BAGGAGE,
    SCORE_WEIGHT_CONFIDENCE,
    SCORE_WEIGHT_CONNECTION,
    SCORE_WEIGHT_DIRECT_BOOKING,
    SCORE_WEIGHT_DURATION,
    SCORE_WEIGHT_PRICE,
    SCORE_WEIGHT_STOPS,
    get_deal_tier,
)
from providers.base import FlightOffer


def calculate_deal_score(offer: FlightOffer) -> float:
    """Score from 0–100. Higher = better deal."""

    # Price score (0–100)
    price = offer.cad_total
    if price <= 0:
        price_score = 0
    elif price <= MIN_TARGET_PRICE_CAD:
        price_score = 100
    elif price <= MAX_TARGET_PRICE_CAD:
        price_score = 100 - ((price - MIN_TARGET_PRICE_CAD) / (MAX_TARGET_PRICE_CAD - MIN_TARGET_PRICE_CAD)) * 60
    else:
        price_score = max(0, 40 - ((price - MAX_TARGET_PRICE_CAD) / 500) * 40)

    # Stops score
    total_stops = (offer.outbound.stops if offer.outbound else 0) + (offer.inbound.stops if offer.inbound else 0)
    if total_stops == 0:
        stops_score = 100
    elif total_stops <= 2:
        stops_score = 80
    elif total_stops <= 4:
        stops_score = 50
    else:
        stops_score = 20

    # Duration score
    max_dur_min = MAX_PREFERRED_DURATION_HOURS * 60
    out_dur = offer.outbound.total_duration_minutes if offer.outbound else 0
    ret_dur = offer.inbound.total_duration_minutes if offer.inbound else 0
    avg_dur = ((out_dur or 0) + (ret_dur or 0)) / 2 if (out_dur or ret_dur) else 0
    if avg_dur <= 0:
        duration_score = 50
    elif avg_dur <= max_dur_min * 0.6:
        duration_score = 100
    elif avg_dur <= max_dur_min:
        duration_score = 100 - ((avg_dur - max_dur_min * 0.6) / (max_dur_min * 0.4)) * 50
    else:
        duration_score = max(0, 50 - ((avg_dur - max_dur_min) / max_dur_min) * 50)

    # Baggage score
    if offer.baggage_status == "VERIFIED_INCLUDED":
        baggage_score = 100
    elif offer.baggage_status == "VERIFIED_EXTRA_COST":
        baggage_score = 70
    elif offer.baggage_status == "NOT_INCLUDED":
        baggage_score = 20
    else:
        baggage_score = 40

    # Direct booking score
    direct_score = 100 if offer.is_airline_direct else 40

    # Confidence score
    if offer.verification_level == "VERIFIED":
        confidence_score = 100
    elif offer.verification_level == "LIKELY":
        confidence_score = 70
    else:
        confidence_score = 30

    # Connection quality score
    connection_score = 100
    if offer.self_transfer:
        connection_score -= 40
    if offer.airport_change:
        connection_score -= 30
    if offer.overnight_layover:
        connection_score -= 10
    if not offer.single_ticket:
        connection_score -= 30
    connection_score = max(0, connection_score)

    total = (
        price_score * SCORE_WEIGHT_PRICE
        + stops_score * SCORE_WEIGHT_STOPS
        + duration_score * SCORE_WEIGHT_DURATION
        + baggage_score * SCORE_WEIGHT_BAGGAGE
        + direct_score * SCORE_WEIGHT_DIRECT_BOOKING
        + confidence_score * SCORE_WEIGHT_CONFIDENCE
        + connection_score * SCORE_WEIGHT_CONNECTION
    )

    return round(min(100, max(0, total)), 1)


def rank_offers(offers: list[FlightOffer]) -> dict:
    """Return ranked categories of offers."""
    for o in offers:
        o.deal_score = calculate_deal_score(o)
        o.deal_tier = get_deal_tier(o.cad_total)

    by_price = sorted(offers, key=lambda o: o.cad_total)
    by_score = sorted(offers, key=lambda o: o.deal_score, reverse=True)
    direct_only = [o for o in offers if o.is_airline_direct]
    by_direct = sorted(direct_only, key=lambda o: o.cad_total) if direct_only else []

    def _total_dur(o: FlightOffer) -> int:
        return (o.outbound.total_duration_minutes or 9999 if o.outbound else 9999) + \
               (o.inbound.total_duration_minutes or 9999 if o.inbound else 9999)

    by_speed = sorted(offers, key=_total_dur)

    return {
        "cheapest": by_price[0] if by_price else None,
        "best_value": by_score[0] if by_score else None,
        "best_direct": by_direct[0] if by_direct else None,
        "fastest": by_speed[0] if by_speed else None,
        "all_by_price": by_price,
        "all_by_score": by_score,
    }
