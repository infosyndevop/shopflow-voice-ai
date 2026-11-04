"""Tests for Product Intelligence, candidate ranking, aliases, and tenant isolation."""

import pytest
from app.services.catalogue.mock_catalogue import MockCatalogueProvider
from app.services.voice.product_matcher import ProductMatcher
from tests.conftest import run_async


def test_exact_canonical_product_matching():
    async def _test():
        catalogue = MockCatalogueProvider()
        result = await ProductMatcher.match_product(
            search_phrase="Urvashi Soap",
            tenant_id="tenant_default",
            catalogue_provider=catalogue
        )
        assert result.status == "verified"
        assert result.product is not None
        assert result.product.canonical_name == "Urvashi Soap"
        assert result.confidence >= 0.95
    run_async(_test())


def test_approved_alias_matching_english_and_indic():
    async def _test():
        catalogue = MockCatalogueProvider()
        # English phonetic alias
        res_en = await ProductMatcher.match_product(
            search_phrase="urvasi soap",
            tenant_id="tenant_default",
            catalogue_provider=catalogue
        )
        assert res_en.status == "verified"
        assert res_en.product.canonical_name == "Urvashi Soap"

        # Malayalam alias
        res_ml = await ProductMatcher.match_product(
            search_phrase="ഊർവശി സോപ്പ്",
            tenant_id="tenant_default",
            catalogue_provider=catalogue
        )
        assert res_ml.status == "verified"
        assert res_ml.product.canonical_name == "Urvashi Soap"

        # Tamil alias
        res_ta = await ProductMatcher.match_product(
            search_phrase="ஊர்வசி சோப்",
            tenant_id="tenant_default",
            catalogue_provider=catalogue
        )
        assert res_ta.status == "verified"
        assert res_ta.product.canonical_name == "Urvashi Soap"
    run_async(_test())


def test_similar_product_names_not_confused():
    async def _test():
        catalogue = MockCatalogueProvider()
        # When user says "Egg", it must match "Egg" and NEVER automatically pick "Egg Masala"
        res_egg = await ProductMatcher.match_product(
            search_phrase="egg",
            tenant_id="tenant_default",
            catalogue_provider=catalogue
        )
        assert res_egg.status == "verified"
        assert res_egg.product.canonical_name == "Egg"
        assert res_egg.product.canonical_name != "Egg Masala"

        # When user explicitly says "Egg Masala", it matches "Egg Masala"
        res_masala = await ProductMatcher.match_product(
            search_phrase="egg masala",
            tenant_id="tenant_default",
            catalogue_provider=catalogue
        )
        assert res_masala.status == "verified"
        assert res_masala.product.canonical_name == "Egg Masala"
    run_async(_test())


def test_missing_product_returns_unmatched():
    async def _test():
        catalogue = MockCatalogueProvider()
        result = await ProductMatcher.match_product(
            search_phrase="NonExistentProductXyZ123",
            tenant_id="tenant_default",
            catalogue_provider=catalogue
        )
        assert result.status == "unmatched"
        assert result.product is None
        assert result.confidence == 0.0
    run_async(_test())


def test_cross_tenant_product_isolation():
    async def _test():
        catalogue = MockCatalogueProvider()
        # Tenant 1 tries to access Tenant 2 exclusive item
        t1_attempt = await ProductMatcher.match_product(
            search_phrase="Store B Organic Rice",
            tenant_id="tenant_default",  # Should NOT find Tenant 2's exclusive product
            catalogue_provider=catalogue
        )
        assert t1_attempt.status == "unmatched"
        assert t1_attempt.product is None

        # Tenant 2 accessing its own item succeeds
        t2_success = await ProductMatcher.match_product(
            search_phrase="Store B Organic Rice",
            tenant_id="tenant_store_b",
            catalogue_provider=catalogue
        )
        assert t2_success.status == "verified"
        assert t2_success.product.canonical_name == "Store B Organic Rice"
    run_async(_test())
