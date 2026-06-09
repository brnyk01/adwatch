from adwatch.connectors.meta import MetaConnector
from adwatch.connectors.google_bq import GoogleBigQueryConnector
from adwatch.connectors.google_ui import GoogleUIConnector
from adwatch.connectors.tiktok import TikTokConnector
from adwatch.connectors.snapchat import SnapchatConnector
from adwatch.connectors.stub import (
    LinkedInStub,
    XStub,
    PinterestStub,
    RedditStub,
    AmazonStub,
    BingStub,
)

CONNECTOR_REGISTRY: dict = {
    "meta":       MetaConnector(),
    "google_bq":  GoogleBigQueryConnector(),
    "google_ui":  GoogleUIConnector(),
    "tiktok":     TikTokConnector(),
    "snapchat":   SnapchatConnector(),
    "linkedin":   LinkedInStub,
    "x":          XStub,
    "pinterest":  PinterestStub,
    "reddit":     RedditStub,
    "amazon":     AmazonStub,
    "bing":       BingStub,
}
