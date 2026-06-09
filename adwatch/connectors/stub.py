"""
Stub connectors for platforms with no usable official API for competitor/transparency data.
Each returns NO_OFFICIAL_API + a deep-link to the platform's public UI.
"""

from adwatch.connectors.base import (
    AbstractConnector,
    ConnectorResponse,
    Query,
    QueryDimension,
    Status,
)


class StubConnector(AbstractConnector):
    """Generic stub — returns NO_OFFICIAL_API with a platform UI deep-link."""

    supported_dimensions = {QueryDimension.NAME, QueryDimension.DOMAIN}

    def __init__(self, name: str, ui_url_template: str, note: str = ""):
        self.name = name
        self._ui_template = ui_url_template
        self._note = note

    def _url(self, q: Query) -> str:
        return self._ui_template.format(
            value=q.value,
            country=q.country.upper(),
        )

    def fetch(self, q: Query) -> ConnectorResponse:
        return ConnectorResponse(
            status=Status.NO_OFFICIAL_API,
            message=self._note or f"No official programmatic API available for {self.name}.",
            manual_url=self._url(q),
        )


# ---------------------------------------------------------------------------
# Pre-configured stubs
# ---------------------------------------------------------------------------

LinkedInStub = StubConnector(
    name="linkedin",
    ui_url_template="https://www.linkedin.com/ad-library/?companyName={value}",
    note=(
        "LinkedIn Ad Library has no public API for competitor data. "
        "The Marketing API only manages your own accounts. "
        "Search by company name in the public UI (active ads only, no spend data)."
    ),
)

XStub = StubConnector(
    name="x",
    ui_url_template="https://ads.x.com/transparency",
    note=(
        "X (Twitter) has no usable official ad transparency API. "
        "The DSA EU repository was fined €120M in Dec 2025 for missing critical fields. "
        "Historical political ads (2018–2019) are available as a downloadable archive only."
    ),
)

PinterestStub = StubConnector(
    name="pinterest",
    ui_url_template="https://ads.pinterest.com/ads-repository/?advertiser={value}",
    note=(
        "Pinterest Ads Transparency Repository is EU-centric with no documented public API. "
        "Search by advertiser in the public UI."
    ),
)

RedditStub = StubConnector(
    name="reddit",
    ui_url_template="https://ads.reddit.com/transparency",
    note=(
        "Reddit has no official ad transparency API for competitor data. "
        "Use the public ad inspiration surface via the UI."
    ),
)

AmazonStub = StubConnector(
    name="amazon",
    ui_url_template="https://advertising-api-eu.amazon.com",
    note=(
        "Amazon's DSA EU ad repository is available under DSA Article 39 but is EU-only "
        "and not a general commercial intelligence API."
    ),
)

BingStub = StubConnector(
    name="bing",
    ui_url_template="https://adlibrary.ads.microsoft.com/?query={value}",
    note=(
        "Microsoft/Bing Ad Library exists as a public UI but has no official public API. "
        "Search by advertiser name in the UI."
    ),
)
