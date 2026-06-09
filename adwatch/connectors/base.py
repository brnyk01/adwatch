from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class QueryDimension(str, Enum):
    DOMAIN = "domain"
    NAME = "name"
    PAGE_ID = "page_id"


class Status(str, Enum):
    OK = "ok"
    NO_OFFICIAL_API = "no_official_api"
    NO_DATA = "no_data"
    ERROR = "error"


@dataclass
class Query:
    dimension: QueryDimension
    value: str
    country: str = "SG"
    date_min: Optional[str] = None   # YYYY-MM-DD
    date_max: Optional[str] = None


@dataclass
class AdResult:
    external_ad_id: str
    advertiser_name: Optional[str]
    landing_domain: Optional[str]
    creative_text: Optional[str]
    creative_link_url: Optional[str]
    snapshot_url: Optional[str]
    media_type: Optional[str]
    first_shown: Optional[str]
    last_shown: Optional[str]
    regions: list[str]
    spend_range: Optional[dict]
    impressions_range: Optional[dict]
    raw: dict


@dataclass
class ConnectorResponse:
    status: Status
    ads: list[AdResult] = field(default_factory=list)
    message: str = ""
    manual_url: Optional[str] = None


class AbstractConnector:
    name: str = ""
    supported_dimensions: set[QueryDimension] = set()

    def supports(self, q: Query) -> bool:
        return q.dimension in self.supported_dimensions

    def fetch(self, q: Query) -> ConnectorResponse:
        raise NotImplementedError
