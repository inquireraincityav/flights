"""SQLAlchemy models for flight price persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class SearchRun(Base):
    __tablename__ = "search_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)
    origin = Column(String(10), nullable=False)
    destination = Column(String(10), nullable=False)
    departure_date = Column(String(10), nullable=False)
    return_date = Column(String(10), nullable=False)
    passengers = Column(Integer, default=1)
    cabin_class = Column(String(20), default="economy")
    provider = Column(String(50), nullable=False)
    status = Column(String(20), default="running")  # running, success, failed
    error_message = Column(Text)
    results_count = Column(Integer, default=0)


class FlightOffer(Base):
    __tablename__ = "flight_offers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    search_run_id = Column(Integer, nullable=False)
    fingerprint = Column(String(255), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Trip
    origin = Column(String(10), nullable=False)
    destination = Column(String(10), nullable=False)
    departure_date = Column(String(10), nullable=False)
    return_date = Column(String(10), nullable=False)
    passengers = Column(Integer, default=1)
    cabin_class = Column(String(20))

    # Pricing
    base_fare = Column(Float)
    taxes = Column(Float)
    fees = Column(Float)
    baggage_cost = Column(Float, default=0)
    total_price = Column(Float, nullable=False)
    total_with_baggage = Column(Float, nullable=False)
    original_currency = Column(String(5), default="CAD")
    original_amount = Column(Float)
    exchange_rate = Column(Float, default=1.0)
    cad_total = Column(Float, nullable=False)

    # Airline
    airline = Column(String(100))
    marketing_airline = Column(String(100))
    operating_airline = Column(String(100))
    flight_numbers = Column(Text)  # JSON list
    aircraft = Column(String(100))
    fare_class = Column(String(50))
    fare_brand = Column(String(100))

    # Booking
    booking_provider = Column(String(100))
    booking_url = Column(Text)
    is_airline_direct = Column(Boolean, default=False)

    # Outbound
    outbound_departure_time = Column(String(20))
    outbound_arrival_time = Column(String(20))
    outbound_stops = Column(Integer, default=0)
    outbound_duration_minutes = Column(Integer)
    outbound_layover_airports = Column(Text)  # JSON
    outbound_layover_durations = Column(Text)  # JSON

    # Return
    return_departure_time = Column(String(20))
    return_arrival_time = Column(String(20))
    return_stops = Column(Integer, default=0)
    return_duration_minutes = Column(Integer)
    return_layover_airports = Column(Text)  # JSON
    return_layover_durations = Column(Text)  # JSON

    # Warnings
    self_transfer = Column(Boolean, default=False)
    single_ticket = Column(Boolean, default=True)
    airport_change = Column(Boolean, default=False)
    overnight_layover = Column(Boolean, default=False)

    # Baggage
    checked_bags_included = Column(Integer, default=0)
    baggage_status = Column(String(30))  # VERIFIED_INCLUDED, VERIFIED_EXTRA_COST, NOT_INCLUDED, UNKNOWN
    baggage_weight_kg = Column(Integer)
    baggage_dimensions = Column(String(50))
    baggage_fare_class = Column(String(50))
    outbound_baggage_cost = Column(Float, default=0)
    inbound_baggage_cost = Column(Float, default=0)
    baggage_info_source = Column(String(100))
    carryon_included = Column(Boolean, default=True)

    # Policies
    refundable = Column(Boolean)
    cancellation_info = Column(Text)
    change_info = Column(Text)
    seat_selection = Column(String(100))

    # Verification
    verification_level = Column(String(20), default="UNVERIFIED")  # VERIFIED, LIKELY, UNVERIFIED
    last_verified_at = Column(DateTime)
    source_website = Column(String(100))

    # Scoring
    deal_score = Column(Float)
    deal_tier = Column(String(20))


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    recorded_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    departure_date = Column(String(10), nullable=False, index=True)
    return_date = Column(String(10), nullable=False, index=True)
    provider = Column(String(50))
    airline = Column(String(100))
    lowest_price_cad = Column(Float, nullable=False)
    is_baggage_inclusive = Column(Boolean, default=False)
    is_airline_direct = Column(Boolean, default=False)
    flight_fingerprint = Column(String(255))
    stops = Column(Integer)
    verification_level = Column(String(20))


class AlertSent(Base):
    __tablename__ = "alerts_sent"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    alert_type = Column(String(30), nullable=False)  # TARGET_PRICE, PRICE_DROP, HISTORICAL_LOW, INSANE_DEAL
    fingerprint = Column(String(255), nullable=False, index=True)
    price_cad = Column(Float, nullable=False)
    deal_tier = Column(String(20))
    departure_date = Column(String(10))
    return_date = Column(String(10))
    airline = Column(String(100))
    provider = Column(String(100))
    message_id = Column(String(50))
    telegram_success = Column(Boolean, default=True)


class ProviderHealth(Base):
    __tablename__ = "provider_health"

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider = Column(String(50), nullable=False, index=True)
    checked_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(String(20), nullable=False)  # success, failed, timeout
    response_time_ms = Column(Integer)
    error_message = Column(Text)
    results_count = Column(Integer, default=0)


class FavoriteItinerary(Base):
    __tablename__ = "favorite_itineraries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    fingerprint = Column(String(255), nullable=False, unique=True)
    added_at = Column(DateTime, default=datetime.utcnow)
    airline = Column(String(100))
    departure_date = Column(String(10))
    return_date = Column(String(10))
    route = Column(String(200))
    last_price_cad = Column(Float)
    notes = Column(Text)
