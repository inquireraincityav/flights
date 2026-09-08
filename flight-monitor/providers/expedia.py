"""Expedia provider using Playwright browser automation.

Expedia is a major OTA with broad airline coverage and competitive pricing.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import List

from providers.base import (
    BaggageStatus,
    BaseProvider,
    FlightLeg,
    FlightOffer,
    VerificationLevel,
)

logger = logging.getLogger("flight_monitor")


class ExpediaProvider(BaseProvider):
    name = "expedia"
    website = "https://www.expedia.ca"
    is_airline_direct = False
    requires_browser = True

    def __init__(self):
        super().__init__()
        self._browser = None
        self._context = None
        self._min_request_interval = 6.0

    async def _ensure_browser(self):
        if self._browser is None:
            from playwright.async_api import async_playwright
            from config import HEADLESS

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=HEADLESS,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1366, "height": 768},
                locale="en-CA",
                timezone_id="America/Vancouver",
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: date,
        return_date: date,
        passengers: int = 1,
        cabin: str = "economy",
    ) -> List[FlightOffer]:
        await self._rate_limit()
        await self._ensure_browser()

        dep_str = departure_date.strftime("%Y-%m-%d")
        ret_str = return_date.strftime("%Y-%m-%d")
        logger.info("Expedia: searching %s→%s %s to %s", origin, destination, dep_str, ret_str)

        cabin_map = {"economy": "coach", "premium_economy": "premiumcoach", "business": "business", "first": "first"}
        cabin_code = cabin_map.get(cabin, "coach")

        url = (
            f"https://www.expedia.ca/Flights-search/{origin}-{destination}/"
            f"{dep_str}_{ret_str}?passengers=adults:{passengers}"
            f"&cabinClass={cabin_code}&sortBy=PRICE"
        )

        page = await self._context.new_page()
        offers = []

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(8000)

            page_text = await page.inner_text("body")
            if any(kw in page_text.lower() for kw in ["captcha", "verify", "blocked", "access denied"]):
                logger.warning("Expedia: access blocked")
                return []

            offers = await self._parse_results(page, origin, destination, dep_str, ret_str, passengers, cabin)
            logger.info("Expedia: found %d results for %s-%s", len(offers), dep_str, ret_str)

        except Exception as e:
            logger.error("Expedia search error: %s", e)
        finally:
            await page.close()

        return offers

    async def _parse_results(self, page, origin, destination, dep_str, ret_str, passengers, cabin) -> List[FlightOffer]:
        offers = []
        try:
            body_text = await page.inner_text("body")
            price_pattern = re.compile(r'(?:C?\$|CAD)\s*([\d,]+)')
            prices = price_pattern.findall(body_text)

            airline_pattern = re.compile(
                r'(Air Canada|Air India|Cathay Pacific|Emirates|Qatar Airways|'
                r'British Airways|Lufthansa|Turkish Airlines|Singapore Airlines|'
                r'KLM|Air France|WestJet|United|American|Delta|EVA Air|'
                r'Japan Airlines|ANA|Korean Air|Etihad)',
                re.IGNORECASE,
            )
            airlines = airline_pattern.findall(body_text)

            stop_pattern = re.compile(r'(\d+)\s+stop|Nonstop|Direct', re.IGNORECASE)
            duration_pattern = re.compile(r'(\d+)h\s*(\d+)?m?')

            stops_found = stop_pattern.findall(body_text)
            durations = duration_pattern.findall(body_text)

            seen = set()
            for idx, ps in enumerate(prices[:15]):
                pv = float(ps.replace(",", ""))
                if pv < 500 or pv > 15000 or pv in seen:
                    continue
                seen.add(pv)

                airline = airlines[idx] if idx < len(airlines) else "Unknown"
                stops = 1
                if idx < len(stops_found):
                    s = stops_found[idx]
                    stops = int(s) if s else 0

                dur_min = 0
                if idx < len(durations):
                    h, m = durations[idx]
                    dur_min = int(h) * 60 + (int(m) if m else 0)

                offer = FlightOffer(
                    provider=self.name,
                    search_timestamp=datetime.utcnow(),
                    origin=origin, destination=destination,
                    departure_date=dep_str, return_date=ret_str,
                    passengers=passengers, cabin_class=cabin,
                    total_price=pv, total_with_baggage=pv,
                    original_currency="CAD", original_amount=pv, cad_total=pv,
                    airline=airline, marketing_airline=airline,
                    booking_provider="Expedia",
                    source_website="expedia.ca",
                    booking_url=url,
                    outbound=FlightLeg(stops=stops, total_duration_minutes=dur_min or None),
                    inbound=FlightLeg(stops=stops),
                    verification_level=VerificationLevel.UNVERIFIED.value,
                )
                offers.append(offer)
        except Exception as e:
            logger.warning("Expedia parsing error: %s", e)

        return offers

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.stop()
