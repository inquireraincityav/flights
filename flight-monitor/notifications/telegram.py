"""Telegram Bot API integration for flight alerts."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    get_deal_emoji,
    get_deal_tier,
)
from utils.dates import format_date_full, format_duration
from utils.time import format_local, now_local

logger = logging.getLogger("flight_monitor")

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


async def _call_api(method: str, data: dict, retries: int = 3) -> Optional[dict]:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — skipping %s", method)
        return None

    url = TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN, method=method)
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=data)
                result = resp.json()
                if result.get("ok"):
                    return result
                logger.warning(
                    "Telegram API error: %s (attempt %d)", result, attempt + 1
                )
        except Exception as e:
            logger.warning("Telegram request failed: %s (attempt %d)", e, attempt + 1)

        if attempt < retries - 1:
            await asyncio.sleep(2 ** (attempt + 1))

    logger.error("Telegram %s failed after %d attempts", method, retries)
    return None


async def send_message(
    text: str,
    parse_mode: str = "HTML",
    reply_markup: Optional[dict] = None,
) -> Optional[str]:
    data: Dict[str, Any] = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        data["reply_markup"] = reply_markup

    result = await _call_api("sendMessage", data)
    if result and result.get("result"):
        msg_id = str(result["result"].get("message_id", ""))
        logger.info("Telegram message sent (id=%s)", msg_id)
        return msg_id
    return None


async def send_test_alert() -> bool:
    text = (
        "<b>\U0001f525 YVR → BOM FLIGHT DEAL — TEST</b>\n\n"
        "\U0001f7e3 EXCELLENT DEAL\n"
        "\U0001f4b0 <b>$1,987 CAD</b> ROUND TRIP\n"
        "✅ 1 CHECKED BAG INCLUDED\n"
        "\U0001f9f3 1 × 23 kg\n"
        "\U0001f7e2 BOOKING STATUS: VERIFIED\n\n"
        "\U0001f4c5 <b>TRAVEL</b>\n"
        "Dec 13, 2026 → Jan 4, 2027\n\n"
        "✈️ <b>AIRLINE</b>\n"
        "Cathay Pacific\n\n"
        "<b>OUTBOUND</b>\n"
        "YVR → HKG → BOM\n"
        "1 stop • 19h 35m\n\n"
        "<b>RETURN</b>\n"
        "BOM → HKG → YVR\n"
        "1 stop • 18h 50m\n\n"
        "\U0001f4ba <b>FARE</b>: Economy Standard\n"
        "\U0001f4b0 <b>BASE FARE</b>: $1,987 CAD\n"
        "\U0001f9f3 <b>BAGGAGE</b>: Included\n"
        "\U0001f4b3 <b>ACTUAL TOTAL</b>: $1,987 CAD\n\n"
        "\U0001f4c9 PREVIOUS BEST: $2,143\n"
        "\U0001f3c6 HISTORICAL LOW: $1,950\n"
        "\U0001f4ca TREND: \U0001f4c9 Falling\n\n"
        "\U0001f3f7 <b>BOOKING SOURCE</b>: Cathay Pacific Direct\n"
        "⭐ <b>DEAL SCORE</b>: 94/100\n\n"
        "\U0001f517 <a href=\"https://www.cathaypacific.com\">VIEW / BOOK</a>\n\n"
        f"<i>Checked: {format_local(now_local())}</i>\n"
        "⚠️ <i>Fare availability and pricing can change until ticketing is completed.</i>\n\n"
        "ℹ️ <b>This is a TEST notification.</b>"
    )
    result = await send_message(text)
    return result is not None


def _build_deal_alert(offer: dict, hist_low: float | None, prev_best: float | None) -> str:
    price = offer["cad_total"]
    tier = get_deal_tier(price)
    emoji = get_deal_emoji(tier)
    tier_label = {
        "INSANE": "INSANE DEAL",
        "EXCELLENT": "EXCELLENT DEAL",
        "GREAT": "GREAT DEAL",
        "GOOD": "GOOD / BOOKABLE DEAL",
        "ABOVE_TARGET": "ABOVE TARGET",
    }.get(tier, tier)

    headline = f"<b>\U0001f525 YVR → BOM FLIGHT DEAL</b>"
    if tier == "INSANE":
        headline = f"<b>\U0001f6a8\U0001f525 INSANE YVR → BOM DEAL \U0001f525\U0001f6a8</b>"

    bag_line = "✅ 1 CHECKED BAG INCLUDED" if offer.get("checked_bags_included", 0) > 0 else ""
    bag_weight = f"\U0001f9f3 {offer.get('checked_bags_included', 1)} × {offer.get('baggage_weight_kg', 23)} kg" if offer.get("baggage_weight_kg") else ""

    verif = offer.get("verification_level", "UNVERIFIED")
    verif_emoji = {"VERIFIED": "\U0001f7e2", "LIKELY": "\U0001f7e1", "UNVERIFIED": "\U0001f534"}.get(verif, "\U0001f534")

    out_stops = offer.get("outbound_stops", 0)
    ret_stops = offer.get("return_stops", 0)
    out_dur = format_duration(offer.get("outbound_duration_minutes"))
    ret_dur = format_duration(offer.get("return_duration_minutes"))

    out_route = f"{offer.get('origin', 'YVR')} → {offer.get('destination', 'BOM')}"
    ret_route = f"{offer.get('destination', 'BOM')} → {offer.get('origin', 'YVR')}"
    if offer.get("outbound_layover_airports"):
        try:
            layovers = json.loads(offer["outbound_layover_airports"]) if isinstance(offer["outbound_layover_airports"], str) else offer["outbound_layover_airports"]
            if layovers:
                out_route = f"{offer.get('origin', 'YVR')} → {' → '.join(layovers)} → {offer.get('destination', 'BOM')}"
        except (json.JSONDecodeError, TypeError):
            pass
    if offer.get("return_layover_airports"):
        try:
            layovers = json.loads(offer["return_layover_airports"]) if isinstance(offer["return_layover_airports"], str) else offer["return_layover_airports"]
            if layovers:
                ret_route = f"{offer.get('destination', 'BOM')} → {' → '.join(layovers)} → {offer.get('origin', 'YVR')}"
        except (json.JSONDecodeError, TypeError):
            pass

    warnings = []
    if offer.get("self_transfer"):
        warnings.append("⚠️ SELF-TRANSFER")
    if offer.get("airport_change"):
        warnings.append("⚠️ AIRPORT CHANGE REQUIRED")

    lines = [
        headline,
        f"{emoji} {tier_label}",
        f"\U0001f4b0 <b>${price:,.0f} CAD</b> ROUND TRIP",
    ]
    if bag_line:
        lines.append(bag_line)
    if bag_weight:
        lines.append(bag_weight)
    lines.append(f"{verif_emoji} BOOKING STATUS: {verif}")
    lines.append("")
    lines.append(f"\U0001f4c5 <b>TRAVEL</b>")
    lines.append(f"{offer.get('departure_date', '')} → {offer.get('return_date', '')}")
    lines.append("")
    lines.append(f"✈️ <b>AIRLINE</b>")
    lines.append(offer.get("airline", "Unknown"))
    lines.append("")
    lines.append(f"<b>OUTBOUND</b>")
    lines.append(f"{out_route}")
    lines.append(f"{out_stops} stop{'s' if out_stops != 1 else ''} • {out_dur}")
    lines.append("")
    lines.append(f"<b>RETURN</b>")
    lines.append(f"{ret_route}")
    lines.append(f"{ret_stops} stop{'s' if ret_stops != 1 else ''} • {ret_dur}")
    lines.append("")
    if offer.get("fare_brand"):
        lines.append(f"\U0001f4ba <b>FARE</b>: {offer['fare_brand']}")
    lines.append(f"\U0001f4b0 <b>BASE FARE</b>: ${offer.get('total_price', price):,.0f} {offer.get('original_currency', 'CAD')}")

    bag_status = offer.get("baggage_status", "UNKNOWN")
    if bag_status == "VERIFIED_INCLUDED":
        lines.append(f"\U0001f9f3 <b>BAGGAGE</b>: Included")
    elif bag_status == "VERIFIED_EXTRA_COST":
        lines.append(f"\U0001f9f3 <b>BAGGAGE</b>: +${offer.get('baggage_cost', 0):,.0f} CAD")
    else:
        lines.append(f"\U0001f9f3 <b>BAGGAGE</b>: {bag_status}")

    lines.append(f"\U0001f4b3 <b>ACTUAL TOTAL</b>: ${price:,.0f} CAD")
    lines.append("")

    if prev_best:
        lines.append(f"\U0001f4c9 PREVIOUS BEST: ${prev_best:,.0f}")
    if hist_low:
        lines.append(f"\U0001f3c6 HISTORICAL LOW: ${hist_low:,.0f}")

    lines.append("")

    for w in warnings:
        lines.append(w)

    lines.append(f"\U0001f3f7 <b>BOOKING SOURCE</b>: {offer.get('booking_provider', offer.get('provider', 'Unknown'))}")
    if offer.get("deal_score"):
        lines.append(f"⭐ <b>DEAL SCORE</b>: {offer['deal_score']:.0f}/100")
    lines.append("")

    if offer.get("booking_url"):
        lines.append(f'\U0001f517 <a href="{offer["booking_url"]}">VIEW / BOOK</a>')
    lines.append("")
    lines.append(f"<i>Checked: {format_local(now_local())}</i>")
    lines.append("⚠️ <i>Fare availability and pricing can change until ticketing is completed.</i>")

    return "\n".join(lines)


async def send_deal_alert(
    offer: dict,
    hist_low: float | None = None,
    prev_best: float | None = None,
) -> Optional[str]:
    text = _build_deal_alert(offer, hist_low, prev_best)
    buttons = []
    if offer.get("booking_url"):
        buttons.append(
            {"text": "VIEW / BOOK", "url": offer["booking_url"]}
        )
    markup = {"inline_keyboard": [buttons]} if buttons else None
    return await send_message(text, reply_markup=markup)


async def send_price_drop_alert(
    offer: dict,
    old_price: float,
    new_price: float,
) -> Optional[str]:
    drop = old_price - new_price
    text = (
        f"<b>\U0001f4c9 MAJOR PRICE DROP</b>\n\n"
        f"YVR → BOM\n"
        f"{offer.get('departure_date', '')} → {offer.get('return_date', '')}\n"
        f"{offer.get('airline', 'Unknown')}\n\n"
        f"Previous: ${old_price:,.0f} CAD\n"
        f"Now: <b>${new_price:,.0f} CAD</b>\n"
        f"Savings: -${drop:,.0f} CAD\n\n"
        f"<i>Checked: {format_local(now_local())}</i>"
    )
    return await send_message(text)


async def send_historical_low_alert(
    offer: dict,
    prev_low: float,
    new_low: float,
) -> Optional[str]:
    savings = prev_low - new_low
    text = (
        f"<b>\U0001f3c6 NEW LOWEST PRICE</b>\n\n"
        f"YVR → BOM\n"
        f"{offer.get('departure_date', '')} → {offer.get('return_date', '')}\n"
        f"{offer.get('airline', 'Unknown')}\n\n"
        f"Previous low: ${prev_low:,.0f} CAD\n"
        f"New low: <b>${new_low:,.0f} CAD</b>\n"
        f"Savings: ${savings:,.0f}\n\n"
        f"<i>Checked: {format_local(now_local())}</i>"
    )
    return await send_message(text)


async def send_daily_summary(summary: dict) -> Optional[str]:
    today = now_local().strftime("%B %d, %Y")

    lines = [
        f"<b>\U0001f4ca YVR → BOM DAILY FLIGHT REPORT</b>",
        f"Date: {today}",
        "",
    ]

    if summary.get("cheapest"):
        c = summary["cheapest"]
        lines.append(f"\U0001f3c6 <b>CHEAPEST TODAY</b>")
        lines.append(f"${c['price']:,.0f} CAD")
        lines.append(f"{c.get('departure_date', '')} → {c.get('return_date', '')}")
        lines.append(f"{c.get('airline', 'Unknown')}")
        if c.get("stops") is not None:
            lines.append(f"{c['stops']} stop{'s' if c['stops'] != 1 else ''}")
        lines.append("")

    if summary.get("best_value"):
        bv = summary["best_value"]
        lines.append(f"⭐ <b>BEST VALUE</b>")
        lines.append(f"${bv['price']:,.0f} CAD")
        lines.append(f"{bv.get('departure_date', '')} → {bv.get('return_date', '')}")
        lines.append(f"{bv.get('airline', 'Unknown')}")
        lines.append("")

    if summary.get("best_direct"):
        bd = summary["best_direct"]
        lines.append(f"✈️ <b>BEST AIRLINE-DIRECT</b>")
        lines.append(f"${bd['price']:,.0f} CAD")
        lines.append(bd.get("airline", "Unknown"))
        lines.append("")

    if summary.get("fastest"):
        f_ = summary["fastest"]
        lines.append(f"⚡ <b>FASTEST ELIGIBLE</b>")
        lines.append(f"${f_['price']:,.0f} CAD")
        lines.append(f"{f_.get('airline', 'Unknown')}")
        lines.append(f"{format_duration(f_.get('duration'))}")
        lines.append("")

    stats = summary.get("stats", {})
    if stats.get("yesterday_low"):
        lines.append(f"Yesterday's lowest: ${stats['yesterday_low']:,.0f}")
    if stats.get("today_low"):
        lines.append(f"Today's lowest: ${stats['today_low']:,.0f}")
    if stats.get("yesterday_low") and stats.get("today_low"):
        change = stats["today_low"] - stats["yesterday_low"]
        arrow = "\U0001f4c9" if change < 0 else "\U0001f4c8" if change > 0 else "➡️"
        lines.append(f"Change: {'+' if change > 0 else ''}{change:,.0f} {arrow}")
    if stats.get("seven_day_low"):
        lines.append(f"7-day low: ${stats['seven_day_low']:,.0f}")
    if stats.get("historical_low"):
        lines.append(f"Historical low: ${stats['historical_low']:,.0f}")
    lines.append("")
    lines.append(f"{stats.get('combinations_checked', 15)} date combinations checked")
    lines.append(f"{stats.get('providers_attempted', 0)} providers attempted")
    lines.append(f"{stats.get('providers_successful', 0)} providers successful")
    lines.append(f"{stats.get('eligible_itineraries', 0)} eligible itineraries analyzed")

    if summary.get("top_options"):
        lines.append("")
        lines.append("<b>TOP OPTIONS</b>")
        for i, opt in enumerate(summary["top_options"][:5], 1):
            lines.append(
                f"{i}. ${opt['price']:,.0f} — {opt.get('departure_date', '')} to {opt.get('return_date', '')} — {opt.get('airline', 'Unknown')}"
            )

    lines.append("")
    lines.append(f"<i>{format_local(now_local())}</i>")

    return await send_message("\n".join(lines))


async def send_status(status: dict) -> Optional[str]:
    lines = [
        "<b>\U0001f4e1 Flight Monitor Status</b>",
        "",
        f"Running: {'Yes' if status.get('running') else 'No'}",
        f"Last check: {status.get('last_check', 'Never')}",
        f"Next check: {status.get('next_check', 'Unknown')}",
        "",
        "<b>Provider Health</b>",
    ]
    for p in status.get("providers", []):
        icon = "✅" if p["status"] == "success" else "⚠️"
        lines.append(f"{icon} {p['provider']}: {p['status']}")
        if p.get("checked_at"):
            lines.append(f"   Last check: {p['checked_at']}")
        if p.get("error"):
            lines.append(f"   Error: {p['error'][:100]}")

    return await send_message("\n".join(lines))


async def handle_command(command: str) -> Optional[str]:
    """Handle incoming Telegram bot commands. Returns response text."""
    cmd = command.strip().lower()
    if cmd == "/help":
        return (
            "<b>Flight Monitor Commands</b>\n\n"
            "/status - Monitoring status\n"
            "/best - Current best flights\n"
            "/today - Today's best fares\n"
            "/dates - Cheapest per date combo\n"
            "/direct - Best airline-direct fares\n"
            "/history - Historical lowest\n"
            "/check - Trigger immediate scan\n"
            "/help - This message"
        )
    return None
