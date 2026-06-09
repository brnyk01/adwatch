"""
Manual refresh orchestrator.
Runs all applicable connectors for a subject (client or competitor),
persists results via store.py, and returns a per-connector summary.
"""

from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session

from adwatch.connectors.base import Query, QueryDimension, Status
from adwatch.db import engine
from adwatch.models import AdvertiserClient, Competitor
from adwatch.registry import CONNECTOR_REGISTRY
from adwatch.services import store


@dataclass
class RefreshResult:
    connector: str
    status: str
    result_count: int
    message: str
    manual_url: Optional[str]


def _build_queries(subject: AdvertiserClient | Competitor) -> dict[str, Query]:
    """
    Return a mapping of connector_name → best Query for that connector.
    Connectors declare supported_dimensions; we pick the best dimension available.
    """
    queries: dict[str, Query] = {}

    for name, connector in CONNECTOR_REGISTRY.items():
        q: Optional[Query] = None

        # PAGE_ID takes priority if available
        meta_page_id = getattr(subject, "meta_page_id", None)
        if QueryDimension.PAGE_ID in connector.supported_dimensions and meta_page_id:
            q = Query(dimension=QueryDimension.PAGE_ID, value=meta_page_id)

        # DOMAIN next
        elif QueryDimension.DOMAIN in connector.supported_dimensions:
            domain = getattr(subject, "landing_domain", None) or getattr(subject, "brand_domain", None)
            if domain:
                q = Query(dimension=QueryDimension.DOMAIN, value=domain)

        # NAME fallback
        if q is None and QueryDimension.NAME in connector.supported_dimensions:
            name_val = getattr(subject, "name", None) or getattr(subject, "display_name", None)
            if name_val:
                q = Query(dimension=QueryDimension.NAME, value=name_val)

        if q is not None:
            queries[name] = q

    return queries


def refresh_subject(
    *,
    subject_type: str,   # 'client' | 'competitor'
    subject_id: int,
    country: str = "SG",
    date_min: Optional[str] = None,
    date_max: Optional[str] = None,
    connector_filter: Optional[list[str]] = None,
) -> list[RefreshResult]:
    """
    Run all (or a filtered subset of) connectors for a single subject.
    Persists ads + flight data + run history.
    Returns one RefreshResult per connector attempted.
    """
    with Session(engine) as session:
        # Load subject
        if subject_type == "client":
            subject = session.get(AdvertiserClient, subject_id)
        else:
            subject = session.get(Competitor, subject_id)

        if not subject:
            return [RefreshResult(
                connector="__system__",
                status="error",
                result_count=0,
                message=f"{subject_type} id={subject_id} not found",
                manual_url=None,
            )]

        queries = _build_queries(subject)
        results: list[RefreshResult] = []

        for connector_name, base_query in queries.items():
            if connector_filter and connector_name not in connector_filter:
                continue

            connector = CONNECTOR_REGISTRY[connector_name]

            # Apply country + date range to the query
            q = Query(
                dimension=base_query.dimension,
                value=base_query.value,
                country=country,
                date_min=date_min,
                date_max=date_max,
            )

            response = connector.fetch(q)

            # Persist run record
            store.record_run(
                session=session,
                connector=connector_name,
                subject_type=subject_type,
                subject_id=subject_id,
                query=q,
                response=response,
            )

            # Persist ads only on OK
            if response.status == Status.OK and response.ads:
                persisted = store.upsert_ads(
                    session=session,
                    platform=connector_name,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    ads=response.ads,
                )
                ad_db_ids = [a.id for a in persisted]
                ext_ids = [a.external_ad_id for a in response.ads]

                store.update_flights(
                    session=session,
                    platform=connector_name,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    ad_ids=ad_db_ids,
                    external_ad_ids=ext_ids,
                )
                store.mark_inactive_flights(
                    session=session,
                    platform=connector_name,
                    subject_id=subject_id,
                    seen_external_ids=set(ext_ids),
                )

            results.append(RefreshResult(
                connector=connector_name,
                status=response.status.value,
                result_count=len(response.ads),
                message=response.message,
                manual_url=response.manual_url,
            ))

    return results


def refresh_all(
    *,
    country: str = "SG",
    subject_type: Optional[str] = None,
    connector_filter: Optional[list[str]] = None,
) -> dict[str, list[RefreshResult]]:
    """
    Refresh every client and/or competitor in the DB.
    Returns {'{type}:{id}': [RefreshResult, ...]}
    """
    from sqlmodel import select as sql_select

    results: dict[str, list[RefreshResult]] = {}

    with Session(engine) as session:
        if subject_type in (None, "client"):
            clients = session.exec(sql_select(AdvertiserClient)).all()
            for c in clients:
                key = f"client:{c.id}"
                results[key] = refresh_subject(
                    subject_type="client",
                    subject_id=c.id,
                    country=country,
                    connector_filter=connector_filter,
                )

        if subject_type in (None, "competitor"):
            competitors = session.exec(sql_select(Competitor)).all()
            for comp in competitors:
                key = f"competitor:{comp.id}"
                results[key] = refresh_subject(
                    subject_type="competitor",
                    subject_id=comp.id,
                    country=country,
                    connector_filter=connector_filter,
                )

    return results
