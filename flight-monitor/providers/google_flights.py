"""Google Flights provider using Playwright browser automation.

Google Flights is the primary provider — it aggregates fares across many airlines
and OTAs, returning structured results that can be parsed from the page.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import date, datetime
from typing import List, Optional

from providers.base import (
    BaggageStatus,
    BaseProvider,
    FlightLeg,
    FlightOffer,
    FlightSegment,
    VerificationLevel,
)

logger = logging.getLogger("flight_monitor")

CABIN_MAP = {
    "economy": 1,
    "premium_economy": 2,
    "business": 3,
    "first": 4,
}


def _build_url(
    origin: str,
    destination: str,
    departure_date: date,
    return_date: date,
    passengers: int = 1,
    cabin: str = "economy",
) -> str:
    dep = departure_date.strftime("%Y-%m-%d")
    ret = return_date.strftime("%Y-%m-%d")
    cabin_code = CABIN_MAP.get(cabin, 1)
    return (
        f"https://www.google.com/travel/flights?"
        f"q=Flights+to+{destination}+from+{origin}+"
        f"on+{dep}+through+{ret}&curr=CAD&"
        f"tfs=CBwQAhooEgoyMDI2LTEyLTExagwIAhIIL20vMDgwaDlyDAoCEggvbS8wMWNnZBooEgoyMDI3LTAxLTAzagwKAhIIL20vMDFjZ2RyDAoCEggvbS8wODBoOXABggELCP___________wFAAUgBmAEB"
    )


def _build_simple_url(
    origin: str,
    destination: str,
    departure_date: date,
    return_date: date,
) -> str:
    dep = departure_date.strftime("%Y-%m-%d")
    ret = return_date.strftime("%Y-%m-%d")
    return (
        f"https://www.google.com/travel/flights/search?"
        f"tfs=CBwQAhoeEgoyMDI2LTEyLTExagcIARIDWVZScgcIARIDQk9NEh4SCjIwMjctMDEtMDNqBwgBEgNCT01yBwgBEgNZVlJwAYIBC"
        f"P___________wFAAUgBmAEB"
    )


class GoogleFlightsProvider(BaseProvider):
    name = "google_flights"
    website = "https://www.google.com/travel/flights"
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
        logger.info(
            "Google Flights: searching %s→%s %s to %s",
            origin, destination, dep_str, ret_str,
        )

        page = await self._context.new_page()
        offers = []

        try:
            url = (
                f"https://www.google.com/travel/flights/search?"
                f"tfs=CBwQAhoeEgoyMDI2LTEyLTExagcIARIDWVZScgcIARIDQk9NEh4SCjIwMjctMDEtMDNqBwgBEgNCT01yBwgBEgNZVlJwAYIBC"
            )
            search_url = f"https://www.google.com/travel/flights?q=Flights+to+{destination}+from+{origin}+on+{dep_str}+through+{ret_str}&curr=CAD"

            await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(5000)

            # Try to dismiss consent dialogs
            for selector in [
                'button:has-text("Accept all")',
                'button:has-text("I agree")',
                'button:has-text("Reject all")',
            ]:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await page.wait_for_timeout(1000)
                        break
                except Exception:
                    pass

            await page.wait_for_timeout(3000)

            # Parse flight results from the page
            results = await self._parse_results(page, origin, destination, dep_str, ret_str, passengers, cabin)
            offers.extend(results)

            logger.info(
                "Google Flights: found %d results for %s→%s %s-%s",
                len(offers), origin, destination, dep_str, ret_str,
            )

        except Exception as e:
            logger.error("Google Flights search error: %s", e)
        finally:
            await page.close()

        return offers

    async def _parse_results(
        self, page, origin, destination, dep_str, ret_str, passengers, cabin
    ) -> List[FlightOffer]:
        offers = []

        try:
            # Google Flights uses data attributes and specific class patterns
            # Look for flight result list items
            result_cards = page.locator('li[class*="pIav2d"], div[class*="yR1fYc"], div[class*="Rk10dc"]')
            count = await result_cards.count()

            if count == 0:
                # Try alternate selectors
                result_cards = page.locator('div[jsname="IWWDBc"], ul[class*="Rk10dc"] > li')
                count = await result_cards.count()

            if count == 0:
                # Fallback: try to extract from page text
                offers = await self._parse_from_text(page, origin, destination, dep_str, ret_str, passengers, cabin)
                return offers

            for i in range(min(count, 20)):
                try:
                    card = result_cards.nth(i)
                    text = await card.inner_text()
                    offer = self._extract_offer_from_text(
                        text, origin, destination, dep_str, ret_str, passengers, cabin
                    )
                    if offer:
                        offers.append(offer)
                except Exception as e:
                    logger.debug("Error parsing card %d: %s", i, e)

        except Exception as e:
            logger.debug("Result parsing fallback: %s", e)
            offers = await self._parse_from_text(
                page, origin, destination, dep_str, ret_str, passengers, cabin
            )

        return offers

    async def _parse_from_text(
        self, page, origin, destination, dep_str, ret_str, passengers, cabin
    ) -> List[FlightOffer]:
        """Fallback: extract flight info from full page text."""
        offers = []
        try:
            body_text = await page.inner_text("body")

            price_pattern = re.compile(r'(?:CA?\$|CAD\s*)\s*([\d,]+)')
            prices = price_pattern.findall(body_text)

            airline_pattern = re.compile(
                r'(Air Canada|Air India|Cathay Pacific|Emirates|Qatar Airways|'
                r'British Airways|Lufthansa|Turkish Airlines|Singapore Airlines|'
                r'KLM|Air France|WestJet|United|American|Delta|EVA Air|'
                r'Japan Airlines|ANA|Korean Air|Etihad|Oman Air|'
                r'China Eastern|China Southern|Hainan Airlines)',
                re.IGNORECASE,
            )
            airlines = airline_pattern.findall(body_text)

            stop_pattern = re.compile(r'(\d+)\s+stop|Nonstop|Non-stop|nonstop', re.IGNORECASE)
            duration_pattern = re.compile(r'(\d+)\s*(?:hr?|hours?)\s*(\d+)?\s*(?:min)?')

            stops_found = stop_pattern.findall(body_text)
            durations = duration_pattern.findall(body_text)

            seen_prices = set()
            for idx, price_str in enumerate(prices[:15]):
                price_val = float(price_str.replace(",", ""))
                if price_val < 500 or price_val > 15000:
                    continue
                if price_val in seen_prices:
                    continue
                seen_prices.add(price_val)

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
                    booking_provider="Google Flights",
                    source_website="google.com/travel/flights",
                    booking_url=f"https://www.google.com/travel/flights?q=Flights+to+{destination}+from+{origin}+on+{dep_str}+through+{ret_str}&curr=CAD",
                    outbound=FlightLeg(
                        stops=stops,
                        total_duration_minutes=dur_min or None,
                    ),
                    inbound=FlightLeg(stops=stops),
                    verification_level=VerificationLevel.UNVERIFIED.value,
                )
                offers.append(offer)

        except Exception as e:
            logger.warning("Text-based parsing failed: %s", e)

        return offers

    def _extract_offer_from_text(
        self, text: str, origin, destination, dep_str, ret_str, passengers, cabin
    ) -> Optional[FlightOffer]:
        """Extract a single flight offer from card text."""
        try:
            price_match = re.search(r'(?:CA?\$|CAD)\s*([\d,]+)', text)
            if not price_match:
                return None
            price = float(price_match.group(1).replace(",", ""))
            if price < 500 or price > 15000:
                return None

            airline_match = re.search(
                r'(Air Canada|Air India|Cathay Pacific|Emirates|Qatar|'
                r'British Airways|Lufthansa|Turkish|Singapore|KLM|Air France|'
                r'WestJet|United|American|Delta|EVA Air|Japan Airlines|ANA|'
                r'Korean Air|Etihad)',
                text, re.IGNORECASE,
            )
            airline = airline_match.group(1) if airline_match else "Unknown"

            stop_match = re.search(r'(\d+)\s*stop', text, re.IGNORECASE)
            nonstop = bool(re.search(r'nonstop|non-stop', text, re.IGNORECASE))
            stops = 0 if nonstop else (int(stop_match.group(1)) if stop_match else 1)

            dur_match = re.search(r'(\d+)\s*(?:hr?|hours?)\s*(\d+)?\s*(?:min)?', text)
            dur_min = 0
            if dur_match:
                dur_min = int(dur_match.group(1)) * 60
                if dur_match.group(2):
                    dur_min += int(dur_match.group(2))

            return FlightOffer(
                provider=self.name,
                search_timestamp=datetime.utcnow(),
                origin=origin,
                destination=destination,
                departure_date=dep_str,
                return_date=ret_str,
                passengers=passengers,
                cabin_class=cabin,
                total_price=price,
                total_with_baggage=price,
                original_currency="CAD",
                original_amount=price,
                cad_total=price,
                airline=airline,
                marketing_airline=airline,
                booking_provider="Google Flights",
                source_website="google.com/travel/flights",
                booking_url=f"https://www.google.com/travel/flights?q=Flights+to+{destination}+from+{origin}+on+{dep_str}+through+{ret_str}&curr=CAD",
                outbound=FlightLeg(stops=stops, total_duration_minutes=dur_min or None),
                inbound=FlightLeg(stops=stops),
                verification_level=VerificationLevel.UNVERIFIED.value,
            )
        except Exception as e:
            logger.debug("Card extraction error: %s", e)
            return None

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if hasattr(self, "_playwright") and self._playwright:
            await self._playwright.stop()
