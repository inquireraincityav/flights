"""Cathay Pacific direct provider using Playwright.

Cathay Pacific operates via HKG hub. Economy includes 1 × 23kg checked bag.
Competitive prices on YVR→BOM with good connection times through Hong Kong.
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


class CathayPacificProvider(BaseProvider):
    name = "cathay_pacific"
    website = "https://www.cathaypacific.com"
    is_airline_direct = True
    requires_browser = True

    def __init__(self):
        super().__init__()
        self._browser = None
        self._context = None
        self._min_request_interval = 5.0

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
        logger.info("Cathay Pacific: searching %s→%s %s to %s", origin, destination, dep_str, ret_str)

        url = (
            f"https://www.cathaypacific.com/cx/en_CA/book-a-trip/flight-search.html?"
            f"origin={origin}&destination={destination}"
            f"&departureDate={dep_str}&returnDate={ret_str}"
            f"&adults={passengers}&children=0&infants=0"
            f"&cabinClass=economy&currency=CAD"
        )

        page = await self._context.new_page()
        offers = []

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(10000)

            page_text = await page.inner_text("body")
            if any(kw in page_text.lower() for kw in ["captcha", "verify", "blocked"]):
                logger.warning("Cathay Pacific: access blocked")
                return []

            offers = await self._parse_results(page, origin, destination, dep_str, ret_str, passengers, cabin)
            logger.info("Cathay Pacific: found %d results for %s-%s", len(offers), dep_str, ret_str)

        except Exception as e:
            logger.error("Cathay Pacific search error: %s", e)
        finally:
            await page.close()

        return offers

    async def _parse_results(self, page, origin, destination, dep_str, ret_str, passengers, cabin) -> List[FlightOffer]:
        offers = []
        try:
            body_text = await page.inner_text("body")
            price_pattern = re.compile(r'(?:C?\$|CAD|HK\$)\s*([\d,]+(?:\.\d{2})?)')
            prices = price_pattern.findall(body_text)

            seen = set()
            for ps in prices[:10]:
                pv = float(ps.replace(",", ""))
                if pv < 500 or pv > 15000 or pv in seen:
                    continue
                seen.add(pv)

                offer = FlightOffer(
                    provider=self.name,
                    search_timestamp=datetime.utcnow(),
                    origin=origin, destination=destination,
                    departure_date=dep_str, return_date=ret_str,
                    passengers=passengers, cabin_class=cabin,
                    total_price=pv, total_with_baggage=pv,
                    original_currency="CAD", original_amount=pv, cad_total=pv,
                    airline="Cathay Pacific", marketing_airline="Cathay Pacific",
                    booking_provider="Cathay Pacific",
                    source_website="cathaypacific.com",
                    booking_url=url,
                    is_airline_direct=True,
                    checked_bags_included=1,
                    baggage_status=BaggageStatus.VERIFIED_INCLUDED.value,
                    baggage_weight_kg=23,
                    baggage_info_source="Cathay Pacific economy baggage allowance",
                    outbound=FlightLeg(stops=1, layover_airports=["HKG"]),
                    inbound=FlightLeg(stops=1, layover_airports=["HKG"]),
                    verification_level=VerificationLevel.LIKELY.value,
                )
                offers.append(offer)
        except Exception as e:
            logger.warning("Cathay Pacific parsing error: %s", e)

        return offers

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.stop()
