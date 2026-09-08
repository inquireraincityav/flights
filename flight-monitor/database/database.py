"""Database session management and initialization."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Generator, List, Optional, Tuple

from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session, sessionmaker

from config import DB_PATH
from database.models import (
    AlertSent,
    Base,
    FavoriteItinerary,
    FlightOffer,
    PriceHistory,
    ProviderHealth,
    SearchRun,
)

_engine = create_engine(
    f"sqlite:///{DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False, "timeout": 30},
)
_SessionLocal = sessionmaker(bind=_engine)


def init_db() -> None:
    Base.metadata.create_all(_engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def save_flight_offer(session: Session, offer_dict: dict) -> FlightOffer:
    offer = FlightOffer(**offer_dict)
    session.add(offer)
    session.flush()
    return offer


def save_price_history(session: Session, entry: dict) -> PriceHistory:
    ph = PriceHistory(**entry)
    session.add(ph)
    session.flush()
    return ph


def save_search_run(session: Session, run_dict: dict) -> SearchRun:
    sr = SearchRun(**run_dict)
    session.add(sr)
    session.flush()
    return sr


def save_provider_health(session: Session, health_dict: dict) -> ProviderHealth:
    ph = ProviderHealth(**health_dict)
    session.add(ph)
    session.flush()
    return ph


def record_alert(session: Session, alert_dict: dict) -> AlertSent:
    a = AlertSent(**alert_dict)
    session.add(a)
    session.flush()
    return a


def get_historical_low(
    session: Session, departure_date: str, return_date: str
) -> Optional[float]:
    result = (
        session.query(func.min(PriceHistory.lowest_price_cad))
        .filter(
            PriceHistory.departure_date == departure_date,
            PriceHistory.return_date == return_date,
            PriceHistory.is_baggage_inclusive == True,
        )
        .scalar()
    )
    return result


def get_overall_historical_low(session: Session) -> Optional[float]:
    return (
        session.query(func.min(PriceHistory.lowest_price_cad))
        .filter(PriceHistory.is_baggage_inclusive == True)
        .scalar()
    )


def get_previous_price(
    session: Session, departure_date: str, return_date: str, hours_ago: int = 24
) -> Optional[float]:
    cutoff = datetime.utcnow() - timedelta(hours=hours_ago)
    result = (
        session.query(func.min(PriceHistory.lowest_price_cad))
        .filter(
            PriceHistory.departure_date == departure_date,
            PriceHistory.return_date == return_date,
            PriceHistory.is_baggage_inclusive == True,
            PriceHistory.recorded_at < cutoff,
            PriceHistory.recorded_at >= cutoff - timedelta(hours=hours_ago),
        )
        .scalar()
    )
    return result


def get_recent_alert(
    session: Session, fingerprint: str, hours: int = 24
) -> Optional[AlertSent]:
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    return (
        session.query(AlertSent)
        .filter(
            AlertSent.fingerprint == fingerprint,
            AlertSent.sent_at >= cutoff,
        )
        .order_by(AlertSent.sent_at.desc())
        .first()
    )


def get_price_trend(
    session: Session, departure_date: str, return_date: str
) -> dict:
    now = datetime.utcnow()

    def _min_price_since(hours: int) -> Optional[float]:
        cutoff = now - timedelta(hours=hours)
        return (
            session.query(func.min(PriceHistory.lowest_price_cad))
            .filter(
                PriceHistory.departure_date == departure_date,
                PriceHistory.return_date == return_date,
                PriceHistory.is_baggage_inclusive == True,
                PriceHistory.recorded_at >= cutoff,
            )
            .scalar()
        )

    current = _min_price_since(6)
    day_ago = _min_price_since(30)
    three_days = _min_price_since(72)
    seven_days = _min_price_since(168)
    hist_low = get_historical_low(session, departure_date, return_date)

    return {
        "current": current,
        "24h_low": day_ago,
        "3d_low": three_days,
        "7d_low": seven_days,
        "historical_low": hist_low,
    }


def get_date_matrix(session: Session) -> List[dict]:
    """Get lowest baggage-inclusive price for each date combination."""
    from config import get_date_combinations

    matrix = []
    for dep, ret in get_date_combinations():
        dep_str = dep.isoformat()
        ret_str = ret.isoformat()

        row = (
            session.query(
                func.min(FlightOffer.cad_total).label("min_price"),
                FlightOffer.airline,
                FlightOffer.outbound_stops,
                FlightOffer.verification_level,
            )
            .filter(
                FlightOffer.departure_date == dep_str,
                FlightOffer.return_date == ret_str,
                FlightOffer.baggage_status.in_(
                    ["VERIFIED_INCLUDED", "VERIFIED_EXTRA_COST"]
                ),
            )
            .group_by(FlightOffer.departure_date, FlightOffer.return_date)
            .first()
        )

        matrix.append(
            {
                "departure_date": dep_str,
                "return_date": ret_str,
                "min_price": row.min_price if row else None,
                "airline": row.airline if row else None,
                "stops": row.outbound_stops if row else None,
                "verification": row.verification_level if row else None,
            }
        )
    return matrix


def get_provider_health_summary(session: Session) -> List[dict]:
    from sqlalchemy import distinct

    providers = session.query(distinct(ProviderHealth.provider)).all()
    summary = []
    for (prov,) in providers:
        latest = (
            session.query(ProviderHealth)
            .filter(ProviderHealth.provider == prov)
            .order_by(ProviderHealth.checked_at.desc())
            .first()
        )
        if latest:
            summary.append(
                {
                    "provider": prov,
                    "status": latest.status,
                    "checked_at": latest.checked_at.isoformat() if latest.checked_at else None,
                    "error": latest.error_message,
                    "results_count": latest.results_count,
                    "response_time_ms": latest.response_time_ms,
                }
            )
    return summary


def is_favorite(session: Session, fingerprint: str) -> bool:
    return (
        session.query(FavoriteItinerary)
        .filter(FavoriteItinerary.fingerprint == fingerprint)
        .first()
        is not None
    )


def add_favorite(session: Session, fingerprint: str, **kwargs) -> FavoriteItinerary:
    fav = FavoriteItinerary(fingerprint=fingerprint, **kwargs)
    session.add(fav)
    session.flush()
    return fav


def remove_favorite(session: Session, fingerprint: str) -> bool:
    deleted = (
        session.query(FavoriteItinerary)
        .filter(FavoriteItinerary.fingerprint == fingerprint)
        .delete()
    )
    return deleted > 0
