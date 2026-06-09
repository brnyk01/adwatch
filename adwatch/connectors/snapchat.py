"""
Snapchat Political & Advocacy Ads connector.
Ingests the official public CSV downloaded from:
  https://www.snap.com/en-US/political-ads
No credentials required — the CSV is a public download.
"""

import csv
import io
from pathlib import Path
from typing import Optional

import httpx

from adwatch.connectors.base import (
    AbstractConnector,
    AdResult,
    ConnectorResponse,
    Query,
    QueryDimension,
    Status,
)

# Snap publishes one CSV per year; we fetch the most recent two
_CSV_URLS = [
    "https://storage.googleapis.com/snap-political-ads/political_ads_2025.csv",
    "https://storage.googleapis.com/snap-political-ads/political_ads_2024.csv",
]
_UI_URL = "https://www.snap.com/en-US/political-ads"

# Optional local cache directory
_CACHE_DIR = Path.home() / ".adwatch_cache" / "snapchat"


def _fetch_csv(url: str) -> list[dict]:
    resp = httpx.get(url, timeout=30, follow_redirects=True)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    reader = csv.DictReader(io.StringIO(resp.text))
    return list(reader)


def _row_to_ad(row: dict) -> AdResult:
    return AdResult(
        external_ad_id=row.get("AdID", "") or row.get("AdId", ""),
        advertiser_name=row.get("PayingAdvertiserName") or row.get("CandidateName"),
        landing_domain=None,
        creative_text=row.get("AdTitle"),
        creative_link_url=row.get("AdTargetingURL"),
        snapshot_url=None,
        media_type=None,
        first_shown=row.get("StartDate") or row.get("AdStartDate"),
        last_shown=row.get("EndDate") or row.get("AdEndDate"),
        regions=[row.get("CountryCode", "").upper()] if row.get("CountryCode") else [],
        spend_range=(
            {"currency": row.get("Currency", "USD"), "amount": row.get("Spend")}
            if row.get("Spend") else None
        ),
        impressions_range=(
            {"impressions": row.get("Impressions")}
            if row.get("Impressions") else None
        ),
        raw=row,
    )


class SnapchatConnector(AbstractConnector):
    """
    Ingests Snapchat's official political/advocacy ads CSV.
    Matches rows by advertiser name (case-insensitive substring).
    Political ads only — no commercial ad library exists for Snapchat.
    """

    name = "snapchat"
    supported_dimensions = {QueryDimension.NAME}

    def _load_rows(self) -> list[dict]:
        rows: list[dict] = []
        for url in _CSV_URLS:
            try:
                rows.extend(_fetch_csv(url))
            except Exception:
                pass
        return rows

    def fetch(self, q: Query) -> ConnectorResponse:
        try:
            all_rows = self._load_rows()
        except Exception as exc:
            return ConnectorResponse(
                status=Status.ERROR,
                message=f"Failed to download Snapchat political ads CSV: {exc}",
                manual_url=_UI_URL,
            )

        if not all_rows:
            return ConnectorResponse(
                status=Status.NO_DATA,
                message="Snapchat political ads CSV returned no rows (URL may have changed).",
                manual_url=_UI_URL,
            )

        term = q.value.lower()
        matched = [
            row for row in all_rows
            if term in (row.get("PayingAdvertiserName") or row.get("CandidateName") or "").lower()
        ]

        if not matched:
            return ConnectorResponse(
                status=Status.NO_DATA,
                message=(
                    f"No Snapchat political ads found for '{q.value}'. "
                    "Note: Snapchat only publishes political/advocacy ads — commercial ads are not available."
                ),
                manual_url=_UI_URL,
            )

        return ConnectorResponse(
            status=Status.OK,
            ads=[_row_to_ad(r) for r in matched],
            message=f"{len(matched)} political/advocacy ad(s) found",
            manual_url=_UI_URL,
        )
