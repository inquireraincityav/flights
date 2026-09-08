"""Comprehensive tests for flight monitor core functionality."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# --- Date Generation ---

class TestDateGeneration:
    def test_date_range(self):
        from utils.dates import generate_date_range
        dates = generate_date_range(date(2026, 12, 11), date(2026, 12, 15))
        assert len(dates) == 5
        assert dates[0] == date(2026, 12, 11)
        assert dates[-1] == date(2026, 12, 15)

    def test_date_combinations(self):
        from utils.dates import generate_date_combinations
        combos = generate_date_combinations(
            date(2026, 12, 11), date(2026, 12, 15),
            date(2027, 1, 3), date(2027, 1, 5),
        )
        assert len(combos) == 15
        assert combos[0] == (date(2026, 12, 11), date(2027, 1, 3))
        assert combos[-1] == (date(2026, 12, 15), date(2027, 1, 5))

    def test_exactly_15_combinations(self):
        from config import get_date_combinations
        combos = get_date_combinations()
        assert len(combos) == 15

    def test_all_departure_dates_present(self):
        from config import get_date_combinations
        combos = get_date_combinations()
        dep_dates = {c[0] for c in combos}
        assert date(2026, 12, 11) in dep_dates
        assert date(2026, 12, 12) in dep_dates
        assert date(2026, 12, 13) in dep_dates
        assert date(2026, 12, 14) in dep_dates
        assert date(2026, 12, 15) in dep_dates

    def test_all_return_dates_present(self):
        from config import get_date_combinations
        combos = get_date_combinations()
        ret_dates = {c[1] for c in combos}
        assert date(2027, 1, 3) in ret_dates
        assert date(2027, 1, 4) in ret_dates
        assert date(2027, 1, 5) in ret_dates

    def test_format_duration(self):
        from utils.dates import format_duration
        assert format_duration(90) == "1h 30m"
        assert format_duration(60) == "1h 00m"
        assert format_duration(0) == "0h 00m"
        assert format_duration(None) == "N/A"


# --- Price Range & Deal Tiers ---

class TestDealTiers:
    def test_insane_deal(self):
        from config import get_deal_tier
        assert get_deal_tier(1700) == "INSANE"
        assert get_deal_tier(1799) == "INSANE"
        assert get_deal_tier(0) == "INSANE"

    def test_excellent_deal(self):
        from config import get_deal_tier
        assert get_deal_tier(1800) == "EXCELLENT"
        assert get_deal_tier(2000) == "EXCELLENT"
        assert get_deal_tier(2099) == "EXCELLENT"

    def test_great_deal(self):
        from config import get_deal_tier
        assert get_deal_tier(2100) == "GREAT"
        assert get_deal_tier(2200) == "GREAT"
        assert get_deal_tier(2299) == "GREAT"

    def test_good_deal(self):
        from config import get_deal_tier
        assert get_deal_tier(2300) == "GOOD"
        assert get_deal_tier(2500) == "GOOD"
        assert get_deal_tier(2600) == "GOOD"

    def test_above_target(self):
        from config import get_deal_tier
        assert get_deal_tier(2601) == "ABOVE_TARGET"
        assert get_deal_tier(3000) == "ABOVE_TARGET"

    def test_under_1800_always_insane(self):
        """Anything below $1,800 must be INSANE — never ignored."""
        from config import get_deal_tier
        for price in [500, 1000, 1500, 1799]:
            assert get_deal_tier(price) == "INSANE", f"${price} should be INSANE"

    def test_deal_emoji(self):
        from config import get_deal_emoji
        assert "🔥" in get_deal_emoji("INSANE")
        assert get_deal_emoji("EXCELLENT") != ""
        assert get_deal_emoji("GREAT") != ""
        assert get_deal_emoji("GOOD") != ""


# --- Baggage Evaluation ---

class TestBaggage:
    def test_air_india_bags_included(self):
        from providers.base import FlightOffer, FlightLeg
        from services.baggage import evaluate_baggage, is_baggage_eligible

        offer = FlightOffer(
            airline="Air India",
            total_price=2000,
            total_with_baggage=2000,
            original_currency="CAD",
            cad_total=2000,
        )
        offer = evaluate_baggage(offer)
        assert offer.baggage_status == "VERIFIED_INCLUDED"
        assert offer.checked_bags_included == 2
        assert offer.baggage_weight_kg == 23
        assert offer.baggage_cost == 0
        assert is_baggage_eligible(offer) is True

    def test_air_canada_bags_extra_cost(self):
        from providers.base import FlightOffer
        from services.baggage import evaluate_baggage, is_baggage_eligible

        offer = FlightOffer(
            airline="Air Canada",
            total_price=2000,
            total_with_baggage=2000,
            original_currency="CAD",
            cad_total=2000,
        )
        offer = evaluate_baggage(offer)
        assert offer.baggage_status == "VERIFIED_EXTRA_COST"
        assert offer.baggage_cost > 0
        assert is_baggage_eligible(offer) is True

    def test_baggage_fee_added_to_total(self):
        """AC: $65/bag each way × 1 bag = $130 total."""
        from providers.base import FlightOffer
        from services.baggage import evaluate_baggage

        offer = FlightOffer(
            airline="Air Canada",
            total_price=1850,
            total_with_baggage=1850,
            original_currency="CAD",
            cad_total=1850,
            exchange_rate=1.0,
        )
        offer = evaluate_baggage(offer)
        assert offer.cad_total == 1850 + 130  # $65 × 2 legs

    def test_cathay_bags_included(self):
        from providers.base import FlightOffer
        from services.baggage import evaluate_baggage

        offer = FlightOffer(
            airline="Cathay Pacific",
            total_price=2200,
            total_with_baggage=2200,
            original_currency="CAD",
            cad_total=2200,
        )
        offer = evaluate_baggage(offer)
        assert offer.baggage_status == "VERIFIED_INCLUDED"
        assert offer.checked_bags_included == 1
        assert offer.baggage_cost == 0

    def test_unknown_airline_baggage(self):
        from providers.base import FlightOffer
        from services.baggage import evaluate_baggage, is_baggage_eligible

        offer = FlightOffer(
            airline="SomeUnknownAir",
            total_price=2000,
            total_with_baggage=2000,
            original_currency="CAD",
            cad_total=2000,
        )
        offer = evaluate_baggage(offer)
        assert offer.baggage_status == "UNKNOWN"
        assert is_baggage_eligible(offer) is False


# --- Fingerprinting ---

class TestFingerprinting:
    def test_same_inputs_same_hash(self):
        from utils.fingerprints import make_fingerprint
        fp1 = make_fingerprint("Air India", "AI123", "2026-12-11", "2027-01-03", "YVR", "BOM", "google")
        fp2 = make_fingerprint("Air India", "AI123", "2026-12-11", "2027-01-03", "YVR", "BOM", "google")
        assert fp1 == fp2

    def test_different_airline_different_hash(self):
        from utils.fingerprints import make_fingerprint
        fp1 = make_fingerprint("Air India", "AI123", "2026-12-11", "2027-01-03", "YVR", "BOM", "google")
        fp2 = make_fingerprint("Air Canada", "AC456", "2026-12-11", "2027-01-03", "YVR", "BOM", "google")
        assert fp1 != fp2

    def test_different_source_different_hash(self):
        from utils.fingerprints import make_fingerprint
        fp1 = make_fingerprint("Air India", "AI123", "2026-12-11", "2027-01-03", "YVR", "BOM", "google")
        fp2 = make_fingerprint("Air India", "AI123", "2026-12-11", "2027-01-03", "YVR", "BOM", "skyscanner")
        assert fp1 != fp2

    def test_case_insensitive(self):
        from utils.fingerprints import make_fingerprint
        fp1 = make_fingerprint("air india", "ai123", "2026-12-11", "2027-01-03", "yvr", "bom", "Google")
        fp2 = make_fingerprint("AIR INDIA", "AI123", "2026-12-11", "2027-01-03", "YVR", "BOM", "google")
        assert fp1 == fp2


# --- Deal Scoring ---

class TestDealScoring:
    def test_score_range(self):
        from providers.base import FlightOffer, FlightLeg
        from services.ranking import calculate_deal_score

        offer = FlightOffer(
            cad_total=2000,
            is_airline_direct=True,
            baggage_status="VERIFIED_INCLUDED",
            verification_level="VERIFIED",
            outbound=FlightLeg(stops=1, total_duration_minutes=1000),
            inbound=FlightLeg(stops=1, total_duration_minutes=1000),
        )
        score = calculate_deal_score(offer)
        assert 0 <= score <= 100

    def test_cheaper_scores_higher(self):
        from providers.base import FlightOffer, FlightLeg
        from services.ranking import calculate_deal_score

        cheap = FlightOffer(
            cad_total=1800,
            outbound=FlightLeg(stops=1, total_duration_minutes=1000),
            inbound=FlightLeg(stops=1, total_duration_minutes=1000),
            baggage_status="VERIFIED_INCLUDED",
        )
        expensive = FlightOffer(
            cad_total=2500,
            outbound=FlightLeg(stops=1, total_duration_minutes=1000),
            inbound=FlightLeg(stops=1, total_duration_minutes=1000),
            baggage_status="VERIFIED_INCLUDED",
        )
        assert calculate_deal_score(cheap) > calculate_deal_score(expensive)

    def test_direct_booking_bonus(self):
        from providers.base import FlightOffer, FlightLeg
        from services.ranking import calculate_deal_score

        direct = FlightOffer(
            cad_total=2100, is_airline_direct=True,
            outbound=FlightLeg(stops=1), inbound=FlightLeg(stops=1),
            baggage_status="VERIFIED_INCLUDED",
        )
        ota = FlightOffer(
            cad_total=2100, is_airline_direct=False,
            outbound=FlightLeg(stops=1), inbound=FlightLeg(stops=1),
            baggage_status="VERIFIED_INCLUDED",
        )
        assert calculate_deal_score(direct) > calculate_deal_score(ota)

    def test_self_transfer_penalty(self):
        from providers.base import FlightOffer, FlightLeg
        from services.ranking import calculate_deal_score

        normal = FlightOffer(
            cad_total=2100, self_transfer=False, single_ticket=True,
            outbound=FlightLeg(stops=1), inbound=FlightLeg(stops=1),
        )
        self_xfer = FlightOffer(
            cad_total=2100, self_transfer=True, single_ticket=False,
            outbound=FlightLeg(stops=1), inbound=FlightLeg(stops=1),
        )
        assert calculate_deal_score(normal) > calculate_deal_score(self_xfer)

    def test_airport_change_penalty(self):
        from providers.base import FlightOffer, FlightLeg
        from services.ranking import calculate_deal_score

        normal = FlightOffer(
            cad_total=2100, airport_change=False,
            outbound=FlightLeg(stops=1), inbound=FlightLeg(stops=1),
        )
        change = FlightOffer(
            cad_total=2100, airport_change=True,
            outbound=FlightLeg(stops=1), inbound=FlightLeg(stops=1),
        )
        assert calculate_deal_score(normal) > calculate_deal_score(change)

    def test_nonstop_scores_higher(self):
        from providers.base import FlightOffer, FlightLeg
        from services.ranking import calculate_deal_score

        nonstop = FlightOffer(
            cad_total=2200,
            outbound=FlightLeg(stops=0, total_duration_minutes=900),
            inbound=FlightLeg(stops=0, total_duration_minutes=900),
        )
        two_stop = FlightOffer(
            cad_total=2200,
            outbound=FlightLeg(stops=2, total_duration_minutes=1800),
            inbound=FlightLeg(stops=2, total_duration_minutes=1800),
        )
        assert calculate_deal_score(nonstop) > calculate_deal_score(two_stop)

    def test_verified_scores_higher(self):
        from providers.base import FlightOffer, FlightLeg
        from services.ranking import calculate_deal_score

        verified = FlightOffer(
            cad_total=2100, verification_level="VERIFIED",
            outbound=FlightLeg(stops=1), inbound=FlightLeg(stops=1),
        )
        unverified = FlightOffer(
            cad_total=2100, verification_level="UNVERIFIED",
            outbound=FlightLeg(stops=1), inbound=FlightLeg(stops=1),
        )
        assert calculate_deal_score(verified) > calculate_deal_score(unverified)


# --- Ranking ---

class TestRanking:
    def test_rank_offers_categories(self):
        from providers.base import FlightOffer, FlightLeg
        from services.ranking import rank_offers

        offers = [
            FlightOffer(
                cad_total=2000, airline="Air India", is_airline_direct=True,
                outbound=FlightLeg(stops=1, total_duration_minutes=1200),
                inbound=FlightLeg(stops=1, total_duration_minutes=1200),
                baggage_status="VERIFIED_INCLUDED",
            ),
            FlightOffer(
                cad_total=1900, airline="Cathay Pacific", is_airline_direct=False,
                outbound=FlightLeg(stops=1, total_duration_minutes=1400),
                inbound=FlightLeg(stops=1, total_duration_minutes=1400),
                baggage_status="VERIFIED_INCLUDED",
            ),
            FlightOffer(
                cad_total=2400, airline="Air Canada", is_airline_direct=True,
                outbound=FlightLeg(stops=0, total_duration_minutes=900),
                inbound=FlightLeg(stops=0, total_duration_minutes=900),
                baggage_status="VERIFIED_EXTRA_COST",
            ),
        ]

        result = rank_offers(offers)
        assert result["cheapest"].cad_total == 1900
        assert result["best_direct"] is not None
        assert result["fastest"] is not None
        assert result["best_value"] is not None


# --- Price Analysis ---

class TestPriceAnalysis:
    def test_trend_label_falling(self):
        from services.price_analysis import get_trend_label
        assert get_trend_label(2000, 2200) == "FALLING"

    def test_trend_label_rising(self):
        from services.price_analysis import get_trend_label
        assert get_trend_label(2200, 2000) == "RISING"

    def test_trend_label_stable(self):
        from services.price_analysis import get_trend_label
        assert get_trend_label(2000, 2000) == "STABLE"

    def test_trend_label_unknown(self):
        from services.price_analysis import get_trend_label
        assert get_trend_label(2000, None) == "UNKNOWN"


# --- Currency ---

class TestCurrency:
    @pytest.mark.asyncio
    async def test_cad_identity(self):
        from services.currency import convert_to_cad
        amount, rate, source = await convert_to_cad(1000, "CAD")
        assert amount == 1000
        assert rate == 1.0


# --- Telegram Formatting ---

class TestTelegramFormatting:
    def test_deal_alert_builds(self):
        from notifications.telegram import _build_deal_alert
        offer = {
            "cad_total": 1987,
            "airline": "Cathay Pacific",
            "departure_date": "2026-12-13",
            "return_date": "2027-01-04",
            "verification_level": "VERIFIED",
            "checked_bags_included": 1,
            "baggage_weight_kg": 23,
            "baggage_status": "VERIFIED_INCLUDED",
            "outbound_stops": 1,
            "return_stops": 1,
            "outbound_duration_minutes": 1175,
            "return_duration_minutes": 1130,
            "booking_provider": "Cathay Pacific",
            "booking_url": "https://www.cathaypacific.com",
            "deal_score": 94,
            "origin": "YVR",
            "destination": "BOM",
            "total_price": 1987,
            "original_currency": "CAD",
            "fare_brand": "Economy Standard",
        }
        text = _build_deal_alert(offer, 1950, 2143)
        assert "$1,987 CAD" in text
        assert "Cathay Pacific" in text
        assert "VERIFIED" in text
        assert "EXCELLENT" in text

    def test_insane_deal_headline(self):
        from notifications.telegram import _build_deal_alert
        offer = {
            "cad_total": 1700,
            "airline": "Test Air",
            "departure_date": "2026-12-13",
            "return_date": "2027-01-04",
            "verification_level": "LIKELY",
            "baggage_status": "VERIFIED_INCLUDED",
            "checked_bags_included": 1,
            "outbound_stops": 1,
            "return_stops": 1,
            "booking_provider": "Test",
            "origin": "YVR",
            "destination": "BOM",
            "total_price": 1700,
            "original_currency": "CAD",
        }
        text = _build_deal_alert(offer, None, None)
        assert "INSANE" in text


# --- Provider Base ---

class TestProviderBase:
    def test_flight_offer_to_db_dict(self):
        from providers.base import FlightOffer, FlightLeg
        offer = FlightOffer(
            provider="test",
            origin="YVR",
            destination="BOM",
            departure_date="2026-12-11",
            return_date="2027-01-03",
            cad_total=2000,
            airline="Test Air",
            outbound=FlightLeg(stops=1, layover_airports=["HKG"]),
            inbound=FlightLeg(stops=1),
        )
        d = offer.to_db_dict(1, "abc123")
        assert d["search_run_id"] == 1
        assert d["fingerprint"] == "abc123"
        assert d["origin"] == "YVR"
        assert d["cad_total"] == 2000
        assert d["outbound_stops"] == 1


# --- Database ---

class TestDatabase:
    def test_init_db(self):
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            with patch("config.DB_PATH", db_path):
                from database.models import Base
                from sqlalchemy import create_engine
                engine = create_engine(f"sqlite:///{db_path}")
                Base.metadata.create_all(engine)
                assert os.path.exists(db_path)


# --- Alert Cooldown ---

class TestAlertCooldown:
    def test_first_alert_always_sent(self):
        with patch("services.deduplication.get_session") as mock_ctx:
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from services.deduplication import should_send_alert
            result = should_send_alert(
                fingerprint="abc123",
                price_cad=2000,
                deal_tier="EXCELLENT",
            )
            assert result is True

    def test_insane_deal_bypasses_cooldown(self):
        with patch("services.deduplication.get_session") as mock_ctx:
            mock_alert = MagicMock()
            mock_alert.deal_tier = "EXCELLENT"
            mock_session = MagicMock()
            mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_alert
            mock_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

            from services.deduplication import should_send_alert
            result = should_send_alert(
                fingerprint="abc123",
                price_cad=1700,
                deal_tier="INSANE",
            )
            assert result is True


# --- Config ---

class TestConfig:
    def test_check_interval_dynamic(self):
        from config import get_check_interval_hours
        interval = get_check_interval_hours()
        assert isinstance(interval, int)
        assert interval > 0

    def test_date_combinations_count(self):
        from config import get_date_combinations
        assert len(get_date_combinations()) == 15

    def test_scoring_weights_sum_to_one(self):
        from config import (
            SCORE_WEIGHT_PRICE, SCORE_WEIGHT_STOPS, SCORE_WEIGHT_DURATION,
            SCORE_WEIGHT_BAGGAGE, SCORE_WEIGHT_DIRECT_BOOKING,
            SCORE_WEIGHT_CONFIDENCE, SCORE_WEIGHT_CONNECTION,
        )
        total = (
            SCORE_WEIGHT_PRICE + SCORE_WEIGHT_STOPS + SCORE_WEIGHT_DURATION
            + SCORE_WEIGHT_BAGGAGE + SCORE_WEIGHT_DIRECT_BOOKING
            + SCORE_WEIGHT_CONFIDENCE + SCORE_WEIGHT_CONNECTION
        )
        assert abs(total - 1.0) < 0.001

    def test_price_weight_dominant(self):
        from config import SCORE_WEIGHT_PRICE
        assert SCORE_WEIGHT_PRICE >= 0.5

    def test_max_stops_allows_indirect(self):
        from config import MAX_STOPS
        assert MAX_STOPS >= 3

    def test_prefer_cheapest_over_fastest(self):
        from config import PREFER_CHEAPEST_OVER_FASTEST
        assert PREFER_CHEAPEST_OVER_FASTEST is True


# --- Provider Registration ---

class TestProviderRegistration:
    def test_17_providers_registered(self):
        from main import create_monitor
        monitor = create_monitor()
        assert len(monitor.providers) == 17

    def test_all_provider_names(self):
        from main import create_monitor
        monitor = create_monitor()
        expected = {
            "google_flights", "skyscanner", "cheapoair",
            "kayak", "expedia", "flighthub",
            "air_canada", "air_india", "cathay_pacific",
            "emirates", "qatar_airways", "lufthansa",
            "british_airways", "turkish_airlines", "klm",
            "air_france", "singapore_airlines",
        }
        assert set(monitor.providers.keys()) == expected

    def test_airline_direct_providers(self):
        from main import create_monitor
        monitor = create_monitor()
        direct_providers = {
            name for name, p in monitor.providers.items()
            if p.is_airline_direct
        }
        expected_direct = {
            "air_canada", "air_india", "cathay_pacific",
            "emirates", "qatar_airways", "lufthansa",
            "british_airways", "turkish_airlines", "klm",
            "air_france", "singapore_airlines",
        }
        assert direct_providers == expected_direct

    def test_aggregator_providers(self):
        from main import create_monitor
        monitor = create_monitor()
        aggregators = {
            name for name, p in monitor.providers.items()
            if not p.is_airline_direct
        }
        expected_agg = {
            "google_flights", "skyscanner", "cheapoair",
            "kayak", "expedia", "flighthub",
        }
        assert aggregators == expected_agg


# --- New Airline Baggage ---

class TestNewAirlineBaggage:
    def test_emirates_bags_included(self):
        from providers.base import FlightOffer
        from services.baggage import evaluate_baggage

        offer = FlightOffer(
            airline="Emirates", total_price=2200,
            total_with_baggage=2200, original_currency="CAD", cad_total=2200,
        )
        offer = evaluate_baggage(offer)
        assert offer.baggage_status == "VERIFIED_INCLUDED"
        assert offer.checked_bags_included == 1
        assert offer.baggage_weight_kg == 30

    def test_qatar_bags_included(self):
        from providers.base import FlightOffer
        from services.baggage import evaluate_baggage

        offer = FlightOffer(
            airline="Qatar Airways", total_price=2100,
            total_with_baggage=2100, original_currency="CAD", cad_total=2100,
        )
        offer = evaluate_baggage(offer)
        assert offer.baggage_status == "VERIFIED_INCLUDED"
        assert offer.baggage_weight_kg == 30

    def test_turkish_bags_included(self):
        from providers.base import FlightOffer
        from services.baggage import evaluate_baggage

        offer = FlightOffer(
            airline="Turkish Airlines", total_price=2000,
            total_with_baggage=2000, original_currency="CAD", cad_total=2000,
        )
        offer = evaluate_baggage(offer)
        assert offer.baggage_status == "VERIFIED_INCLUDED"
        assert offer.baggage_weight_kg == 30

    def test_lufthansa_bags_included(self):
        from providers.base import FlightOffer
        from services.baggage import evaluate_baggage

        offer = FlightOffer(
            airline="Lufthansa", total_price=2300,
            total_with_baggage=2300, original_currency="CAD", cad_total=2300,
        )
        offer = evaluate_baggage(offer)
        assert offer.baggage_status == "VERIFIED_INCLUDED"
        assert offer.baggage_weight_kg == 23

    def test_singapore_airlines_bags_included(self):
        from providers.base import FlightOffer
        from services.baggage import evaluate_baggage

        offer = FlightOffer(
            airline="Singapore Airlines", total_price=2400,
            total_with_baggage=2400, original_currency="CAD", cad_total=2400,
        )
        offer = evaluate_baggage(offer)
        assert offer.baggage_status == "VERIFIED_INCLUDED"
        assert offer.baggage_weight_kg == 30


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
