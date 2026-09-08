"""CheapOair provider using Playwright browser automation.

CheapOair is a third-party OTA that often shows competitive prices.
Their results page includes detailed itinerary info with baggage details.

Limitation: CheapOair may use anti-bot protections. If access is blocked,
this provider will gracefully fail.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import List

from providers.base import (
    BaseProvider,
    FlightLeg,
    FlightOffer,
    VerificationLevel,
)

logger = logging.getLogger("flight_monitor")


class CheapOairProvider(BaseProvider):
    name = "cheapoair"
    website = "https://www.cheapoair.ca"
    is_airline_direct = False
    requires_browser = True

    def __init__(self):
        super().__init__()
        self._browser = None
        self._context = None

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
        dep_fmt = departure_date.strftime("%m/%d/%Y")
        ret_fmt = return_date.strftime("%m/%d/%Y")

        logger.info("CheapOair: searching %s→%s %s to %s", origin, destination, dep_str, ret_str)

        cabin_map = {"economy": "Economy", "premium_economy": "PremiumEconomy", "business": "Business", "first": "First"}
        cabin_val = cabin_map.get(cabin, "Economy")

        url = (
            f"https://www.cheapoair.ca/flights/results?"
            f"origin={origin}&destination={destination}"
            f"&departure={dep_fmt}&return={ret_fmt}"
            f"&adults={passengers}&cabin={cabin_val}"
        )

        page = await self._context.new_page()
        offers = []

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(10000)

            page_text = await page.inner_text("body")
            if any(kw in page_text.lower() for kw in ["captcha", "verify", "blocked", "access denied"]):
                logger.warning("CheapOair: access blocked")
                return []

            offers = await self._parse_results(page, origin, destination, dep_str, ret_str, passengers, cabin)
            logger.info("CheapOair: found %d results for %s-%s", len(offers), dep_str, ret_str)

        except Exception as e:
            logger.error("CheapOair search error: %s", e)
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
                r'British Airways|Lufthansa|Turkish Airlines|WestJet|United|'
                r'American|Delta|EVA Air|Japan Airlines|ANA|Korean Air|Etihad)',
                re.IGNORECASE,
            )
            airlines = airline_pattern.findall(body_text)

            seen = set()
            for idx, ps in enumerate(prices[:15]):
                pv = float(ps.replace(",", ""))
                if pv < 500 or pv > 15000 or pv in seen:
                    continue
                seen.add(pv)
                airline = airlines[idx] if idx < len(airlines) else "Unknown"

                offer = FlightOffer(
                    provider=self.name,
                    search_timestamp=datetime.utcnow(),
                    origin=origin, destination=destination,
                    departure_date=dep_str, return_date=ret_str,
                    passengers=passengers, cabin_class=cabin,
                    total_price=pv, total_with_baggage=pv,
                    original_currency="CAD", original_amount=pv, cad_total=pv,
                    airline=airline, marketing_airline=airline,
                    booking_provider="CheapOair",
                    source_website="cheapoair.ca",
                    booking_url=f"https://www.cheapoair.ca/flights/results?origin={origin}&destination={destination}",
                    outbound=FlightLeg(stops=1),
                    inbound=FlightLeg(stops=1),
                    verification_level=VerificationLevel.UNVERIFIED.value,
                )
                offers.append(offer)
        except Exception as e:
            logger.warning("CheapOair parsing error: %s", e)

        return offers

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.stop()
