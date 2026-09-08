"""FlightHub provider using Playwright browser automation.

FlightHub is a Canadian OTA often competitive on Canada-originating international routes.
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


class FlightHubProvider(BaseProvider):
    name = "flighthub"
    website = "https://www.flighthub.com"
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
        logger.info("FlightHub: searching %s→%s %s to %s", origin, destination, dep_str, ret_str)

        dep_fmt = departure_date.strftime("%d/%m/%Y")
        ret_fmt = return_date.strftime("%d/%m/%Y")

        url = (
            f"https://www.flighthub.com/flight/search?"
            f"num_adults={passengers}&num_children=0&num_infants=0&num_infants_lap=0"
            f"&seat_class={cabin}&type=roundtrip"
            f"&seg0_from={origin}&seg0_to={destination}&seg0_date={dep_str}"
            f"&seg1_from={destination}&seg1_to={origin}&seg1_date={ret_str}"
        )

        page = await self._context.new_page()
        offers = []

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(10000)

            page_text = await page.inner_text("body")
            if any(kw in page_text.lower() for kw in ["captcha", "verify", "blocked", "access denied"]):
                logger.warning("FlightHub: access blocked")
                return []

            offers = await self._parse_results(page, origin, destination, dep_str, ret_str, passengers, cabin, url)
            logger.info("FlightHub: found %d results for %s-%s", len(offers), dep_str, ret_str)

        except Exception as e:
            logger.error("FlightHub search error: %s", e)
        finally:
            await page.close()

        return offers

    async def _parse_results(self, page, origin, destination, dep_str, ret_str, passengers, cabin, url) -> List[FlightOffer]:
        offers = []
        try:
            body_text = await page.inner_text("body")
            price_pattern = re.compile(r'(?:C?\$|CAD)\s*([\d,]+(?:\.\d{2})?)')
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
            stops_found = stop_pattern.findall(body_text)

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

                offer = FlightOffer(
                    provider=self.name,
                    search_timestamp=datetime.utcnow(),
                    origin=origin, destination=destination,
                    departure_date=dep_str, return_date=ret_str,
                    passengers=passengers, cabin_class=cabin,
                    total_price=pv, total_with_baggage=pv,
                    original_currency="CAD", original_amount=pv, cad_total=pv,
                    airline=airline, marketing_airline=airline,
                    booking_provider="FlightHub",
                    source_website="flighthub.com",
                    booking_url=url,
                    outbound=FlightLeg(stops=stops),
                    inbound=FlightLeg(stops=stops),
                    verification_level=VerificationLevel.UNVERIFIED.value,
                )
                offers.append(offer)
        except Exception as e:
            logger.warning("FlightHub parsing error: %s", e)

        return offers

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.stop()
