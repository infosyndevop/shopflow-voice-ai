"""Catalogue service factory and provider exports."""

from typing import Optional
from app.core.config import settings
from app.services.catalogue.interface import CatalogueProvider
from app.services.catalogue.mock_catalogue import MockCatalogueProvider
from app.services.catalogue.http_catalogue import HttpCatalogueProvider

_global_catalogue_provider: Optional[CatalogueProvider] = None


def get_catalogue_provider() -> CatalogueProvider:
    """Dependency provider returning singleton catalogue provider."""
    global _global_catalogue_provider
    if _global_catalogue_provider is None:
        if settings.CATALOGUE_PROVIDER_TYPE == "http":
            _global_catalogue_provider = HttpCatalogueProvider()
        else:
            _global_catalogue_provider = MockCatalogueProvider()
    return _global_catalogue_provider


def set_catalogue_provider(provider: CatalogueProvider) -> None:
    """Explicitly override catalogue provider for test isolation."""
    global _global_catalogue_provider
    _global_catalogue_provider = provider
