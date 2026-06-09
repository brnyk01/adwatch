from datetime import datetime
from typing import Optional
from sqlmodel import Field, SQLModel
import json


class AdvertiserClient(SQLModel, table=True):
    __tablename__ = "advertisers_clients"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    landing_domain: str
    meta_page_id: Optional[str] = None
    google_advertiser_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Competitor(SQLModel, table=True):
    __tablename__ = "competitors"

    id: Optional[int] = Field(default=None, primary_key=True)
    display_name: str
    type: str  # 'agency' | 'brand'
    registration_name: str
    brand_domain: Optional[str] = None
    meta_page_id: Optional[str] = None
    google_advertiser_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Ad(SQLModel, table=True):
    __tablename__ = "ads"

    id: Optional[int] = Field(default=None, primary_key=True)
    platform: str
    external_ad_id: str
    subject_type: str  # 'client' | 'competitor'
    subject_id: int
    advertiser_name: Optional[str] = None
    landing_domain: Optional[str] = None
    creative_text: Optional[str] = None
    creative_link_url: Optional[str] = None
    snapshot_url: Optional[str] = None
    media_type: Optional[str] = None
    format: Optional[str] = None
    first_shown: Optional[str] = None
    last_shown: Optional[str] = None
    regions: str = "[]"          # JSON array
    spend_range: Optional[str] = None      # JSON object
    impressions_range: Optional[str] = None  # JSON object
    raw_payload: str = "{}"      # JSON object
    fetched_at: datetime = Field(default_factory=datetime.utcnow)


class QueryRun(SQLModel, table=True):
    __tablename__ = "query_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    connector: str
    subject_type: str
    subject_id: int
    query_dimension: str   # 'domain' | 'name' | 'page_id'
    query_value: str
    status: str            # 'ok' | 'no_official_api' | 'no_data' | 'error'
    result_count: int = 0
    message: str = ""
    ran_at: datetime = Field(default_factory=datetime.utcnow)


class CreativeFlight(SQLModel, table=True):
    __tablename__ = "creative_flights"

    id: Optional[int] = Field(default=None, primary_key=True)
    ad_id: int = Field(foreign_key="ads.id")
    platform: str
    external_ad_id: str
    subject_type: str
    subject_id: int
    flight_start: datetime
    flight_last_seen: datetime
    is_active: bool = True
    days_live: int = 0
    seen_count: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
