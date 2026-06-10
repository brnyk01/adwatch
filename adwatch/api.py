from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query as FQuery
from pydantic import BaseModel
from sqlmodel import Session, select

from adwatch.db import create_db, get_session
from adwatch.models import Ad, AdvertiserClient, Competitor, QueryRun
from adwatch.services.refresh import RefreshResult, refresh_all, refresh_subject


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db()
    yield


app = FastAPI(title="AdWatch", version="0.1.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class ClientIn(BaseModel):
    name: str
    landing_domain: str
    meta_page_id: Optional[str] = None
    google_advertiser_id: Optional[str] = None
    notes: Optional[str] = None


class ClientOut(ClientIn):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class CompetitorIn(BaseModel):
    display_name: str
    type: str                           # 'agency' | 'brand'
    registration_name: str
    brand_domain: Optional[str] = None
    meta_page_id: Optional[str] = None
    google_advertiser_id: Optional[str] = None


class CompetitorOut(CompetitorIn):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class RefreshRequest(BaseModel):
    subject_type: Optional[str] = None  # 'client' | 'competitor' | None (all)
    subject_id: Optional[int] = None    # if set, refresh only this subject
    country: str = "SG"
    date_min: Optional[str] = None
    date_max: Optional[str] = None
    connectors: Optional[list[str]] = None  # subset of registry keys


class AdOut(BaseModel):
    id: int
    platform: str
    external_ad_id: str
    subject_type: str
    subject_id: int
    advertiser_name: Optional[str]
    landing_domain: Optional[str]
    creative_text: Optional[str]
    snapshot_url: Optional[str]
    media_type: Optional[str]
    first_shown: Optional[str]
    last_shown: Optional[str]
    spend_range: Optional[str]
    impressions_range: Optional[str]
    fetched_at: datetime

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: int
    connector: str
    subject_type: str
    subject_id: int
    query_dimension: str
    query_value: str
    status: str
    result_count: int
    message: str
    ran_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

@app.get("/clients", response_model=list[ClientOut])
def list_clients(session: Session = Depends(get_session)):
    return session.exec(select(AdvertiserClient)).all()


@app.post("/clients", response_model=ClientOut, status_code=201)
def create_client(body: ClientIn, session: Session = Depends(get_session)):
    client = AdvertiserClient(**body.model_dump())
    session.add(client)
    session.commit()
    session.refresh(client)
    return client


@app.get("/clients/{client_id}", response_model=ClientOut)
def get_client(client_id: int, session: Session = Depends(get_session)):
    obj = session.get(AdvertiserClient, client_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Client not found")
    return obj


@app.patch("/clients/{client_id}", response_model=ClientOut)
def update_client(client_id: int, body: ClientIn, session: Session = Depends(get_session)):
    obj = session.get(AdvertiserClient, client_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Client not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@app.delete("/clients/{client_id}", status_code=204)
def delete_client(client_id: int, session: Session = Depends(get_session)):
    obj = session.get(AdvertiserClient, client_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Client not found")
    session.delete(obj)
    session.commit()


# ---------------------------------------------------------------------------
# Competitors
# ---------------------------------------------------------------------------

@app.get("/competitors", response_model=list[CompetitorOut])
def list_competitors(session: Session = Depends(get_session)):
    return session.exec(select(Competitor)).all()


@app.post("/competitors", response_model=CompetitorOut, status_code=201)
def create_competitor(body: CompetitorIn, session: Session = Depends(get_session)):
    comp = Competitor(**body.model_dump())
    session.add(comp)
    session.commit()
    session.refresh(comp)
    return comp


@app.get("/competitors/{comp_id}", response_model=CompetitorOut)
def get_competitor(comp_id: int, session: Session = Depends(get_session)):
    obj = session.get(Competitor, comp_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Competitor not found")
    return obj


@app.patch("/competitors/{comp_id}", response_model=CompetitorOut)
def update_competitor(comp_id: int, body: CompetitorIn, session: Session = Depends(get_session)):
    obj = session.get(Competitor, comp_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Competitor not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@app.delete("/competitors/{comp_id}", status_code=204)
def delete_competitor(comp_id: int, session: Session = Depends(get_session)):
    obj = session.get(Competitor, comp_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Competitor not found")
    session.delete(obj)
    session.commit()


# ---------------------------------------------------------------------------
# Refresh
# ---------------------------------------------------------------------------

@app.post("/refresh")
def trigger_refresh(body: RefreshRequest) -> dict:
    """
    Manual refresh. Runs connectors and persists results.
    - body.subject_id set  → refresh one subject
    - body.subject_id None → refresh all subjects of body.subject_type (or all types)
    """
    if body.subject_id is not None:
        if not body.subject_type:
            raise HTTPException(status_code=422, detail="subject_type required when subject_id is set")
        results: list[RefreshResult] = refresh_subject(
            subject_type=body.subject_type,
            subject_id=body.subject_id,
            country=body.country,
            date_min=body.date_min,
            date_max=body.date_max,
            connector_filter=body.connectors,
        )
        return {"results": [r.__dict__ for r in results]}

    all_results = refresh_all(
        country=body.country,
        subject_type=body.subject_type,
        connector_filter=body.connectors,
    )
    return {
        "results": {
            k: [r.__dict__ for r in v]
            for k, v in all_results.items()
        }
    }


# ---------------------------------------------------------------------------
# Ads
# ---------------------------------------------------------------------------

@app.get("/ads", response_model=list[AdOut])
def list_ads(
    subject_type: Optional[str] = FQuery(default=None),
    subject_id: Optional[int] = FQuery(default=None),
    platform: Optional[str] = FQuery(default=None),
    limit: int = FQuery(default=100, le=500),
    offset: int = FQuery(default=0),
    session: Session = Depends(get_session),
):
    stmt = select(Ad)
    if subject_type:
        stmt = stmt.where(Ad.subject_type == subject_type)
    if subject_id is not None:
        stmt = stmt.where(Ad.subject_id == subject_id)
    if platform:
        stmt = stmt.where(Ad.platform == platform)
    stmt = stmt.order_by(Ad.fetched_at.desc()).offset(offset).limit(limit)
    return session.exec(stmt).all()


# ---------------------------------------------------------------------------
# Run history
# ---------------------------------------------------------------------------

@app.get("/runs", response_model=list[RunOut])
def list_runs(
    connector: Optional[str] = FQuery(default=None),
    subject_type: Optional[str] = FQuery(default=None),
    subject_id: Optional[int] = FQuery(default=None),
    limit: int = FQuery(default=50, le=200),
    session: Session = Depends(get_session),
):
    stmt = select(QueryRun)
    if connector:
        stmt = stmt.where(QueryRun.connector == connector)
    if subject_type:
        stmt = stmt.where(QueryRun.subject_type == subject_type)
    if subject_id is not None:
        stmt = stmt.where(QueryRun.subject_id == subject_id)
    stmt = stmt.order_by(QueryRun.ran_at.desc()).limit(limit)
    return session.exec(stmt).all()


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------

class ResolveOut(BaseModel):
    platform_id: Optional[str]
    message: str

# keep old name as alias for backwards compat
MetaResolveOut = ResolveOut


@app.get("/resolve/meta", response_model=ResolveOut)
def resolve_meta_page_id(
    domain: Optional[str] = FQuery(default=None),
    name: Optional[str] = FQuery(default=None),
):
    """
    Best-effort resolution of a brand domain or name → Meta page_id.
    Pass ?domain=example.com OR ?name=Brand Name.
    Returns the first matching page_id from the Ad Library, or null if not found.
    """
    if not domain and not name:
        raise HTTPException(status_code=422, detail="Provide ?domain= or ?name=")

    try:
        from adwatch.connectors.meta import MetaConnector
        from adwatch.config import settings

        if not settings.meta_access_token:
            return ResolveOut(platform_id=None, message="Meta: META_ACCESS_TOKEN not configured")

        connector = MetaConnector()
        search_value = domain or name
        page_id = connector._resolve_domain_to_page_id(search_value)

        if page_id:
            return ResolveOut(platform_id=page_id, message=f"Meta: found page_id {page_id} for '{search_value}'")
        return ResolveOut(platform_id=None, message=f"Meta: no page_id found for '{search_value}' — enter manually")
    except Exception as exc:
        return ResolveOut(platform_id=None, message=f"Meta: lookup failed — {str(exc)[:120]}")


@app.get("/resolve/google", response_model=ResolveOut)
def resolve_google_advertiser_id(
    domain: Optional[str] = FQuery(default=None),
    name: Optional[str] = FQuery(default=None),
):
    """
    Best-effort resolution of a brand domain or name → Google advertiser_id
    via the BigQuery public dataset (EEA ads). Returns null if credentials not set.
    """
    if not domain and not name:
        raise HTTPException(status_code=422, detail="Provide ?domain= or ?name=")

    from adwatch.config import settings
    import os

    creds = settings.google_application_credentials
    adc = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
    if not creds and not os.path.exists(adc):
        return ResolveOut(platform_id=None, message="Google credentials not configured")

    try:
        from google.cloud import bigquery as bq  # noqa

        if creds and os.path.exists(creds):
            client = bq.Client.from_service_account_json(creds)
        else:
            client = bq.Client()

        pattern = f"%{(domain or name).lower()}%"
        field = "advertiser_url" if domain else "advertiser_name"
        sql = f"""
            SELECT advertiser_id, advertiser_name, advertiser_url
            FROM `bigquery-public-data.google_ads_transparency_center.creative_stats`
            WHERE LOWER({field}) LIKE @pattern
            LIMIT 1
        """
        job = client.query(sql, job_config=bq.QueryJobConfig(
            query_parameters=[bq.ScalarQueryParameter("pattern", "STRING", pattern)]
        ))
        rows = list(job.result())
        if rows:
            aid = str(rows[0].advertiser_id)
            return ResolveOut(platform_id=aid, message=f"Found advertiser_id {aid} for '{domain or name}'")
        return ResolveOut(platform_id=None, message=f"No Google advertiser_id found for '{domain or name}'")
    except Exception as exc:
        return ResolveOut(platform_id=None, message=f"BigQuery lookup failed: {str(exc)[:120]}")


class PatchIdsIn(BaseModel):
    meta_page_id: Optional[str] = None
    google_advertiser_id: Optional[str] = None


@app.patch("/clients/{client_id}/ids", response_model=ClientOut)
def patch_client_ids(client_id: int, body: PatchIdsIn, session: Session = Depends(get_session)):
    """Update just the platform IDs on a client without touching other fields."""
    obj = session.get(AdvertiserClient, client_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Client not found")
    if body.meta_page_id is not None:
        obj.meta_page_id = body.meta_page_id or None
    if body.google_advertiser_id is not None:
        obj.google_advertiser_id = body.google_advertiser_id or None
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@app.patch("/competitors/{comp_id}/ids", response_model=CompetitorOut)
def patch_competitor_ids(comp_id: int, body: PatchIdsIn, session: Session = Depends(get_session)):
    """Update just the platform IDs on a competitor without touching other fields."""
    obj = session.get(Competitor, comp_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Competitor not found")
    if body.meta_page_id is not None:
        obj.meta_page_id = body.meta_page_id or None
    if body.google_advertiser_id is not None:
        obj.google_advertiser_id = body.google_advertiser_id or None
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj
