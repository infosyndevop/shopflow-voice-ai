"""Tests for exact SKU matching, leading zero preservation, and conflict detection."""

import pytest
from app.services.catalogue.mock_catalogue import MockCatalogueProvider
from app.services.voice.sku_matcher import SkuMatcher
from tests.conftest import run_async


def test_exact_sku_matching_with_leading_zeros():
    async def _test():
        catalogue = MockCatalogueProvider()
        # Spoken: "item code 002"
        result = await SkuMatcher.match_sku(
            text="item code 002",
            tenant_id="tenant_default",
            catalogue_provider=catalogue
        )
        assert result.extracted_sku == "002"
        assert result.matched_product is not None
        assert result.matched_product.canonical_name == "Washing Soap"
        assert result.matched_variant is not None
        assert result.matched_variant.sku == "002"
        assert not result.is_conflict
    run_async(_test())


def test_spoken_digit_words_for_sku_preserves_zeros():
    async def _test():
        catalogue = MockCatalogueProvider()
        # Spoken: "SKU zero zero two"
        result = await SkuMatcher.match_sku(
            text="SKU zero zero two",
            tenant_id="tenant_default",
            catalogue_provider=catalogue
        )
        assert result.extracted_sku == "002"
        assert result.matched_variant.sku == "002"
        assert not result.is_conflict
    run_async(_test())


def test_unknown_sku_not_found():
    async def _test():
        catalogue = MockCatalogueProvider()
        result = await SkuMatcher.match_sku(
            text="SKU 9999",
            tenant_id="tenant_default",
            catalogue_provider=catalogue
        )
        assert result.extracted_sku == "9999"
        assert result.matched_product is None
        assert "not found" in (result.conflict_reason or "")
    run_async(_test())


def test_sku_and_product_name_conflict():
    async def _test():
        catalogue = MockCatalogueProvider()
        # Employee says "Egg" but specifies SKU "002" which belongs to "Washing Soap"
        result = await SkuMatcher.match_sku(
            text="SKU 002",
            tenant_id="tenant_default",
            catalogue_provider=catalogue,
            claimed_product_name="Egg"
        )
        assert result.is_conflict is True
        assert "Disagreement" in result.conflict_reason
    run_async(_test())


def test_cross_tenant_sku_isolation():
    async def _test():
        catalogue = MockCatalogueProvider()
        # SKU "002" in tenant_default is "Washing Soap"
        t1_result = await SkuMatcher.match_sku(
            text="SKU 002",
            tenant_id="tenant_default",
            catalogue_provider=catalogue
        )
        assert t1_result.matched_product.canonical_name == "Washing Soap"

        # SKU "002" in tenant_store_b is "Store B Organic Rice"
        t2_result = await SkuMatcher.match_sku(
            text="SKU 002",
            tenant_id="tenant_store_b",
            catalogue_provider=catalogue
        )
        assert t2_result.matched_product.canonical_name == "Store B Organic Rice"
    run_async(_test())


def test_ordinary_quantity_not_mistaken_for_sku():
    async def _test():
        catalogue = MockCatalogueProvider()
        result = await SkuMatcher.match_sku(
            text="two soaps",
            tenant_id="tenant_default",
            catalogue_provider=catalogue
        )
        assert result.extracted_sku is None
        assert result.matched_product is None
        assert result.clean_text == "two soaps"
    run_async(_test())
