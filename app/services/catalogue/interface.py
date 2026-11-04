"""Catalogue Provider interface and domain models."""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CatalogueProductVariant(BaseModel):
    variant_id: str
    variant_name: str
    sku: Optional[str] = None
    barcode: Optional[str] = None
    package_size: Optional[str] = None  # e.g. "160g", "1L", "500g"
    unit: str = "piece"                 # piece, packet, box, kg, gram, litre, ml
    is_active: bool = True
    stock_available: Optional[float] = None


class CatalogueAlias(BaseModel):
    alias_phrase: str                   # normalized alias phrase e.g. "ഊർവശി സോപ്പ്", "urvashi"
    product_id: str
    variant_id: Optional[str] = None
    language: str = "all"               # "ml", "ta", "en", "all"
    is_active: bool = True


class CatalogueProduct(BaseModel):
    product_id: str
    tenant_id: str
    canonical_name: str
    category: Optional[str] = None
    default_unit: str = "piece"
    variants: List[CatalogueProductVariant] = Field(default_factory=list)
    aliases: List[CatalogueAlias] = Field(default_factory=list)
    is_active: bool = True


class CatalogueProvider(ABC):
    """Abstract interface defining tenant-isolated product catalogue access."""

    @abstractmethod
    async def get_tenant_products(self, tenant_id: str) -> List[CatalogueProduct]:
        """Fetch all active products for the authenticated tenant."""
        pass

    @abstractmethod
    async def get_product_by_id(self, tenant_id: str, product_id: str) -> Optional[CatalogueProduct]:
        """Find a specific product by product ID strictly within the tenant."""
        pass

    @abstractmethod
    async def get_product_by_sku(self, tenant_id: str, sku: str) -> Optional[tuple[CatalogueProduct, CatalogueProductVariant]]:
        """Exact SKU lookup preserving leading zeros strictly within tenant."""
        pass

    @abstractmethod
    async def get_product_by_barcode(self, tenant_id: str, barcode: str) -> Optional[tuple[CatalogueProduct, CatalogueProductVariant]]:
        """Exact barcode lookup strictly within tenant."""
        pass

    @abstractmethod
    async def get_aliases_for_tenant(self, tenant_id: str) -> List[CatalogueAlias]:
        """Fetch all approved shop-specific aliases for tenant."""
        pass

    @abstractmethod
    async def check_health(self) -> bool:
        """Verify catalogue service health."""
        pass
