"""Base provider interface for flight search."""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class BaggageStatus(str, Enum):
    VERIFIED_INCLUDED = "VERIFIED_INCLUDED"
    VERIFIED_EXTRA_COST = "VERIFIED_EXTRA_COST"
    NOT_INCLUDED = "NOT_INCLUDED"
    UNKNOWN = "UNKNOWN"


class VerificationLevel(str, Enum):
    VERIFIED = "VERIFIED"
    LIKELY = "LIKELY"
    UNVERIFIED = "UNVERIFIED"


@dataclass
class FlightSegment:
    departure_airport: str = ""
    arrival_airport: str = ""
    departure_time: str = ""
    arrival_time: str = ""
    airline: str = ""
    flight_number: str = ""
    operating_airline: str = ""
    aircraft: str = ""
    duration_minutes: int = 0


@dataclass
class FlightLeg:
    segments: List[FlightSegment] = field(default_factory=list)
    departure_time: str = ""
    arrival_time: str = ""
    total_duration_minutes: int = 0
    stops: int = 0
    layover_airports: List[str] = field(default_factory=list)
    layover_durations: List[int] = field(default_factory=list)
    self_transfer: bool = False
    airport_change: bool = False
    overnight_layover: bool = False


@dataclass
class FlightOffer:
    """Standardized flight offer returned by all providers."""

    # Identity
    provider: str = ""
    search_timestamp: Optional[datetime] = None

    # Trip
    origin: str = ""
    destination: str = ""
    departure_date: str = ""
    return_date: str = ""
    passengers: int = 1
    cabin_class: str = "economy"

    # Pricing
    base_fare: float = 0
    taxes: float = 0
    fees: float = 0
    baggage_cost: float = 0
    total_price: float = 0
    total_with_baggage: float = 0
    original_currency: str = "CAD"
    original_amount: float = 0
    exchange_rate: float = 1.0
    cad_total: float = 0

    # Airline
    airline: str = ""
    marketing_airline: str = ""
    operating_airline: str = ""
    flight_numbers: str = ""
    aircraft: str = ""
    fare_class: str = ""
    fare_brand: str = ""

    # Booking
    booking_provider: str = ""
    booking_url: str = ""
    is_airline_direct: bool = False

    # Legs
    outbound: Optional[FlightLeg] = None
    inbound: Optional[FlightLeg] = None

    # Baggage
    checked_bags_included: int = 0
    baggage_status: str = BaggageStatus.UNKNOWN.value
    baggage_weight_kg: int = 0
    baggage_dimensions: str = ""
    baggage_fare_class: str = ""
    outbound_baggage_cost: float = 0
    inbound_baggage_cost: float = 0
    baggage_info_source: str = ""
    carryon_included: bool = True

    # Policies
    refundable: Optional[bool] = None
    cancellation_info: str = ""
    change_info: str = ""
    seat_selection: str = ""

    # Transfer warnings
    self_transfer: bool = False
    single_ticket: bool = True
    airport_change: bool = False
    overnight_layover: bool = False

    # Verification
    verification_level: str = VerificationLevel.UNVERIFIED.value
    last_verified_at: Optional[datetime] = None
    source_website: str = ""

    # Scoring (set by ranking service)
    deal_score: float = 0
    deal_tier: str = ""

    def to_db_dict(self, search_run_id: int, fingerprint: str) -> dict:
        import json

        return {
            "search_run_id": search_run_id,
            "fingerprint": fingerprint,
            "origin": self.origin,
            "destination": self.destination,
            "departure_date": self.departure_date,
            "return_date": self.return_date,
            "passengers": self.passengers,
            "cabin_class": self.cabin_class,
            "base_fare": self.base_fare,
            "taxes": self.taxes,
            "fees": self.fees,
            "baggage_cost": self.baggage_cost,
            "total_price": self.total_price,
            "total_with_baggage": self.total_with_baggage,
            "original_currency": self.original_currency,
            "original_amount": self.original_amount,
            "exchange_rate": self.exchange_rate,
            "cad_total": self.cad_total,
            "airline": self.airline,
            "marketing_airline": self.marketing_airline,
            "operating_airline": self.operating_airline,
            "flight_numbers": self.flight_numbers,
            "aircraft": self.aircraft,
            "fare_class": self.fare_class,
            "fare_brand": self.fare_brand,
            "booking_provider": self.booking_provider,
            "booking_url": self.booking_url,
            "is_airline_direct": self.is_airline_direct,
            "outbound_departure_time": self.outbound.departure_time if self.outbound else "",
            "outbound_arrival_time": self.outbound.arrival_time if self.outbound else "",
            "outbound_stops": self.outbound.stops if self.outbound else 0,
            "outbound_duration_minutes": self.outbound.total_duration_minutes if self.outbound else None,
            "outbound_layover_airports": json.dumps(self.outbound.layover_airports) if self.outbound else "[]",
            "outbound_layover_durations": json.dumps(self.outbound.layover_durations) if self.outbound else "[]",
            "return_departure_time": self.inbound.departure_time if self.inbound else "",
            "return_arrival_time": self.inbound.arrival_time if self.inbound else "",
            "return_stops": self.inbound.stops if self.inbound else 0,
            "return_duration_minutes": self.inbound.total_duration_minutes if self.inbound else None,
            "return_layover_airports": json.dumps(self.inbound.layover_airports) if self.inbound else "[]",
            "return_layover_durations": json.dumps(self.inbound.layover_durations) if self.inbound else "[]",
            "self_transfer": self.self_transfer,
            "single_ticket": self.single_ticket,
            "airport_change": self.airport_change,
            "overnight_layover": self.overnight_layover,
            "checked_bags_included": self.checked_bags_included,
            "baggage_status": self.baggage_status,
            "baggage_weight_kg": self.baggage_weight_kg,
            "baggage_dimensions": self.baggage_dimensions,
            "baggage_fare_class": self.baggage_fare_class,
            "outbound_baggage_cost": self.outbound_baggage_cost,
            "inbound_baggage_cost": self.inbound_baggage_cost,
            "baggage_info_source": self.baggage_info_source,
            "carryon_included": self.carryon_included,
            "refundable": self.refundable,
            "cancellation_info": self.cancellation_info,
            "change_info": self.change_info,
            "seat_selection": self.seat_selection,
            "verification_level": self.verification_level,
            "last_verified_at": self.last_verified_at,
            "source_website": self.source_website,
            "deal_score": self.deal_score,
            "deal_tier": self.deal_tier,
        }


class BaseProvider(ABC):
    """Abstract base for all flight search providers."""

    name: str = "base"
    website: str = ""
    is_airline_direct: bool = False
    requires_browser: bool = False

    def __init__(self):
        self._last_request_time: float = 0
        self._min_request_interval: float = 2.0

    async def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

    @abstractmethod
    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: date,
        passengers: int = 1,
        cabin: str = "economy",
    ) -> List[FlightOffer]:
        """Search for flights. Must be implemented by each provider."""
        ...

    async def verify_price(self, offer: FlightOffer) -> FlightOffer:
        """Optionally verify a fare deeper in booking flow. Default: no-op."""
        return offer

    async def close(self):
        """Clean up resources (browser, sessions, etc.)."""
        pass
