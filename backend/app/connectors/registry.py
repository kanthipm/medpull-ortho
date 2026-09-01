"""Provider registry — the single list the API and UI read integrations from.

Two kinds of entry share it. **Connectors** are things a webhook can be
addressed to (``/api/webhooks/wearables/{key}``): the demo source and the
Junction aggregator. **Brands** are the devices a patient actually wears; none
has a direct connector, and each is reachable through Junction under the slug
``connectors/junction.py`` maps it to, or, for the on-device platforms (Apple
Health, Health Connect, Samsung Health), only once a patient app embeds
Junction's mobile SDK.

Status is computed per request rather than stored, because the one thing that
flips it — the Junction API key — is read from the environment (or SSM on
Lambda) and can be set after import.
"""

from dataclasses import dataclass
from typing import Literal

from app.connectors.base import WearableConnector
from app.connectors.junction import SDK_ONLY_SLUGS, SLUG_BY_BRAND, JunctionConnector
from app.connectors.mock import MockConnector
from app.models.enums import SourceProvider as P

ProviderStatus = Literal[
    "mock_connected",  # the demo source: always "connected"
    "live",  # the aggregator, with an API key configured
    "needs_setup",  # the aggregator, without one
    "via_junction",  # a brand patients link from the hosted Junction page
    "needs_app",  # a brand only reachable through Junction's mobile SDK
    "coming_soon",  # no path at all yet
]


@dataclass(frozen=True)
class ProviderInfo:
    key: P
    name: str
    connector: WearableConnector | None
    # Junction's slug for the brand, when it is reachable through Junction.
    junction_slug: str | None = None


_mock = MockConnector()
_junction = JunctionConnector()


def _brand(key: P, name: str) -> ProviderInfo:
    return ProviderInfo(key, name, None, SLUG_BY_BRAND.get(key))


PROVIDERS: list[ProviderInfo] = [
    ProviderInfo(P.JUNCTION, "Junction", _junction, None),
    _brand(P.APPLE, "Apple Health"),
    _brand(P.FITBIT, "Fitbit"),
    _brand(P.GARMIN, "Garmin"),
    _brand(P.OURA, "Oura"),
    _brand(P.WHOOP, "WHOOP"),
    _brand(P.WITHINGS, "Withings"),
    _brand(P.DEXCOM, "Dexcom"),
    _brand(P.POLAR, "Polar"),
    _brand(P.SAMSUNG, "Samsung Health"),
    ProviderInfo(P.MOCK, "Demo data source", _mock, None),
]


def provider_status(info: ProviderInfo) -> ProviderStatus:
    if info.key is P.MOCK:
        return "mock_connected"
    if info.key is P.JUNCTION:
        return "live" if JunctionConnector.is_configured() else "needs_setup"
    if info.junction_slug is None:
        return "coming_soon"
    if info.junction_slug in SDK_ONLY_SLUGS:
        return "needs_app"
    return "via_junction"


def get_provider_info(provider: P) -> ProviderInfo | None:
    return next((p for p in PROVIDERS if p.key == provider), None)


def get_connector(provider: P) -> WearableConnector | None:
    info = get_provider_info(provider)
    return info.connector if info else None


def junction_connector() -> JunctionConnector:
    return _junction
