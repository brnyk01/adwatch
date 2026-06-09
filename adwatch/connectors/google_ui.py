from adwatch.connectors.base import (
    AbstractConnector,
    ConnectorResponse,
    Query,
    QueryDimension,
    Status,
)

_UI_BASE = "https://adstransparency.google.com"


def _ui_url(q: Query) -> str:
    region = q.country.upper()
    if q.dimension == QueryDimension.DOMAIN:
        return f"{_UI_BASE}/?region={region}&domain={q.value}"
    return f"{_UI_BASE}/?region={region}&advertiser_name={q.value}"


class GoogleUIConnector(AbstractConnector):
    """
    No scraping — returns a deep-link into the official Google Ads Transparency Center UI.
    Used for non-EEA markets (e.g. Singapore) where no official API/BigQuery data exists.
    """

    name = "google_ui"
    supported_dimensions = {QueryDimension.DOMAIN, QueryDimension.NAME}

    def fetch(self, q: Query) -> ConnectorResponse:
        return ConnectorResponse(
            status=Status.NO_OFFICIAL_API,
            message=(
                "Google Ads Transparency Center has no official API for non-EEA markets. "
                "Use the link below to search the public UI (supports domain and advertiser search, "
                "global coverage, no login required)."
            ),
            manual_url=_ui_url(q),
        )
