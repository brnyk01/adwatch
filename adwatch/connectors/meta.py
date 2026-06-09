import time
import urllib.parse
from typing import Optional

import httpx

from adwatch.config import settings
from adwatch.connectors.base import (
    AbstractConnector,
    AdResult,
    ConnectorResponse,
    Query,
    QueryDimension,
    Status,
)

_EU_COUNTRIES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI",
    "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK", "GB",  # UK (DSA 1-yr archive)
}

_BASE_FIELDS = (
    "id,ad_creative_bodies,ad_creative_link_titles,"
    "ad_creative_link_captions,ad_creative_link_urls,"
    "page_id,page_name,ad_delivery_start_time,ad_delivery_stop_time,"
    "publisher_platforms,ad_snapshot_url"
)
_EU_EXTRA_FIELDS = ",spend,impressions,currency,eu_total_reach"

_LIBRARY_UI = "https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country={country}&q={q}"


def _manual_url(q: Query) -> str:
    return _LIBRARY_UI.format(
        country=q.country,
        q=urllib.parse.quote(q.value),
    )


def _extract_domain(urls: list[str]) -> Optional[str]:
    for u in urls:
        try:
            return urllib.parse.urlparse(u).netloc.lstrip("www.")
        except Exception:
            pass
    return None


def _parse_ad(raw: dict) -> AdResult:
    bodies = raw.get("ad_creative_bodies") or []
    link_urls = raw.get("ad_creative_link_urls") or []
    link_titles = raw.get("ad_creative_link_titles") or []

    snapshot = raw.get("ad_snapshot_url")

    spend = raw.get("spend")  # dict with lower_bound/upper_bound
    impressions = raw.get("impressions")

    return AdResult(
        external_ad_id=str(raw["id"]),
        advertiser_name=raw.get("page_name"),
        landing_domain=_extract_domain(link_urls),
        creative_text=(bodies[0] if bodies else None) or (link_titles[0] if link_titles else None),
        creative_link_url=(link_urls[0] if link_urls else None),
        snapshot_url=snapshot,
        media_type=None,
        first_shown=raw.get("ad_delivery_start_time"),
        last_shown=raw.get("ad_delivery_stop_time"),
        regions=[],
        spend_range=spend,
        impressions_range=impressions,
        raw=raw,
    )


class MetaConnector(AbstractConnector):
    name = "meta"
    supported_dimensions = {QueryDimension.PAGE_ID, QueryDimension.NAME, QueryDimension.DOMAIN}

    def __init__(self):
        self._token = settings.meta_access_token
        self._version = settings.meta_api_version
        self._base = f"https://graph.facebook.com/{self._version}"

    def _is_eu(self, country: str) -> bool:
        return country.upper() in _EU_COUNTRIES

    def _fields(self, country: str) -> str:
        if self._is_eu(country):
            return _BASE_FIELDS + _EU_EXTRA_FIELDS
        return _BASE_FIELDS

    def _get(self, params: dict, retries: int = 3) -> dict:
        params["access_token"] = self._token
        url = f"{self._base}/ads_archive"
        for attempt in range(retries):
            resp = httpx.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            data = resp.json()
            # Rate limit: error code 613
            if resp.status_code in (400, 429):
                code = (data.get("error") or {}).get("code")
                if code == 613 and attempt < retries - 1:
                    time.sleep(20 * (attempt + 1))
                    continue
            raise RuntimeError(f"Meta API error {resp.status_code}: {data}")
        raise RuntimeError("Meta API rate limit exceeded after retries")

    def _paginate(self, params: dict, limit: int = 200) -> list[dict]:
        ads: list[dict] = []
        params = {**params, "limit": 25}
        while True:
            data = self._get(params)
            ads.extend(data.get("data", []))
            if len(ads) >= limit:
                break
            paging = data.get("paging", {})
            cursor = (paging.get("cursors") or {}).get("after")
            if not cursor or not paging.get("next"):
                break
            params["after"] = cursor
        return ads[:limit]

    def _resolve_domain_to_page_id(self, domain: str) -> Optional[str]:
        """
        Meta has no native domain→page_id lookup via the Ad Library API.
        Search by the brand name (strip TLD) and return the first page_id hit.
        This is best-effort; callers should let users override with a known page_id.
        """
        brand = domain.split(".")[0]
        params = {
            "search_terms": brand,
            "ad_type": "ALL",
            "ad_reached_countries": '["SG","US","GB","DE","FR"]',
            "fields": "page_id,page_name",
            "limit": 5,
        }
        try:
            data = self._get(params)
            for ad in data.get("data", []):
                if ad.get("page_id"):
                    return str(ad["page_id"])
        except Exception:
            pass
        return None

    def fetch(self, q: Query) -> ConnectorResponse:
        if not self._token:
            return ConnectorResponse(
                status=Status.ERROR,
                message="META_ACCESS_TOKEN not configured",
                manual_url=_manual_url(q),
            )

        country = q.country.upper()

        # Build base params
        params: dict = {
            "ad_type": "ALL",
            "ad_reached_countries": f'["{country}"]',
            "ad_active_status": "ALL",
            "fields": self._fields(country),
        }

        if q.date_min:
            params["ad_delivery_date_min"] = q.date_min
        if q.date_max:
            params["ad_delivery_date_max"] = q.date_max

        # Dimension routing
        if q.dimension == QueryDimension.PAGE_ID:
            params["search_page_ids"] = q.value

        elif q.dimension == QueryDimension.NAME:
            params["search_terms"] = q.value

        elif q.dimension == QueryDimension.DOMAIN:
            page_id = _resolve_domain_to_page_id_via_connector(self, q.value)
            if page_id:
                params["search_page_ids"] = page_id
            else:
                # Fall back to keyword search on domain root
                params["search_terms"] = q.value.split(".")[0]

        try:
            raw_ads = self._paginate(params)
        except RuntimeError as exc:
            return ConnectorResponse(
                status=Status.ERROR,
                message=str(exc),
                manual_url=_manual_url(q),
            )

        if not raw_ads:
            msg = (
                "Meta Ad Library API returned no results. "
                "For non-EU commercial ads (e.g. Singapore-only), this is expected — "
                "the API only surfaces EU/UK commercial ads and political ads globally."
            )
            return ConnectorResponse(
                status=Status.NO_DATA,
                message=msg,
                manual_url=_manual_url(q),
            )

        ads = [_parse_ad(a) for a in raw_ads]
        return ConnectorResponse(
            status=Status.OK,
            ads=ads,
            message=f"{len(ads)} ad(s) retrieved",
            manual_url=_manual_url(q),
        )


def _resolve_domain_to_page_id_via_connector(connector: MetaConnector, domain: str) -> Optional[str]:
    return connector._resolve_domain_to_page_id(domain)
