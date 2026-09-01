"""Provider registry — the single list the API and UI read integrations from."""

from dataclasses import dataclass
from typing import Literal

from app.connectors.base import WearableConnector
from app.connectors.mock import MockConnector
from app.models.enums import SourceProvider as P


@dataclass(frozen=True)
class ProviderInfo:
    key: P
    name: str
    status: Literal["mock_connected", "coming_soon"]
    connector: WearableConnector | None


_mock = MockConnector()

PROVIDERS: list[ProviderInfo] = [
    ProviderInfo(P.APPLE, "Apple Health", "coming_soon", None),
    ProviderInfo(P.FITBIT, "Fitbit", "coming_soon", None),
    ProviderInfo(P.GARMIN, "Garmin", "coming_soon", None),
    ProviderInfo(P.OURA, "Oura", "coming_soon", None),
    ProviderInfo(P.WHOOP, "WHOOP", "coming_soon", None),
    ProviderInfo(P.WITHINGS, "Withings", "coming_soon", None),
    ProviderInfo(P.DEXCOM, "Dexcom", "coming_soon", None),
    ProviderInfo(P.POLAR, "Polar", "coming_soon", None),
    ProviderInfo(P.SAMSUNG, "Samsung Health", "coming_soon", None),
    ProviderInfo(P.MOCK, "Demo data source", "mock_connected", _mock),
]


def get_provider_info(provider: P) -> ProviderInfo | None:
    return next((p for p in PROVIDERS if p.key == provider), None)


def get_connector(provider: P) -> WearableConnector | None:
    info = get_provider_info(provider)
    return info.connector if info else None
