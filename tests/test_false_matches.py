"""Tests for False-Positive Prevention, Variant Ambiguity, and Silent Selection Protection."""

import pytest
from app.services.catalogue.mock_catalogue import MockCatalogueProvider
from app.services.voice.confidence_engine import ConfidenceEngine
from app.services.voice.product_matcher import ProductMatcher
from app.services.voice.quantity_parser import QuantityParser
from app.services.voice.variant_matcher import VariantMatcher
from app.schemas.voice_schemas import ItemStatus, InterpretationStatus
from tests.conftest import run_async


def test_egg_versus_egg_masala_no_false_selection():
    async def _test():
        catalogue = MockCatalogueProvider()
        # Query "egg" must NOT return Egg Masala or Egg Noodles
        res = await ProductMatcher.match_product("egg", "tenant_default", catalogue)
        assert res.product.canonical_name == "Egg"
        assert res.product.canonical_name != "Egg Masala"
        assert res.product.canonical_name != "Egg Noodles"
        assert res.product.canonical_name != "Egg Biscuit"
    run_async(_test())


def test_generic_soap_query_requires_clarification_no_silent_selection():
    async def _test():
        catalogue = MockCatalogueProvider()
        # Catalogue contains both "Urvashi Soap" and "Washing Soap".
        # Saying generic "soap" must NOT silently choose either!
        candidates = await ProductMatcher.find_candidates("soap", "tenant_default", catalogue)
        # Because "soap" is only 1 token and both products are compound (Urvashi Soap, Washing Soap),
        # neither is an exact canonical match.
        res = await ProductMatcher.match_product("soap", "tenant_default", catalogue)
        assert res.status == "needs_clarification" or res.status == "unmatched"
        assert res.product is None  # Never silently selects!
    run_async(_test())


def test_multi_variant_product_without_specified_variant_triggers_clarification():
    async def _test():
        catalogue = MockCatalogueProvider()
        # "Washing Soap" has 3 variants: 100g, 160g, 250g.
        p = await catalogue.get_product_by_id("tenant_default", "prod-washing-soap")
        assert p is not None

        # User did not specify variant size:
        v_match = VariantMatcher.match_variant(
            product=p,
            package_size=None,
            sku=None,
            spoken_text="two washing soaps"
        )
        assert v_match.variant is None
        assert v_match.clarification_required is True
        assert len(v_match.candidate_variants) == 3
    run_async(_test())


def test_multi_variant_product_with_exact_package_size_resolves_cleanly():
    async def _test():
        catalogue = MockCatalogueProvider()
        p = await catalogue.get_product_by_id("tenant_default", "prod-washing-soap")

        v_match = VariantMatcher.match_variant(
            product=p,
            package_size="160g",
            sku=None,
            spoken_text="three packets of 160 gram washing soap"
        )
        assert v_match.variant is not None
        assert v_match.variant.variant_name == "160g"
        assert v_match.clarification_required is False
    run_async(_test())


def test_numeric_product_name_not_confused_with_quantity():
    # 20-20 Butter Cookies: "three 20-20 butter cookies"
    qty_res = QuantityParser.parse("three 20-20 butter cookies")
    assert qty_res.quantity == 3.0
    assert "20-20" in qty_res.remaining_text or "20 20" in qty_res.remaining_text


def test_confidence_engine_rejects_unverified_tenant():
    metrics = ConfidenceEngine.evaluate_item(
        speech_quality=0.95,
        product_score=1.0,
        variant_matched=True,
        has_multiple_variants=False,
        quantity=2.0,
        quantity_ambiguous=False,
        has_sku_conflict=False,
        is_tenant_verified=False,  # Unverified!
    )
    assert metrics.status == ItemStatus.REJECTED
    assert metrics.overall_confidence == 0.0
    assert "Tenant" in metrics.rejection_reason


def test_confidence_engine_marks_sku_conflict_as_clarification():
    metrics = ConfidenceEngine.evaluate_item(
        speech_quality=0.95,
        product_score=1.0,
        variant_matched=True,
        has_multiple_variants=False,
        quantity=2.0,
        quantity_ambiguous=False,
        has_sku_conflict=True,  # Conflict!
        is_tenant_verified=True,
        rejection_reason="Spoken product contradicts SKU"
    )
    assert metrics.status == ItemStatus.NEEDS_CLARIFICATION
