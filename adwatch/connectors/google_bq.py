import os
from typing import Optional

from adwatch.config import settings
from adwatch.connectors.base import (
    AbstractConnector,
    AdResult,
    ConnectorResponse,
    Query,
    QueryDimension,
    Status,
)

_EEA_COUNTRIES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI",
    "FR", "GR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK",
}

_CREATIVE_STATS_TABLE = "bigquery-public-data.google_ads_transparency_center.creative_stats"
_POLITICAL_ADVERTISER_TABLE = "bigquery-public-data.google_political_ads.advertiser_stats"
_POLITICAL_CREATIVE_TABLE = "bigquery-public-data.google_political_ads.creative_stats"

_UI_BASE = "https://adstransparency.google.com"


def _ui_url(q: Query) -> str:
    region = q.country.upper()
    if q.dimension == QueryDimension.DOMAIN:
        return f"{_UI_BASE}/?region={region}&domain={q.value}"
    return f"{_UI_BASE}/?region={region}&advertiser_name={q.value}"


class GoogleBigQueryConnector(AbstractConnector):
    """
    Queries the official Google Ads Transparency Center BigQuery public dataset
    (EEA-served ads) and the Google Political Ads public dataset (global, 35+ countries).
    Requires a Google Cloud service-account JSON with BigQuery read access to public datasets.
    """

    name = "google_bq"
    supported_dimensions = {QueryDimension.DOMAIN, QueryDimension.NAME}

    def _client(self):
        try:
            from google.cloud import bigquery
        except ImportError:
            raise RuntimeError("google-cloud-bigquery not installed")

        creds_path = settings.google_application_credentials
        if creds_path and os.path.exists(creds_path):
            return bigquery.Client.from_service_account_json(creds_path)
        # Falls back to Application Default Credentials (gcloud auth)
        return bigquery.Client()

    def _is_eea(self, country: str) -> bool:
        return country.upper() in _EEA_COUNTRIES

    def _query_creative_stats(self, q: Query) -> list[AdResult]:
        """EEA commercial ads from google_ads_transparency_center."""
        client = self._client()

        if q.dimension == QueryDimension.DOMAIN:
            filter_clause = "LOWER(advertiser_url) LIKE @pattern"
            params = [
                ("pattern", "STRING", f"%{q.value.lower()}%"),
                ("region", "STRING", q.country.upper()),
            ]
        else:
            filter_clause = "LOWER(advertiser_name) LIKE @pattern"
            params = [
                ("pattern", "STRING", f"%{q.value.lower()}%"),
                ("region", "STRING", q.country.upper()),
            ]

        date_filter = ""
        if q.date_min:
            date_filter += " AND DATE(last_shown_date) >= @date_min"
            params.append(("date_min", "DATE", q.date_min))
        if q.date_max:
            date_filter += " AND DATE(last_shown_date) <= @date_max"
            params.append(("date_max", "DATE", q.date_max))

        sql = f"""
            SELECT
                creative_id,
                advertiser_id,
                advertiser_name,
                advertiser_url,
                ad_format_type,
                DATE(first_shown_date) AS first_shown,
                DATE(last_shown_date)  AS last_shown,
                (
                    SELECT STRING_AGG(rs.region_code)
                    FROM UNNEST(region_stats) AS rs
                    WHERE rs.region_code = @region
                ) AS matched_region
            FROM `{_CREATIVE_STATS_TABLE}`
            WHERE {filter_clause}
              AND EXISTS (
                  SELECT 1 FROM UNNEST(region_stats) AS rs
                  WHERE rs.region_code = @region
              )
              {date_filter}
            ORDER BY last_shown_date DESC
            LIMIT 200
        """

        from google.cloud import bigquery as bq

        job_config = bq.QueryJobConfig(
            query_parameters=[
                bq.ScalarQueryParameter(name, type_, value)
                for name, type_, value in params
            ]
        )
        rows = list(client.query(sql, job_config=job_config).result())

        return [
            AdResult(
                external_ad_id=str(row.creative_id),
                advertiser_name=row.advertiser_name,
                landing_domain=_strip_domain(row.advertiser_url),
                creative_text=None,
                creative_link_url=row.advertiser_url,
                snapshot_url=None,
                media_type=row.ad_format_type,
                first_shown=str(row.first_shown) if row.first_shown else None,
                last_shown=str(row.last_shown) if row.last_shown else None,
                regions=[q.country.upper()],
                spend_range=None,
                impressions_range=None,
                raw=dict(row),
            )
            for row in rows
        ]

    def _query_political(self, q: Query) -> list[AdResult]:
        """Political ads from google_political_ads (global, 35+ countries)."""
        client = self._client()

        if q.dimension == QueryDimension.DOMAIN:
            filter_clause = "LOWER(a.advertiser_name) LIKE @pattern"
        else:
            filter_clause = "LOWER(a.advertiser_name) LIKE @pattern"

        params = [("pattern", "STRING", f"%{q.value.lower()}%")]

        date_filter = ""
        if q.date_min:
            date_filter += " AND DATE(c.date_range_start) >= @date_min"
            params.append(("date_min", "DATE", q.date_min))
        if q.date_max:
            date_filter += " AND DATE(c.date_range_end) <= @date_max"
            params.append(("date_max", "DATE", q.date_max))

        sql = f"""
            SELECT
                c.creative_id,
                a.advertiser_id,
                a.advertiser_name,
                c.ad_type,
                c.date_range_start,
                c.date_range_end,
                c.regions,
                c.spend_usd
            FROM `{_POLITICAL_CREATIVE_TABLE}` c
            JOIN `{_POLITICAL_ADVERTISER_TABLE}` a USING (advertiser_id)
            WHERE {filter_clause}
              {date_filter}
            ORDER BY c.date_range_end DESC
            LIMIT 200
        """

        from google.cloud import bigquery as bq

        job_config = bq.QueryJobConfig(
            query_parameters=[
                bq.ScalarQueryParameter(name, type_, value)
                for name, type_, value in params
            ]
        )
        rows = list(client.query(sql, job_config=job_config).result())

        return [
            AdResult(
                external_ad_id=f"gpol_{row.creative_id}",
                advertiser_name=row.advertiser_name,
                landing_domain=None,
                creative_text=None,
                creative_link_url=None,
                snapshot_url=None,
                media_type=row.ad_type,
                first_shown=str(row.date_range_start) if row.date_range_start else None,
                last_shown=str(row.date_range_end) if row.date_range_end else None,
                regions=row.regions or [],
                spend_range={"usd": row.spend_usd} if row.spend_usd else None,
                impressions_range=None,
                raw=dict(row),
            )
            for row in rows
        ]

    def fetch(self, q: Query) -> ConnectorResponse:
        creds = settings.google_application_credentials
        if not creds and not _has_adc():
            return ConnectorResponse(
                status=Status.ERROR,
                message="No Google Cloud credentials configured (set GOOGLE_APPLICATION_CREDENTIALS or run 'gcloud auth application-default login')",
                manual_url=_ui_url(q),
            )

        country = q.country.upper()

        # Non-EEA: BigQuery dataset only covers EEA — return NO_DATA + deep-link
        if not self._is_eea(country):
            return ConnectorResponse(
                status=Status.NO_DATA,
                message=(
                    f"Google Ads Transparency Center BigQuery dataset covers EEA countries only. "
                    f"{country} is outside EEA. Use the manual link to search the global UI."
                ),
                manual_url=_ui_url(q),
            )

        try:
            commercial = self._query_creative_stats(q)
            political = self._query_political(q)
        except Exception as exc:
            return ConnectorResponse(
                status=Status.ERROR,
                message=str(exc),
                manual_url=_ui_url(q),
            )

        all_ads = commercial + political
        if not all_ads:
            return ConnectorResponse(
                status=Status.NO_DATA,
                message="No ads found in BigQuery for this query.",
                manual_url=_ui_url(q),
            )

        return ConnectorResponse(
            status=Status.OK,
            ads=all_ads,
            message=f"{len(commercial)} commercial + {len(political)} political ad(s)",
            manual_url=_ui_url(q),
        )


def _strip_domain(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    import urllib.parse
    try:
        return urllib.parse.urlparse(url).netloc.lstrip("www.")
    except Exception:
        return None


def _has_adc() -> bool:
    """True if Application Default Credentials appear to be configured."""
    import os
    adc_path = os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
    return os.path.exists(adc_path)
