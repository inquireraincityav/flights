"""Baggage evaluation and cost calculation."""

from __future__ import annotations

import logging
from typing import Optional

from config import CHECKED_BAGS_PER_PASSENGER, REQUIRE_CHECKED_BAG
from providers.base import BaggageStatus, FlightOffer

logger = logging.getLogger("flight_monitor")

# Known airline baggage policies (economy, per passenger, one-way)
AIRLINE_BAGGAGE_POLICIES = {
    "Air India": {
        "included": 2,
        "weight_kg": 23,
        "status": BaggageStatus.VERIFIED_INCLUDED,
        "source": "Air India published policy (economy to India: 2 × 23kg)",
    },
    "Air Canada": {
        "included": 0,
        "weight_kg": 23,
        "extra_cost_cad": 65,
        "status": BaggageStatus.VERIFIED_EXTRA_COST,
        "source": "Air Canada published baggage fees",
    },
    "Cathay Pacific": {
        "included": 1,
        "weight_kg": 23,
        "status": BaggageStatus.VERIFIED_INCLUDED,
        "source": "Cathay Pacific economy baggage allowance",
    },
    "Emirates": {
        "included": 1,
        "weight_kg": 30,
        "status": BaggageStatus.VERIFIED_INCLUDED,
        "source": "Emirates economy baggage allowance",
    },
    "Qatar Airways": {
        "included": 1,
        "weight_kg": 30,
        "status": BaggageStatus.VERIFIED_INCLUDED,
        "source": "Qatar Airways economy baggage allowance",
    },
    "British Airways": {
        "included": 1,
        "weight_kg": 23,
        "status": BaggageStatus.VERIFIED_INCLUDED,
        "source": "British Airways economy long-haul baggage",
    },
    "Lufthansa": {
        "included": 1,
        "weight_kg": 23,
        "status": BaggageStatus.VERIFIED_INCLUDED,
        "source": "Lufthansa economy baggage allowance",
    },
    "Singapore Airlines": {
        "included": 1,
        "weight_kg": 30,
        "status": BaggageStatus.VERIFIED_INCLUDED,
        "source": "Singapore Airlines economy baggage allowance",
    },
    "Turkish Airlines": {
        "included": 1,
        "weight_kg": 30,
        "status": BaggageStatus.VERIFIED_INCLUDED,
        "source": "Turkish Airlines economy baggage allowance",
    },
    "KLM": {
        "included": 1,
        "weight_kg": 23,
        "status": BaggageStatus.VERIFIED_INCLUDED,
        "source": "KLM economy intercontinental baggage",
    },
    "Air France": {
        "included": 1,
        "weight_kg": 23,
        "status": BaggageStatus.VERIFIED_INCLUDED,
        "source": "Air France economy long-haul baggage",
    },
    "WestJet": {
        "included": 0,
        "weight_kg": 23,
        "extra_cost_cad": 50,
        "status": BaggageStatus.VERIFIED_EXTRA_COST,
        "source": "WestJet published baggage fees",
    },
}


def evaluate_baggage(offer: FlightOffer) -> FlightOffer:
    """Evaluate baggage status and adjust pricing."""

    if offer.baggage_status in (
        BaggageStatus.VERIFIED_INCLUDED.value,
        BaggageStatus.VERIFIED_EXTRA_COST.value,
    ):
        return offer

    airline = offer.airline or offer.marketing_airline or ""
    policy = None
    for name, pol in AIRLINE_BAGGAGE_POLICIES.items():
        if name.lower() in airline.lower():
            policy = pol
            break

    if policy:
        offer.baggage_info_source = policy["source"]
        if policy["status"] == BaggageStatus.VERIFIED_INCLUDED:
            offer.checked_bags_included = policy["included"]
            offer.baggage_weight_kg = policy["weight_kg"]
            offer.baggage_status = BaggageStatus.VERIFIED_INCLUDED.value
            offer.baggage_cost = 0
            offer.outbound_baggage_cost = 0
            offer.inbound_baggage_cost = 0
        elif policy["status"] == BaggageStatus.VERIFIED_EXTRA_COST:
            extra = policy.get("extra_cost_cad", 0)
            offer.checked_bags_included = 0
            offer.baggage_weight_kg = policy["weight_kg"]
            offer.baggage_status = BaggageStatus.VERIFIED_EXTRA_COST.value
            offer.outbound_baggage_cost = extra * CHECKED_BAGS_PER_PASSENGER
            offer.inbound_baggage_cost = extra * CHECKED_BAGS_PER_PASSENGER
            offer.baggage_cost = offer.outbound_baggage_cost + offer.inbound_baggage_cost
    else:
        offer.baggage_status = BaggageStatus.UNKNOWN.value

    offer.total_with_baggage = offer.total_price + offer.baggage_cost
    offer.cad_total = offer.total_with_baggage * (1.0 / offer.exchange_rate if offer.exchange_rate and offer.exchange_rate != 0 else 1.0)
    if offer.original_currency == "CAD":
        offer.cad_total = offer.total_with_baggage

    return offer


def is_baggage_eligible(offer: FlightOffer) -> bool:
    """Check if an offer meets the checked-bag requirement."""
    if not REQUIRE_CHECKED_BAG:
        return True
    return offer.baggage_status in (
        BaggageStatus.VERIFIED_INCLUDED.value,
        BaggageStatus.VERIFIED_EXTRA_COST.value,
    )
