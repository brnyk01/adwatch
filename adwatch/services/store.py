"""
Persistence helpers.
- upsert_ads:     write AdResults → ads table, dedupe on (platform, external_ad_id)
- update_flights: maintain creative_flights continuity rows
- record_run:     write a query_runs row for every connector call
"""

import json
from datetime import datetime, timezone

from sqlmodel import Session, select

from adwatch.connectors.base import AdResult, ConnectorResponse, Query, Status
from adwatch.db import engine
from adwatch.models import Ad, CreativeFlight, QueryRun


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    import urllib.parse
    try:
        return urllib.parse.urlparse(url).netloc.lstrip("www.") or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upsert_ads(
    *,
    session: Session,
    platform: str,
    subject_type: str,
    subject_id: int,
    ads: list[AdResult],
) -> list[Ad]:
    """
    Insert or update Ad rows.
    Deduplication key: (platform, external_ad_id).
    Returns the list of persisted Ad ORM objects.
    """
    persisted: list[Ad] = []
    now = _now()

    for result in ads:
        existing = session.exec(
            select(Ad).where(
                Ad.platform == platform,
                Ad.external_ad_id == result.external_ad_id,
            )
        ).first()

        if existing:
            # Update mutable fields
            existing.last_shown = result.last_shown
            existing.creative_text = result.creative_text or existing.creative_text
            existing.snapshot_url = result.snapshot_url or existing.snapshot_url
            existing.spend_range = json.dumps(result.spend_range) if result.spend_range else existing.spend_range
            existing.impressions_range = json.dumps(result.impressions_range) if result.impressions_range else existing.impressions_range
            existing.raw_payload = json.dumps(result.raw)
            existing.fetched_at = now
            session.add(existing)
            persisted.append(existing)
        else:
            ad = Ad(
                platform=platform,
                external_ad_id=result.external_ad_id,
                subject_type=subject_type,
                subject_id=subject_id,
                advertiser_name=result.advertiser_name,
                landing_domain=result.landing_domain or _domain_from_url(result.creative_link_url),
                creative_text=result.creative_text,
                creative_link_url=result.creative_link_url,
                snapshot_url=result.snapshot_url,
                media_type=result.media_type,
                format=None,
                first_shown=result.first_shown,
                last_shown=result.last_shown,
                regions=json.dumps(result.regions),
                spend_range=json.dumps(result.spend_range) if result.spend_range else None,
                impressions_range=json.dumps(result.impressions_range) if result.impressions_range else None,
                raw_payload=json.dumps(result.raw),
                fetched_at=now,
            )
            session.add(ad)
            session.flush()  # get ad.id
            persisted.append(ad)

    session.commit()
    return persisted


def update_flights(
    *,
    session: Session,
    platform: str,
    subject_type: str,
    subject_id: int,
    ad_ids: list[int],          # DB primary keys from upsert_ads
    external_ad_ids: list[str],
) -> None:
    """
    Maintain creative_flights rows:
    - If a creative was last seen and is still active → bump flight_last_seen + seen_count
    - If a creative appears after a gap (was inactive) → open a new flight row
    - Does NOT close flights here; closure happens on the next refresh that omits the creative
      (handled by mark_inactive_flights)
    """
    now = _now()

    for db_id, ext_id in zip(ad_ids, external_ad_ids):
        active_flight = session.exec(
            select(CreativeFlight).where(
                CreativeFlight.platform == platform,
                CreativeFlight.external_ad_id == ext_id,
                CreativeFlight.is_active == True,  # noqa: E712
            )
        ).first()

        if active_flight:
            active_flight.flight_last_seen = now
            active_flight.seen_count += 1
            active_flight.days_live = (now - active_flight.flight_start).days
            session.add(active_flight)
        else:
            flight = CreativeFlight(
                ad_id=db_id,
                platform=platform,
                external_ad_id=ext_id,
                subject_type=subject_type,
                subject_id=subject_id,
                flight_start=now,
                flight_last_seen=now,
                is_active=True,
                days_live=0,
                seen_count=1,
            )
            session.add(flight)

    session.commit()


def mark_inactive_flights(
    *,
    session: Session,
    platform: str,
    subject_id: int,
    seen_external_ids: set[str],
) -> int:
    """
    Mark previously active flights as inactive if their external_ad_id
    was NOT returned in the latest refresh for this platform + subject.
    Returns count of flights closed.
    """
    active_flights = session.exec(
        select(CreativeFlight).where(
            CreativeFlight.platform == platform,
            CreativeFlight.subject_id == subject_id,
            CreativeFlight.is_active == True,  # noqa: E712
        )
    ).all()

    closed = 0
    for flight in active_flights:
        if flight.external_ad_id not in seen_external_ids:
            flight.is_active = False
            session.add(flight)
            closed += 1

    session.commit()
    return closed


def record_run(
    *,
    session: Session,
    connector: str,
    subject_type: str,
    subject_id: int,
    query: Query,
    response: ConnectorResponse,
) -> QueryRun:
    """Write a query_runs row capturing the outcome of one connector call."""
    run = QueryRun(
        connector=connector,
        subject_type=subject_type,
        subject_id=subject_id,
        query_dimension=query.dimension.value,
        query_value=query.value,
        status=response.status.value,
        result_count=len(response.ads),
        message=response.message,
        ran_at=_now(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run
