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

# TikTok Commercial Content Library covers EEA + UK + Switzerland only
_CCL_COUNTRIES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI",
    "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",  # EEA
    "GB",   # UK
    "CH",   # Switzerland
}

_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
_SEARCH_URL = "https://open.tiktokapis.com/v2/research/adlib/ad/query/"
_LIBRARY_UI = "https://library.tiktok.com/ads?region={country}&keyword={q}"


def _manual_url(q: Query) -> str:
    return _LIBRARY_UI.format(
        country=q.country.upper(),
        q=urllib.parse.quote(q.value),
    )


def _parse_ad(raw: dict) -> AdResult:
    return AdResult(
        external_ad_id=str(raw.get("id", "")),
        advertiser_name=raw.get("advertiser_name"),
        landing_domain=None,
        creative_text=raw.get("video_info", {}).get("description"),
        creative_link_url=raw.get("redirect_url"),
        snapshot_url=raw.get("video_info", {}).get("cover_image_url"),
        media_type="video",
        first_shown=raw.get("first_shown_date"),
        last_shown=raw.get("last_shown_date"),
        regions=raw.get("countries_shown", []),
        spend_range=None,  # TikTok does not publish spend
        impressions_range=(
            {"lower": raw["reach"]["lower"], "upper": raw["reach"]["upper"]}
            if raw.get("reach") else None
        ),
        raw=raw,
    )


class TikTokConnector(AbstractConnector):
    name = "tiktok"
    supported_dimensions = {QueryDimension.NAME}

    def __init__(self):
        self._key = settings.tiktok_client_key
        self._secret = settings.tiktok_client_secret
        self._access_token: Optional[str] = None

    def _is_ccl(self, country: str) -> bool:
        return country.upper() in _CCL_COUNTRIES

    def _get_token(self) -> str:
        resp = httpx.post(
            _TOKEN_URL,
            data={
                "client_key": self._key,
                "client_secret": self._secret,
                "grant_type": "client_credentials",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _token(self) -> str:
        if not self._access_token:
            self._access_token = self._get_token()
        return self._access_token

    def _search(self, q: Query) -> list[dict]:
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "filters": {
                "country_code": [q.country.upper()],
                "advertiser_name": q.value,
                "ad_active_status": "ALL",
            },
            "max_count": 100,
        }
        if q.date_min:
            payload["filters"]["create_date_start"] = q.date_min
        if q.date_max:
            payload["filters"]["create_date_end"] = q.date_max

        ads: list[dict] = []
        cursor: Optional[str] = None

        for _ in range(5):  # max 5 pages
            if cursor:
                payload["cursor"] = cursor
            resp = httpx.post(_SEARCH_URL, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json().get("data", {})
            ads.extend(data.get("ads", []))
            if not data.get("has_more"):
                break
            cursor = data.get("cursor")

        return ads

    def fetch(self, q: Query) -> ConnectorResponse:
        if not self._key or not self._secret:
            return ConnectorResponse(
                status=Status.ERROR,
                message="TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET not configured",
                manual_url=_manual_url(q),
            )

        if not self._is_ccl(q.country):
            return ConnectorResponse(
                status=Status.NO_DATA,
                message=(
                    f"TikTok Commercial Content Library covers EEA, UK, and Switzerland only. "
                    f"{q.country.upper()} is not supported via the official API."
                ),
                manual_url=_manual_url(q),
            )

        try:
            raw_ads = self._search(q)
        except Exception as exc:
            # Token may have expired — reset and surface error
            self._access_token = None
            return ConnectorResponse(
                status=Status.ERROR,
                message=str(exc),
                manual_url=_manual_url(q),
            )

        if not raw_ads:
            return ConnectorResponse(
                status=Status.NO_DATA,
                message="No ads found in TikTok Commercial Content Library.",
                manual_url=_manual_url(q),
            )

        return ConnectorResponse(
            status=Status.OK,
            ads=[_parse_ad(a) for a in raw_ads],
            message=f"{len(raw_ads)} ad(s) retrieved",
            manual_url=_manual_url(q),
        )
