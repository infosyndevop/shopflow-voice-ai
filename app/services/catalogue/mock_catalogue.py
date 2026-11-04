"""Mock Catalogue Provider with tenant isolation and test fixtures."""

import asyncio
from typing import Dict, List, Optional, Tuple
from app.services.catalogue.interface import (
    CatalogueAlias,
    CatalogueProduct,
    CatalogueProductVariant,
    CatalogueProvider,
)
from app.core.errors import CatalogueServiceUnavailableError, CatalogueTimeoutError


class MockCatalogueProvider(CatalogueProvider):
    """In-memory mock catalogue provider supporting strict tenant-isolation and failure simulations."""

    def __init__(self, simulate_timeout: bool = False, simulate_offline: bool = False):
        self.simulate_timeout = simulate_timeout
        self.simulate_offline = simulate_offline
        # Internal catalogue storage keyed by tenant_id
        self._tenants_catalogue: Dict[str, Dict[str, CatalogueProduct]] = {}
        self._init_fixtures()

    def _init_fixtures(self):
        """Populates realistic retail test fixtures."""
        t1 = "tenant_default"
        self._tenants_catalogue[t1] = {}

        # 1. Urvashi Soap
        p_urvashi = CatalogueProduct(
            product_id="prod-urvashi-soap",
            tenant_id=t1,
            canonical_name="Urvashi Soap",
            category="Personal Care",
            default_unit="piece",
            variants=[
                CatalogueProductVariant(
                    variant_id="var-urvashi-100g",
                    variant_name="100g",
                    package_size="100g",
                    sku="URV-100",
                    unit="piece",
                ),
                CatalogueProductVariant(
                    variant_id="var-urvashi-150g",
                    variant_name="150g",
                    package_size="150g",
                    sku="URV-150",
                    unit="piece",
                ),
            ],
            aliases=[
                CatalogueAlias(alias_phrase="urvashi soap", product_id="prod-urvashi-soap"),
                CatalogueAlias(alias_phrase="urvasi soap", product_id="prod-urvashi-soap"),
                CatalogueAlias(alias_phrase="ഊർവശി സോപ്പ്", product_id="prod-urvashi-soap", language="ml"),
                CatalogueAlias(alias_phrase="ഉർവ്വശി സോപ്പ്", product_id="prod-urvashi-soap", language="ml"),
                CatalogueAlias(alias_phrase="ഉർവശി സോപ്പ്", product_id="prod-urvashi-soap", language="ml"),
                CatalogueAlias(alias_phrase="ഊർവ്വശി സോപ്പ്", product_id="prod-urvashi-soap", language="ml"),
                CatalogueAlias(alias_phrase="ஊர்வசி சோப்", product_id="prod-urvashi-soap", language="ta"),
            ],
        )
        self._tenants_catalogue[t1][p_urvashi.product_id] = p_urvashi

        # 2. Washing Soap with 100g, 160g, 250g and exact SKU with leading zeros "002"
        p_washing = CatalogueProduct(
            product_id="prod-washing-soap",
            tenant_id=t1,
            canonical_name="Washing Soap",
            category="Household",
            default_unit="packet",
            variants=[
                CatalogueProductVariant(
                    variant_id="var-wash-100g",
                    variant_name="100g",
                    package_size="100g",
                    sku="WS-100",
                    unit="packet",
                ),
                CatalogueProductVariant(
                    variant_id="var-wash-160g",
                    variant_name="160g",
                    package_size="160g",
                    sku="002",  # Preserves leading zeros
                    barcode="8901234567890",
                    unit="packet",
                ),
                CatalogueProductVariant(
                    variant_id="var-wash-250g",
                    variant_name="250g",
                    package_size="250g",
                    sku="WS-250",
                    unit="packet",
                ),
            ],
            aliases=[
                CatalogueAlias(alias_phrase="washing soap", product_id="prod-washing-soap"),
                CatalogueAlias(alias_phrase="തുണി സോപ്പ്", product_id="prod-washing-soap", language="ml"),
                CatalogueAlias(alias_phrase="துணி சோப்", product_id="prod-washing-soap", language="ta"),
            ],
        )
        self._tenants_catalogue[t1][p_washing.product_id] = p_washing

        # 3. Similar name test suite: Egg vs Egg Masala vs Egg Noodles vs Egg Biscuit
        p_egg = CatalogueProduct(
            product_id="prod-egg",
            tenant_id=t1,
            canonical_name="Egg",
            category="Poultry",
            default_unit="piece",
            variants=[
                CatalogueProductVariant(
                    variant_id="var-egg-standard",
                    variant_name="Regular",
                    sku="EGG-001",
                    unit="piece",
                )
            ],
            aliases=[
                CatalogueAlias(alias_phrase="egg", product_id="prod-egg"),
                CatalogueAlias(alias_phrase="മുട്ട", product_id="prod-egg", language="ml"),
                CatalogueAlias(alias_phrase="முட்டை", product_id="prod-egg", language="ta"),
            ],
        )
        self._tenants_catalogue[t1][p_egg.product_id] = p_egg

        p_egg_masala = CatalogueProduct(
            product_id="prod-egg-masala",
            tenant_id=t1,
            canonical_name="Egg Masala",
            category="Spices",
            default_unit="packet",
            variants=[
                CatalogueProductVariant(
                    variant_id="var-egg-masala-100g",
                    variant_name="100g",
                    package_size="100g",
                    sku="EGG-MAS-100",
                    unit="packet",
                )
            ],
            aliases=[
                CatalogueAlias(alias_phrase="egg masala", product_id="prod-egg-masala"),
                CatalogueAlias(alias_phrase="മുട്ട മസാല", product_id="prod-egg-masala", language="ml"),
            ],
        )
        self._tenants_catalogue[t1][p_egg_masala.product_id] = p_egg_masala

        p_egg_noodles = CatalogueProduct(
            product_id="prod-egg-noodles",
            tenant_id=t1,
            canonical_name="Egg Noodles",
            category="Packaged Food",
            default_unit="packet",
            variants=[
                CatalogueProductVariant(
                    variant_id="var-egg-nood-200g",
                    variant_name="200g",
                    package_size="200g",
                    sku="EGG-NOOD-200",
                    unit="packet",
                )
            ],
            aliases=[
                CatalogueAlias(alias_phrase="egg noodles", product_id="prod-egg-noodles"),
            ],
        )
        self._tenants_catalogue[t1][p_egg_noodles.product_id] = p_egg_noodles

        p_egg_biscuit = CatalogueProduct(
            product_id="prod-egg-biscuit",
            tenant_id=t1,
            canonical_name="Egg Biscuit",
            category="Snacks",
            default_unit="packet",
            variants=[
                CatalogueProductVariant(
                    variant_id="var-egg-bisc-150g",
                    variant_name="150g",
                    package_size="150g",
                    sku="EGG-BISC-150",
                    unit="packet",
                )
            ],
            aliases=[
                CatalogueAlias(alias_phrase="egg biscuit", product_id="prod-egg-biscuit"),
            ],
        )
        self._tenants_catalogue[t1][p_egg_biscuit.product_id] = p_egg_biscuit

        # 4. Numeric product name: "20-20 Butter Cookies"
        p_2020 = CatalogueProduct(
            product_id="prod-2020-butter-cookies",
            tenant_id=t1,
            canonical_name="20-20 Butter Cookies",
            category="Snacks",
            default_unit="packet",
            variants=[
                CatalogueProductVariant(
                    variant_id="var-2020-100g",
                    variant_name="100g",
                    package_size="100g",
                    sku="2020-BC-100",
                    unit="packet",
                )
            ],
            aliases=[
                CatalogueAlias(alias_phrase="20-20 butter cookies", product_id="prod-2020-butter-cookies"),
                CatalogueAlias(alias_phrase="20 20 biscuit", product_id="prod-2020-butter-cookies"),
                CatalogueAlias(alias_phrase="20-20", product_id="prod-2020-butter-cookies"),
                CatalogueAlias(alias_phrase="20 20", product_id="prod-2020-butter-cookies"),
            ],
        )
        self._tenants_catalogue[t1][p_2020.product_id] = p_2020

        # Tenant 2: Separate tenant for strict tenant isolation testing
        t2 = "tenant_store_b"
        self._tenants_catalogue[t2] = {}
        p_t2_item = CatalogueProduct(
            product_id="prod-store-b-exclusive",
            tenant_id=t2,
            canonical_name="Store B Organic Rice",
            category="Grains",
            default_unit="kg",
            variants=[
                CatalogueProductVariant(
                    variant_id="var-b-rice-1kg",
                    variant_name="1kg",
                    package_size="1kg",
                    sku="002",  # Identical SKU to Washing Soap in T1, but completely different tenant!
                    unit="kg",
                )
            ],
            aliases=[
                CatalogueAlias(alias_phrase="organic rice", product_id="prod-store-b-exclusive"),
            ],
        )
        self._tenants_catalogue[t2][p_t2_item.product_id] = p_t2_item

    async def _simulate_network_conditions(self):
        if self.simulate_offline:
            raise CatalogueServiceUnavailableError("Mocked catalogue service failure: offline")
        if self.simulate_timeout:
            raise CatalogueTimeoutError("Mocked catalogue lookup timeout")

    async def get_tenant_products(self, tenant_id: str) -> List[CatalogueProduct]:
        await self._simulate_network_conditions()
        tenant_prods = self._tenants_catalogue.get(tenant_id, {})
        return list(tenant_prods.values())

    async def get_product_by_id(self, tenant_id: str, product_id: str) -> Optional[CatalogueProduct]:
        await self._simulate_network_conditions()
        return self._tenants_catalogue.get(tenant_id, {}).get(product_id)

    async def get_product_by_sku(self, tenant_id: str, sku: str) -> Optional[Tuple[CatalogueProduct, CatalogueProductVariant]]:
        await self._simulate_network_conditions()
        tenant_prods = self._tenants_catalogue.get(tenant_id, {})
        target_sku = sku.strip()
        for prod in tenant_prods.values():
            for variant in prod.variants:
                if variant.sku == target_sku:
                    return (prod, variant)
        return None

    async def get_product_by_barcode(self, tenant_id: str, barcode: str) -> Optional[Tuple[CatalogueProduct, CatalogueProductVariant]]:
        await self._simulate_network_conditions()
        tenant_prods = self._tenants_catalogue.get(tenant_id, {})
        target_code = barcode.strip()
        for prod in tenant_prods.values():
            for variant in prod.variants:
                if variant.barcode == target_code:
                    return (prod, variant)
        return None

    async def get_aliases_for_tenant(self, tenant_id: str) -> List[CatalogueAlias]:
        await self._simulate_network_conditions()
        aliases: List[CatalogueAlias] = []
        for prod in self._tenants_catalogue.get(tenant_id, {}).values():
            aliases.extend(prod.aliases)
        return aliases

    async def check_health(self) -> bool:
        if self.simulate_offline or self.simulate_timeout:
            return False
        return True
