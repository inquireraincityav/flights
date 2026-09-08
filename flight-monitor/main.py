#!/usr/bin/env python3
"""Flight Price Monitor — YVR → BOM

Main entry point for the flight price monitoring system.
Continuously monitors flight prices across multiple providers,
evaluates baggage-inclusive costs, and sends Telegram alerts.

Usage:
    python main.py                          # Start continuous monitoring
    python main.py --check-now              # Run one immediate scan
    python main.py --daily-summary          # Send daily summary now
    python main.py --test-alert             # Send test Telegram alert
    python main.py --test-provider NAME     # Test a single provider
    python main.py --dashboard              # Start web dashboard only
    python main.py --init-db                # Initialize database
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    CABIN_CLASS,
    DASHBOARD_HOST,
    DASHBOARD_PORT,
    DEPARTURE_START,
    DEPARTURE_END,
    DESTINATION,
    ORIGIN,
    PASSENGERS,
    RETURN_START,
    RETURN_END,
    get_check_interval_hours,
    get_date_combinations,
)
from database.database import init_db, get_session
from services.monitor import FlightMonitor
from utils.logging import setup_logging

logger = setup_logging()


def create_monitor() -> FlightMonitor:
    """Create and configure the flight monitor with all providers."""
    monitor = FlightMonitor()

    from providers.google_flights import GoogleFlightsProvider
    from providers.skyscanner import SkyscannerProvider
    from providers.cheapoair import CheapOairProvider
    from providers.air_canada import AirCanadaProvider
    from providers.air_india import AirIndiaProvider
    from providers.cathay_pacific import CathayPacificProvider

    monitor.register_provider(GoogleFlightsProvider())
    monitor.register_provider(SkyscannerProvider())
    monitor.register_provider(CheapOairProvider())
    monitor.register_provider(AirCanadaProvider())
    monitor.register_provider(AirIndiaProvider())
    monitor.register_provider(CathayPacificProvider())

    return monitor


async def run_check_now():
    """Run a single immediate scan."""
    logger.info("Running immediate scan...")
    init_db()
    monitor = create_monitor()
    try:
        result = await monitor.run_full_scan()
        logger.info(
            "Scan complete: %d total, %d eligible, %.1fs",
            result["total_offers"],
            result["eligible_offers"],
            result["elapsed_seconds"],
        )
        for name, stats in result["providers"].items():
            status_icon = "✅" if stats["status"] == "success" else "⚠️"
            logger.info(
                "  %s %s: %d results, %dms",
                status_icon, name, stats["results"], stats["elapsed_ms"],
            )
    finally:
        await monitor.close_all()


async def run_daily_summary():
    """Generate and send daily summary."""
    logger.info("Generating daily summary...")
    init_db()
    monitor = create_monitor()
    try:
        summary = await monitor.generate_daily_summary()
        if summary:
            logger.info("Daily summary sent successfully")
        else:
            logger.info("No data available for daily summary")
    finally:
        await monitor.close_all()


async def run_test_alert():
    """Send a test Telegram alert."""
    from notifications.telegram import send_test_alert

    logger.info("Sending test Telegram alert...")
    success = await send_test_alert()
    if success:
        logger.info("✅ Test alert sent successfully! Check your Telegram.")
    else:
        logger.error("❌ Test alert failed. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")


async def run_test_provider(provider_name: str):
    """Test a single provider with one date combination."""
    init_db()
    logger.info("Testing provider: %s", provider_name)

    provider_map = {
        "google": "providers.google_flights.GoogleFlightsProvider",
        "google_flights": "providers.google_flights.GoogleFlightsProvider",
        "skyscanner": "providers.skyscanner.SkyscannerProvider",
        "cheapoair": "providers.cheapoair.CheapOairProvider",
        "air_canada": "providers.air_canada.AirCanadaProvider",
        "air_india": "providers.air_india.AirIndiaProvider",
        "cathay": "providers.cathay_pacific.CathayPacificProvider",
        "cathay_pacific": "providers.cathay_pacific.CathayPacificProvider",
    }

    key = provider_name.lower().replace("-", "_").replace(" ", "_")
    if key not in provider_map:
        logger.error("Unknown provider: %s. Available: %s", provider_name, ", ".join(provider_map.keys()))
        return

    module_path, class_name = provider_map[key].rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    provider_class = getattr(mod, class_name)
    provider = provider_class()

    combos = get_date_combinations()
    dep, ret = combos[0]

    try:
        results = await provider.search_flights(
            origin=ORIGIN,
            destination=DESTINATION,
            departure_date=dep,
            return_date=ret,
            passengers=PASSENGERS,
            cabin=CABIN_CLASS,
        )

        if results:
            logger.info("✅ %s returned %d results for %s → %s", provider_name, len(results), dep, ret)
            from services.baggage import evaluate_baggage
            from services.ranking import calculate_deal_score
            for i, offer in enumerate(results[:5]):
                offer = evaluate_baggage(offer)
                score = calculate_deal_score(offer)
                logger.info(
                    "  %d. $%.0f CAD | %s | %s | %d stops | bag: %s | score: %.0f",
                    i + 1,
                    offer.cad_total,
                    offer.airline,
                    offer.booking_provider,
                    offer.outbound.stops if offer.outbound else 0,
                    offer.baggage_status,
                    score,
                )
        else:
            logger.warning("⚠️ %s returned 0 results for %s → %s", provider_name, dep, ret)

    except Exception as e:
        logger.error("❌ %s failed: %s", provider_name, e)
    finally:
        await provider.close()


async def run_continuous():
    """Run the monitor continuously with scheduled checks."""
    init_db()
    monitor = create_monitor()

    logger.info("=" * 60)
    logger.info("Flight Price Monitor — YVR → BOM")
    logger.info("=" * 60)
    logger.info("Origin: %s → Destination: %s", ORIGIN, DESTINATION)
    logger.info("Departures: %s to %s", DEPARTURE_START, DEPARTURE_END)
    logger.info("Returns: %s to %s", RETURN_START, RETURN_END)
    logger.info("Date combinations: %d", len(get_date_combinations()))
    logger.info("Providers: %s", ", ".join(monitor.providers.keys()))
    logger.info("Passengers: %d, Cabin: %s", PASSENGERS, CABIN_CLASS)
    logger.info("Check interval: %dh (dynamic)", get_check_interval_hours())
    logger.info("=" * 60)

    stop_event = asyncio.Event()

    def _signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        stop_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        while not stop_event.is_set():
            try:
                result = await monitor.run_full_scan()
                logger.info(
                    "Scan complete: %d eligible offers found",
                    result["eligible_offers"],
                )
            except Exception as e:
                logger.error("Scan failed: %s", e)

            interval_hours = get_check_interval_hours()
            interval_seconds = interval_hours * 3600
            next_check = datetime.now().strftime("%H:%M")
            logger.info("Next scan in %d hours", interval_hours)

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                pass

    finally:
        await monitor.close_all()
        logger.info("Monitor stopped")


def run_dashboard():
    """Start the FastAPI web dashboard."""
    init_db()
    import uvicorn

    logger.info("Starting dashboard at http://%s:%d", DASHBOARD_HOST, DASHBOARD_PORT)
    uvicorn.run(
        "dashboard.app:app",
        host=DASHBOARD_HOST,
        port=DASHBOARD_PORT,
        reload=False,
        log_level="info",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Flight Price Monitor — YVR → BOM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--check-now", action="store_true", help="Run one immediate scan")
    parser.add_argument("--daily-summary", action="store_true", help="Send daily summary")
    parser.add_argument("--test-alert", action="store_true", help="Send test Telegram alert")
    parser.add_argument("--test-provider", type=str, help="Test a single provider")
    parser.add_argument("--dashboard", action="store_true", help="Start web dashboard")
    parser.add_argument("--init-db", action="store_true", help="Initialize database")

    args = parser.parse_args()

    if args.init_db:
        init_db()
        logger.info("✅ Database initialized at %s", str(Path("data/flights.db").absolute()))
        return

    if args.test_alert:
        asyncio.run(run_test_alert())
        return

    if args.test_provider:
        asyncio.run(run_test_provider(args.test_provider))
        return

    if args.check_now:
        asyncio.run(run_check_now())
        return

    if args.daily_summary:
        asyncio.run(run_daily_summary())
        return

    if args.dashboard:
        run_dashboard()
        return

    # Default: run continuous monitoring
    asyncio.run(run_continuous())


if __name__ == "__main__":
    main()
