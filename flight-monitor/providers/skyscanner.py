"""Skyscanner provider using Playwright browser automation.

Skyscanner aggregates across many airlines and OTAs, with a well-structured
results page that shows prices, airlines, stops, and durations.

Limitation: Skyscanner may present CAPTCHAs or rate-limit automated access.
If this happens consistently, this provider will gracefully fail and log the issue.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime
from typing import List, Optional

from providers.base import (
    BaseProvider,
    FlightLeg,
    FlightOffer,
    VerificationLevel,
)

logger = logging.getLogger("flight_monitor")


class SkyscannerProvider(BaseProvider):
    name = "skyscanner"
    website = "https://www.skyscanner.ca"
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
        dep_fmt = departure_date.strftime("%y%m%d")
        ret_fmt = return_date.strftime("%y%m%d")

        logger.info("Skyscanner: searching %s→%s %s to %s", origin, destination, dep_str, ret_str)

        cabin_map = {"economy": "economy", "premium_economy": "premiumeconomy", "business": "business", "first": "first"}
        cabin_slug = cabin_map.get(cabin, "economy")

        url = (
            f"https://www.skyscanner.ca/transport/flights/{origin.lower()}/{destination.lower()}/"
            f"{dep_fmt}/{ret_fmt}/?adults={passengers}&cabinclass={cabin_slug}&currency=CAD"
        )

        page = await self._context.new_page()
        offers = []

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(8000)

            # Check for CAPTCHA / access blocked
            page_text = await page.inner_text("body")
            if any(kw in page_text.lower() for kw in ["verify you are human", "captcha", "blocked", "access denied"]):
                logger.warning("Skyscanner: access blocked (CAPTCHA or anti-bot)")
                return []

            offers = await self._parse_results(page, origin, destination, dep_str, ret_str, passengers, cabin)
            logger.info("Skyscanner: found %d results for %s-%s", len(offers), dep_str, ret_str)

        except Exception as e:
            logger.error("Skyscanner search error: %s", e)
        finally:
            await page.close()

        return offers

    async def _parse_results(
        self, page, origin, destination, dep_str, ret_str, passengers, cabin
    ) -> List[FlightOffer]:
        offers = []
        try:
            body_text = await page.inner_text("body")

            price_pattern = re.compile(r'(?:C?\$|CAD)\s*([\d,]+)')
            prices = price_pattern.findall(body_text)

            airline_pattern = re.compile(
                r'(Air Canada|Air India|Cathay Pacific|Emirates|Qatar Airways|'
                r'British Airways|Lufthansa|Turkish Airlines|Singapore Airlines|'
                r'KLM|Air France|WestJet|United|American|Delta|EVA Air|'
                r'Japan Airlines|ANA|Korean Air|Etihad|Oman Air)',
                re.IGNORECASE,
            )
            airlines = airline_pattern.findall(body_text)

            seen_prices = set()
            for idx, price_str in enumerate(prices[:15]):
                price_val = float(price_str.replace(",", ""))
                if price_val < 500 or price_val > 15000:
                    continue
                if price_val in seen_prices:
                    continue
                seen_prices.add(price_val)

                airline = airlines[idx] if idx < len(airlines) else "Unknown"

                stop_match = re.search(r'(\d+)\s*stop', body_text, re.IGNORECASE)
                stops = int(stop_match.group(1)) if stop_match else 1

                offer = FlightOffer(
                    provider=self.name,
                    search_timestamp=datetime.utcnow(),
                    origin=origin,
                    destination=destination,
                    departure_date=dep_str,
                    return_date=ret_str,
                    passengers=passengers,
                    cabin_class=cabin,
                    total_price=price_val,
                    total_with_baggage=price_val,
                    original_currency="CAD",
                    original_amount=price_val,
                    cad_total=price_val,
                    airline=airline,
                    marketing_airline=airline,
                    booking_provider="Skyscanner",
                    source_website="skyscanner.ca",
                    booking_url=f"https://www.skyscanner.ca/transport/flights/{origin.lower()}/{destination.lower()}/",
                    outbound=FlightLeg(stops=stops),
                    inbound=FlightLeg(stops=stops),
                    verification_level=VerificationLevel.UNVERIFIED.value,
                )
                offers.append(offer)

        except Exception as e:
            logger.warning("Skyscanner parsing error: %s", e)

        return offers

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.stop()
