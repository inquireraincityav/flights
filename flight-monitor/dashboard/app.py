"""FastAPI dashboard for flight price monitoring."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from config import (
    DEPARTURE_END,
    DEPARTURE_START,
    DESTINATION,
    ORIGIN,
    RETURN_END,
    RETURN_START,
    get_date_combinations,
)
from database.database import (
    add_favorite,
    get_date_matrix,
    get_overall_historical_low,
    get_provider_health_summary,
    get_session,
    init_db,
    is_favorite,
    remove_favorite,
)
from database.models import FlightOffer, PriceHistory

app = FastAPI(title="Flight Price Monitor", version="1.0.0")

BASE = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/summary")
async def api_summary():
    with get_session() as session:
        from sqlalchemy import func

        cheapest = (
            session.query(FlightOffer)
            .filter(FlightOffer.baggage_status.in_(["VERIFIED_INCLUDED", "VERIFIED_EXTRA_COST"]))
            .order_by(FlightOffer.cad_total.asc())
            .first()
        )

        direct = (
            session.query(FlightOffer)
            .filter(
                FlightOffer.is_airline_direct == True,
                FlightOffer.baggage_status.in_(["VERIFIED_INCLUDED", "VERIFIED_EXTRA_COST"]),
            )
            .order_by(FlightOffer.cad_total.asc())
            .first()
        )

        best_score = (
            session.query(FlightOffer)
            .filter(FlightOffer.baggage_status.in_(["VERIFIED_INCLUDED", "VERIFIED_EXTRA_COST"]))
            .order_by(FlightOffer.deal_score.desc())
            .first()
        )

        hist_low = get_overall_historical_low(session)

        # Recent 7-day
        from datetime import timedelta
        week_ago = datetime.utcnow() - timedelta(days=7)
        seven_low = (
            session.query(func.min(PriceHistory.lowest_price_cad))
            .filter(
                PriceHistory.is_baggage_inclusive == True,
                PriceHistory.recorded_at >= week_ago,
            )
            .scalar()
        )

        providers = get_provider_health_summary(session)

        total = session.query(func.count(FlightOffer.id)).scalar() or 0

    def _offer_dict(o):
        if o is None:
            return None
        return {
            "price": o.cad_total,
            "airline": o.airline,
            "departure_date": o.departure_date,
            "return_date": o.return_date,
            "stops": o.outbound_stops,
            "deal_score": o.deal_score,
            "deal_tier": o.deal_tier,
            "verification": o.verification_level,
            "provider": o.booking_provider,
            "booking_url": o.booking_url,
        }

    return {
        "origin": ORIGIN,
        "destination": DESTINATION,
        "departure_range": f"{DEPARTURE_START} to {DEPARTURE_END}",
        "return_range": f"{RETURN_START} to {RETURN_END}",
        "cheapest": _offer_dict(cheapest),
        "best_value": _offer_dict(best_score),
        "best_direct": _offer_dict(direct),
        "historical_low": hist_low,
        "seven_day_low": seven_low,
        "total_offers": total,
        "providers": providers,
    }


@app.get("/api/matrix")
async def api_matrix():
    with get_session() as session:
        matrix = get_date_matrix(session)
    return {"matrix": matrix}


@app.get("/api/flights")
async def api_flights(
    departure_date: Optional[str] = None,
    return_date: Optional[str] = None,
    airline: Optional[str] = None,
    provider: Optional[str] = None,
    max_price: Optional[float] = None,
    max_stops: Optional[int] = None,
    max_duration: Optional[int] = None,
    baggage_included: Optional[bool] = None,
    airline_direct: Optional[bool] = None,
    verified_only: Optional[bool] = None,
    exclude_self_transfer: Optional[bool] = None,
    exclude_airport_change: Optional[bool] = None,
    sort_by: str = "price",
    limit: int = 50,
    offset: int = 0,
):
    with get_session() as session:
        q = session.query(FlightOffer)

        if departure_date:
            q = q.filter(FlightOffer.departure_date == departure_date)
        if return_date:
            q = q.filter(FlightOffer.return_date == return_date)
        if airline:
            q = q.filter(FlightOffer.airline.ilike(f"%{airline}%"))
        if provider:
            q = q.filter(FlightOffer.booking_provider.ilike(f"%{provider}%"))
        if max_price:
            q = q.filter(FlightOffer.cad_total <= max_price)
        if max_stops is not None:
            q = q.filter(FlightOffer.outbound_stops <= max_stops)
        if baggage_included:
            q = q.filter(FlightOffer.baggage_status.in_(["VERIFIED_INCLUDED", "VERIFIED_EXTRA_COST"]))
        if airline_direct:
            q = q.filter(FlightOffer.is_airline_direct == True)
        if verified_only:
            q = q.filter(FlightOffer.verification_level.in_(["VERIFIED", "LIKELY"]))
        if exclude_self_transfer:
            q = q.filter(FlightOffer.self_transfer == False)
        if exclude_airport_change:
            q = q.filter(FlightOffer.airport_change == False)

        sort_map = {
            "price": FlightOffer.cad_total.asc(),
            "score": FlightOffer.deal_score.desc(),
            "duration": FlightOffer.outbound_duration_minutes.asc(),
            "stops": FlightOffer.outbound_stops.asc(),
        }
        q = q.order_by(sort_map.get(sort_by, FlightOffer.cad_total.asc()))

        total = q.count()
        results = q.offset(offset).limit(limit).all()

        flights = []
        for o in results:
            flights.append({
                "id": o.id,
                "fingerprint": o.fingerprint,
                "departure_date": o.departure_date,
                "return_date": o.return_date,
                "airline": o.airline,
                "cad_total": o.cad_total,
                "base_fare": o.base_fare,
                "taxes": o.taxes,
                "baggage_cost": o.baggage_cost,
                "total_with_baggage": o.total_with_baggage,
                "original_currency": o.original_currency,
                "outbound_stops": o.outbound_stops,
                "return_stops": o.return_stops,
                "outbound_duration_minutes": o.outbound_duration_minutes,
                "return_duration_minutes": o.return_duration_minutes,
                "outbound_layover_airports": o.outbound_layover_airports,
                "return_layover_airports": o.return_layover_airports,
                "is_airline_direct": o.is_airline_direct,
                "booking_provider": o.booking_provider,
                "booking_url": o.booking_url,
                "baggage_status": o.baggage_status,
                "checked_bags_included": o.checked_bags_included,
                "baggage_weight_kg": o.baggage_weight_kg,
                "verification_level": o.verification_level,
                "deal_score": o.deal_score,
                "deal_tier": o.deal_tier,
                "self_transfer": o.self_transfer,
                "airport_change": o.airport_change,
                "fare_brand": o.fare_brand,
                "fare_class": o.fare_class,
            })

    return {"total": total, "flights": flights}


@app.get("/api/price-history")
async def api_price_history(
    departure_date: Optional[str] = None,
    return_date: Optional[str] = None,
    airline: Optional[str] = None,
    days: int = 7,
):
    with get_session() as session:
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)

        q = session.query(PriceHistory).filter(PriceHistory.recorded_at >= cutoff)
        if departure_date:
            q = q.filter(PriceHistory.departure_date == departure_date)
        if return_date:
            q = q.filter(PriceHistory.return_date == return_date)
        if airline:
            q = q.filter(PriceHistory.airline.ilike(f"%{airline}%"))

        q = q.order_by(PriceHistory.recorded_at.asc())
        results = q.limit(5000).all()

        history = [
            {
                "recorded_at": r.recorded_at.isoformat(),
                "departure_date": r.departure_date,
                "return_date": r.return_date,
                "provider": r.provider,
                "airline": r.airline,
                "price": r.lowest_price_cad,
                "is_direct": r.is_airline_direct,
            }
            for r in results
        ]

    return {"history": history, "count": len(history)}


@app.get("/api/providers")
async def api_providers():
    with get_session() as session:
        return {"providers": get_provider_health_summary(session)}


@app.post("/api/favorites/{fingerprint}")
async def toggle_favorite(fingerprint: str):
    with get_session() as session:
        if is_favorite(session, fingerprint):
            remove_favorite(session, fingerprint)
            return {"favorited": False}
        else:
            add_favorite(session, fingerprint)
            return {"favorited": True}


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
