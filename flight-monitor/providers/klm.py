"""KLM provider using Playwright browser automation.

KLM operates via Amsterdam Schiphol (AMS) hub. Economy includes 1 × 23kg checked bag on intercontinental.
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


class KLMProvider(BaseProvider):
    name = "klm"
    website = "https://www.klm.ca"
    is_airline_direct = True
    requires_browser = True

    def __init__(self):
        super().__init__()
        self._browser = None
        self._context = None
        self._min_request_interval = 8.0

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
        logger.info("KLM: searching %s→%s %s to %s", origin, destination, dep_str, ret_str)

        dep_ddmm = departure_date.strftime("%d%m%Y")
        ret_ddmm = return_date.strftime("%d%m%Y")

        url = (
            f"https://www.klm.ca/search/offers?"
            f"origin={origin}&destination={destination}"
            f"&outboundDate={dep_str}&inboundDate={ret_str}"
            f"&adultCount={passengers}&childCount=0&infantCount=0"
            f"&cabinClass=ECONOMY"
        )

        page = await self._context.new_page()
        offers = []

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(12000)

            page_text = await page.inner_text("body")
            if any(kw in page_text.lower() for kw in ["captcha", "verify", "blocked", "access denied"]):
                logger.warning("KLM: access blocked")
                return []

            offers = await self._parse_results(page, origin, destination, dep_str, ret_str, passengers, cabin)
            logger.info("KLM: found %d results for %s-%s", len(offers), dep_str, ret_str)

        except Exception as e:
            logger.error("KLM search error: %s", e)
        finally:
            await page.close()

        return offers

    async def _parse_results(self, page, origin, destination, dep_str, ret_str, passengers, cabin) -> List[FlightOffer]:
        offers = []
        try:
            body_text = await page.inner_text("body")
            price_pattern = re.compile(r'(?:C?\$|CAD|EUR|€)\s*([\d,]+(?:\.\d{2})?)')
            prices = price_pattern.findall(body_text)

            duration_pattern = re.compile(r'(\d+)h\s*(\d+)?m?')
            durations = duration_pattern.findall(body_text)

            seen = set()
            for idx, ps in enumerate(prices[:10]):
                pv = float(ps.replace(",", ""))
                if pv < 500 or pv > 15000 or pv in seen:
                    continue
                seen.add(pv)

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
                    airline="KLM", marketing_airline="KLM",
                    booking_provider="KLM",
                    source_website="klm.ca",
                    booking_url=f"https://www.klm.ca/search/offers?origin={origin}&destination={destination}",
                    is_airline_direct=True,
                    checked_bags_included=1,
                    baggage_status=BaggageStatus.VERIFIED_INCLUDED.value,
                    baggage_weight_kg=23,
                    baggage_info_source="KLM economy intercontinental baggage (1 × 23kg)",
                    outbound=FlightLeg(stops=1, layover_airports=["AMS"], total_duration_minutes=dur_min or None),
                    inbound=FlightLeg(stops=1, layover_airports=["AMS"]),
                    verification_level=VerificationLevel.LIKELY.value,
                )
                offers.append(offer)
        except Exception as e:
            logger.warning("KLM parsing error: %s", e)

        return offers

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.stop()
