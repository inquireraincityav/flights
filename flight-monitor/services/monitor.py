"""Core flight monitoring service — orchestrates search, analysis, and alerts."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Type

from config import (
    CABIN_CLASS,
    DESTINATION,
    MAX_STOPS,
    MAX_TARGET_PRICE_CAD,
    MIN_TARGET_PRICE_CAD,
    ORIGIN,
    PASSENGERS,
    REQUIRE_CHECKED_BAG,
    get_date_combinations,
    get_deal_tier,
)
from database.database import (
    get_historical_low,
    get_overall_historical_low,
    get_previous_price,
    get_session,
    record_alert,
    save_flight_offer,
    save_price_history,
    save_provider_health,
    save_search_run,
)
from notifications.telegram import (
    send_daily_summary,
    send_deal_alert,
    send_historical_low_alert,
    send_price_drop_alert,
    send_scan_report,
    store_last_scan,
)
from providers.base import BaseProvider, BaggageStatus, FlightOffer
from services.baggage import evaluate_baggage, is_baggage_eligible
from services.deduplication import should_send_alert
from services.price_analysis import (
    build_trend_summary,
    detect_price_drop,
    is_historical_low,
)
from services.ranking import calculate_deal_score, rank_offers
from services.verification import verify_offer
from utils.fingerprints import make_fingerprint

logger = logging.getLogger("flight_monitor")


class FlightMonitor:
    def __init__(self):
        self.providers: Dict[str, BaseProvider] = {}
        self._running = False

    def register_provider(self, provider: BaseProvider):
        self.providers[provider.name] = provider
        logger.info("Registered provider: %s", provider.name)

    async def run_full_scan(self) -> dict:
        """Execute a complete scan across all date combinations and providers."""
        logger.info("=" * 60)
        logger.info("Starting YVR → BOM full scan")
        logger.info("=" * 60)

        combos = get_date_combinations()
        logger.info("Scanning %d date combinations across %d providers", len(combos), len(self.providers))

        all_offers: List[FlightOffer] = []
        provider_stats = {}
        scan_start = time.time()

        for provider_name, provider in self.providers.items():
            provider_offers = []
            provider_start = time.time()
            provider_error = None

            try:
                for dep_date, ret_date in combos:
                    try:
                        results = await provider.search_flights(
                            origin=ORIGIN,
                            destination=DESTINATION,
                            departure_date=dep_date,
                            return_date=ret_date,
                            passengers=PASSENGERS,
                            cabin=CABIN_CLASS,
                        )

                        for offer in results:
                            offer = evaluate_baggage(offer)
                            offer = await verify_offer(offer)
                            offer.deal_score = calculate_deal_score(offer)
                            offer.deal_tier = get_deal_tier(offer.cad_total)
                            provider_offers.append(offer)

                        # Stagger between date combinations
                        await asyncio.sleep(2)

                    except Exception as e:
                        logger.warning(
                            "Provider %s failed for %s→%s: %s",
                            provider_name, dep_date, ret_date, e,
                        )
                        continue

            except Exception as e:
                provider_error = str(e)
                logger.error("Provider %s failed entirely: %s", provider_name, e)

            elapsed_ms = int((time.time() - provider_start) * 1000)
            status = "success" if provider_offers else ("failed" if provider_error else "no_results")

            provider_stats[provider_name] = {
                "status": status,
                "results": len(provider_offers),
                "elapsed_ms": elapsed_ms,
                "error": provider_error,
            }

            # Record provider health
            with get_session() as session:
                save_provider_health(session, {
                    "provider": provider_name,
                    "checked_at": datetime.utcnow(),
                    "status": status,
                    "response_time_ms": elapsed_ms,
                    "error_message": provider_error,
                    "results_count": len(provider_offers),
                })

            all_offers.extend(provider_offers)
            logger.info(
                "%s: %d results in %dms (%s)",
                provider_name, len(provider_offers), elapsed_ms, status,
            )

            # Stagger between providers
            await asyncio.sleep(3)

        # Process results
        eligible = [o for o in all_offers if self._is_eligible(o)]
        logger.info(
            "Total: %d offers, %d eligible (baggage-inclusive, within stops)",
            len(all_offers), len(eligible),
        )

        # Save to database and check for alerts
        await self._save_and_alert(eligible)

        scan_elapsed = time.time() - scan_start
        logger.info("Full scan completed in %.1f seconds", scan_elapsed)

        # Build top offers sorted by price for scan report
        top_sorted = sorted(eligible, key=lambda o: o.cad_total)[:5]
        top_offers = []
        for o in top_sorted:
            top_offers.append({
                "cad_total": o.cad_total,
                "airline": o.airline,
                "departure_date": o.departure_date,
                "return_date": o.return_date,
                "outbound_stops": o.outbound.stops if o.outbound else 0,
                "baggage_status": o.baggage_status,
                "deal_score": o.deal_score or 0,
            })

        result = {
            "total_offers": len(all_offers),
            "eligible_offers": len(eligible),
            "providers": provider_stats,
            "elapsed_seconds": round(scan_elapsed, 1),
            "top_offers": top_offers,
        }

        # Store for /status command and send scan report to Telegram
        store_last_scan(result)
        try:
            await send_scan_report(result)
        except Exception as e:
            logger.warning("Failed to send scan report: %s", e)

        return result

    def _is_eligible(self, offer: FlightOffer) -> bool:
        """Check if an offer meets basic eligibility criteria."""
        if REQUIRE_CHECKED_BAG and not is_baggage_eligible(offer):
            return False

        max_stops = MAX_STOPS
        out_stops = offer.outbound.stops if offer.outbound else 0
        ret_stops = offer.inbound.stops if offer.inbound else 0
        if out_stops > max_stops or ret_stops > max_stops:
            return False

        if offer.cad_total <= 0:
            return False

        return True

    async def _save_and_alert(self, offers: List[FlightOffer]):
        """Save eligible offers to DB and trigger alerts as needed."""
        with get_session() as session:
            for offer in offers:
                fingerprint = make_fingerprint(
                    airline=offer.airline,
                    flight_numbers=offer.flight_numbers,
                    departure_date=offer.departure_date,
                    return_date=offer.return_date,
                    origin=offer.origin,
                    destination=offer.destination,
                    source=offer.provider,
                    fare_class=offer.fare_class,
                    baggage_status=offer.baggage_status,
                )

                search_run = save_search_run(session, {
                    "started_at": datetime.utcnow(),
                    "completed_at": datetime.utcnow(),
                    "origin": offer.origin,
                    "destination": offer.destination,
                    "departure_date": offer.departure_date,
                    "return_date": offer.return_date,
                    "passengers": offer.passengers,
                    "cabin_class": offer.cabin_class,
                    "provider": offer.provider,
                    "status": "success",
                    "results_count": 1,
                })

                db_dict = offer.to_db_dict(search_run.id, fingerprint)
                save_flight_offer(session, db_dict)

                save_price_history(session, {
                    "recorded_at": datetime.utcnow(),
                    "departure_date": offer.departure_date,
                    "return_date": offer.return_date,
                    "provider": offer.provider,
                    "airline": offer.airline,
                    "lowest_price_cad": offer.cad_total,
                    "is_baggage_inclusive": is_baggage_eligible(offer),
                    "is_airline_direct": offer.is_airline_direct,
                    "flight_fingerprint": fingerprint,
                    "stops": (offer.outbound.stops if offer.outbound else 0),
                    "verification_level": offer.verification_level,
                })

                # Check for alerts
                await self._check_alerts(offer, fingerprint, session)

    async def _check_alerts(self, offer: FlightOffer, fingerprint: str, session):
        """Check if this offer should trigger any alerts."""
        price = offer.cad_total
        tier = get_deal_tier(price)

        offer_dict = offer.to_db_dict(0, fingerprint)
        offer_dict["provider"] = offer.provider
        offer_dict["outbound_stops"] = offer.outbound.stops if offer.outbound else 0
        offer_dict["return_stops"] = offer.inbound.stops if offer.inbound else 0
        offer_dict["outbound_duration_minutes"] = offer.outbound.total_duration_minutes if offer.outbound else None
        offer_dict["return_duration_minutes"] = offer.inbound.total_duration_minutes if offer.inbound else None
        offer_dict["deal_score"] = offer.deal_score

        hist_low = get_historical_low(session, offer.departure_date, offer.return_date)
        prev_price = get_previous_price(session, offer.departure_date, offer.return_date)

        # Target-price alert
        if tier in ("INSANE", "EXCELLENT", "GREAT", "GOOD"):
            if offer.verification_level in ("VERIFIED", "LIKELY"):
                if should_send_alert(
                    fingerprint=fingerprint,
                    price_cad=price,
                    deal_tier=tier,
                    alert_type="TARGET_PRICE",
                    previous_price=prev_price,
                    is_historical_low=(price < hist_low if hist_low else True),
                ):
                    msg_id = await send_deal_alert(offer_dict, hist_low, prev_price)
                    record_alert(session, {
                        "alert_type": "INSANE_DEAL" if tier == "INSANE" else "TARGET_PRICE",
                        "fingerprint": fingerprint,
                        "price_cad": price,
                        "deal_tier": tier,
                        "departure_date": offer.departure_date,
                        "return_date": offer.return_date,
                        "airline": offer.airline,
                        "provider": offer.provider,
                        "message_id": msg_id,
                        "telegram_success": msg_id is not None,
                    })
                    logger.info(
                        "%s %s DEAL: $%.0f %s %s→%s",
                        get_deal_tier(price), "🔥" if tier == "INSANE" else "✓",
                        price, offer.airline, offer.departure_date, offer.return_date,
                    )

        # Price-drop alert
        drop_info = detect_price_drop(offer.departure_date, offer.return_date, price)
        if drop_info:
            msg_id = await send_price_drop_alert(
                offer_dict, drop_info["old_price"], drop_info["new_price"]
            )
            if msg_id:
                record_alert(session, {
                    "alert_type": "PRICE_DROP",
                    "fingerprint": fingerprint,
                    "price_cad": price,
                    "deal_tier": tier,
                    "departure_date": offer.departure_date,
                    "return_date": offer.return_date,
                    "airline": offer.airline,
                    "provider": offer.provider,
                    "message_id": msg_id,
                    "telegram_success": True,
                })

        # Historical low alert
        is_low, prev_low = is_historical_low(
            offer.departure_date, offer.return_date, price
        )
        if is_low and prev_low is not None:
            msg_id = await send_historical_low_alert(offer_dict, prev_low, price)
            if msg_id:
                record_alert(session, {
                    "alert_type": "HISTORICAL_LOW",
                    "fingerprint": fingerprint,
                    "price_cad": price,
                    "deal_tier": tier,
                    "departure_date": offer.departure_date,
                    "return_date": offer.return_date,
                    "airline": offer.airline,
                    "provider": offer.provider,
                    "message_id": msg_id,
                    "telegram_success": True,
                })

    async def generate_daily_summary(self) -> Optional[dict]:
        """Build and send the daily summary report."""
        with get_session() as session:
            from sqlalchemy import func
            from database.models import FlightOffer as FOModel, PriceHistory

            # Today's cheapest
            today_offers = (
                session.query(FOModel)
                .filter(
                    FOModel.baggage_status.in_(["VERIFIED_INCLUDED", "VERIFIED_EXTRA_COST"]),
                )
                .order_by(FOModel.cad_total.asc())
                .limit(20)
                .all()
            )

            if not today_offers:
                logger.info("No eligible offers for daily summary")
                return None

            cheapest = today_offers[0] if today_offers else None
            direct_offers = [o for o in today_offers if o.is_airline_direct]
            best_direct = direct_offers[0] if direct_offers else None

            # By deal score
            scored = sorted(today_offers, key=lambda o: o.deal_score or 0, reverse=True)
            best_value = scored[0] if scored else None

            # Fastest
            def _dur(o):
                return (o.outbound_duration_minutes or 9999) + (o.return_duration_minutes or 9999)
            fastest = min(today_offers, key=_dur) if today_offers else None

            overall_low = get_overall_historical_low(session)

            summary = {
                "cheapest": {
                    "price": cheapest.cad_total,
                    "departure_date": cheapest.departure_date,
                    "return_date": cheapest.return_date,
                    "airline": cheapest.airline,
                    "stops": cheapest.outbound_stops,
                } if cheapest else None,
                "best_value": {
                    "price": best_value.cad_total,
                    "departure_date": best_value.departure_date,
                    "return_date": best_value.return_date,
                    "airline": best_value.airline,
                } if best_value else None,
                "best_direct": {
                    "price": best_direct.cad_total,
                    "airline": best_direct.airline,
                } if best_direct else None,
                "fastest": {
                    "price": fastest.cad_total,
                    "airline": fastest.airline,
                    "duration": _dur(fastest),
                } if fastest else None,
                "stats": {
                    "today_low": cheapest.cad_total if cheapest else None,
                    "historical_low": overall_low,
                    "combinations_checked": 15,
                    "providers_attempted": len(self.providers),
                    "eligible_itineraries": len(today_offers),
                },
                "top_options": [
                    {
                        "price": o.cad_total,
                        "departure_date": o.departure_date,
                        "return_date": o.return_date,
                        "airline": o.airline,
                    }
                    for o in today_offers[:5]
                ],
            }

            await send_daily_summary(summary)
            return summary

    async def close_all(self):
        for name, provider in self.providers.items():
            try:
                await provider.close()
            except Exception as e:
                logger.warning("Error closing provider %s: %s", name, e)
