"""Production HTTP Catalogue Provider connecting to ShopFlow Main Backend.

DOCUMENTED INTERNAL API CONTRACT:
To fetch catalogue data from the main ShopFlow backend, the following internal
authenticated endpoint must be provided by the main backend:

Method: GET
Path: {SHOPFLOW_BACKEND_URL}/internal/api/v1/tenants/{tenant_id}/catalogue
Headers:
    X-ShopFlow-Internal-Key: <SHOPFLOW_INTERNAL_API_KEY>
    X-Request-ID: <UUID>

Expected Response (200 OK):
{
  "tenant_id": "tenant-123",
  "products": [
    {
      "product_id": "prod-1",
      "canonical_name": "Urvashi Soap",
      "category": "Personal Care",
      "default_unit": "piece",
      "variants": [
        {
          "variant_id": "var-1",
          "variant_name": "100g",
          "sku": "URV-100",
          "barcode": "89012345",
          "package_size": "100g",
          "unit": "piece",
          "stock_available": 50.0
        }
      ],
      "aliases": [
        {"alias_phrase": "urvashi soap", "language": "en"},
        {"alias_phrase": "ഊർവശി സോപ്പ്", "language": "ml"}
      ]
    }
  ]
}
"""

from typing import Dict, List, Optional, Tuple
import httpx
from app.core.config import settings
from app.core.errors import CatalogueServiceUnavailableError, CatalogueTimeoutError
from app.core.logging import logger
from app.services.catalogue.interface import (
    CatalogueAlias,
    CatalogueProduct,
    CatalogueProductVariant,
    CatalogueProvider,
)


class HttpCatalogueProvider(CatalogueProvider):
    """Client for fetching tenant-isolated products from the authoritative ShopFlow main backend."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ):
        self.base_url = (base_url or settings.SHOPFLOW_BACKEND_URL or "").rstrip("/")
        self.api_key = api_key or settings.SHOPFLOW_INTERNAL_API_KEY
        self.timeout = timeout_seconds or settings.CATALOGUE_TIMEOUT_SECONDS

    async def _request(self, endpoint: str, tenant_id: str) -> dict:
        if not self.base_url:
            raise CatalogueServiceUnavailableError("ShopFlow backend URL is not configured")

        headers = {
            "Accept": "application/json",
            "X-Tenant-ID": tenant_id,
        }
        if self.api_key:
            headers["X-ShopFlow-Internal-Key"] = self.api_key

        url = f"{self.base_url}{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 404:
                    return {}
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as exc:
            logger.warning(f"Catalogue request timed out for tenant {tenant_id}")
            raise CatalogueTimeoutError(f"Catalogue service timed out: {exc}") from exc
        except (httpx.ConnectError, httpx.HTTPStatusError) as exc:
            logger.warning(f"Catalogue service unavailable for tenant {tenant_id}: {exc}")
            raise CatalogueServiceUnavailableError(f"Catalogue service error: {exc}") from exc

    async def get_tenant_products(self, tenant_id: str) -> List[CatalogueProduct]:
        data = await self._request(f"/internal/api/v1/tenants/{tenant_id}/catalogue", tenant_id)
        raw_products = data.get("products", [])
        results: List[CatalogueProduct] = []
        for p in raw_products:
            variants = [CatalogueProductVariant(**v) for v in p.get("variants", [])]
            aliases = [
                CatalogueAlias(
                    alias_phrase=a.get("alias_phrase", ""),
                    product_id=p.get("product_id"),
                    language=a.get("language", "all"),
                )
                for a in p.get("aliases", [])
            ]
            results.append(
                CatalogueProduct(
                    product_id=p["product_id"],
                    tenant_id=tenant_id,
                    canonical_name=p["canonical_name"],
                    category=p.get("category"),
                    default_unit=p.get("default_unit", "piece"),
                    variants=variants,
                    aliases=aliases,
                )
            )
        return results

    async def get_product_by_id(self, tenant_id: str, product_id: str) -> Optional[CatalogueProduct]:
        products = await self.get_tenant_products(tenant_id)
        for p in products:
            if p.product_id == product_id:
                return p
        return None

    async def get_product_by_sku(self, tenant_id: str, sku: str) -> Optional[Tuple[CatalogueProduct, CatalogueProductVariant]]:
        products = await self.get_tenant_products(tenant_id)
        for p in products:
            for v in p.variants:
                if v.sku == sku:
                    return (p, v)
        return None

    async def get_product_by_barcode(self, tenant_id: str, barcode: str) -> Optional[Tuple[CatalogueProduct, CatalogueProductVariant]]:
        products = await self.get_tenant_products(tenant_id)
        for p in products:
            for v in p.variants:
                if v.barcode == barcode:
                    return (p, v)
        return None

    async def get_aliases_for_tenant(self, tenant_id: str) -> List[CatalogueAlias]:
        products = await self.get_tenant_products(tenant_id)
        aliases: List[CatalogueAlias] = []
        for p in products:
            aliases.extend(p.aliases)
        return aliases

    async def check_health(self) -> bool:
        if not self.base_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.base_url}/health/live")
                return res.status_code == 200
        except Exception:
            return False
