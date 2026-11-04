"""Adversarial and Edge-Case Tests for Quantity, Unit, Price, and Product Safety.

Verifies strict retail safety:
- ₹10 biscuit: price isolated ($10), quantity NOT assumed to be 10 or 1.
- 20-20 Butter Cookies: numeric brand protected, not parsed as quantity 20.
- SKU 002: leading zeros preserved, matches Washing Soap 160g variant.
- Three packets of 160 g: separate quantity (3), unit (packet), package_size (160g).
- Two 160 g packets and three 250 g packets: multiple variant orders in one utterance.
- One dozen eggs: retail collective 'dozen' -> quantity 12.0.
- Two pieces of Egg Masala: quantity 2.0, unit 'piece', matches Egg Masala (not Egg).
- Contradictory quantities: 'two or maybe three' -> ambiguous, needs clarification.
- Missing quantities: 'biscuit' -> quantity None, needs clarification, never silently 1.
- Invalid quantities: 0 or negative -> rejected.
- Retail limit check: quantities exceeding max threshold -> rejected.
"""

import pytest
from app.api.voice import interpret_voice
from app.services.voice.quantity_parser import QuantityParser
from app.schemas.voice_schemas import (
    InterpretationRequest,
    InterpretationStatus,
    ItemStatus,
)
from app.security.service_auth import TenantSecurityContext
from tests.conftest import run_async


def test_price_reference_isolated_from_quantity():
    """'₹10 biscuit' -> price_reference: 10.0, quantity: None (never assumed 10 or 1)."""
    parsed = QuantityParser.parse("₹10 biscuit")
    assert parsed.price_reference == 10.0
    assert parsed.quantity is None
    assert "biscuit" in parsed.remaining_text.lower()

    # Also test through API
    ctx = TenantSecurityContext(
        tenant_id="tenant_default",
        client_id="test_client",
        is_authenticated=True,
        roles=["pos_terminal"],
        request_id="req-price-adv",
    )
    req = InterpretationRequest(
        transcript="₹10 egg biscuit",
        idempotency_key="idem-price-adv-2",
    )
    resp = run_async(interpret_voice(req, security_ctx=ctx))

    # Since quantity is missing, item cannot be silently verified as 1
    assert resp.status == InterpretationStatus.NEEDS_CLARIFICATION
    if resp.items:
        assert resp.items[0].price_reference == 10.0
        assert resp.items[0].quantity is None


def test_numeric_brand_20_20_protected():
    """'two 20-20 butter cookies' -> quantity: 2.0, product: '20-20 Butter Cookies'."""
    parsed = QuantityParser.parse("two 20-20 butter cookies")
    assert parsed.quantity == 2.0
    assert "20-20" in parsed.remaining_text

    ctx = TenantSecurityContext(
        tenant_id="tenant_default",
        client_id="test_client",
        is_authenticated=True,
        roles=["pos_terminal"],
        request_id="req-2020-adv",
    )
    req = InterpretationRequest(
        transcript="two 20-20 butter cookies",
        idempotency_key="idem-2020-adv",
    )
    resp = run_async(interpret_voice(req, security_ctx=ctx))

    assert len(resp.items) == 1
    item = resp.items[0]
    assert item.product_name == "20-20 Butter Cookies"
    assert item.quantity == 2.0


def test_sku_002_preserves_leading_zeros():
    """Utterance 'SKU 002' must match Washing Soap 160g variant without trimming zeros."""
    ctx = TenantSecurityContext(
        tenant_id="tenant_default",
        client_id="test_client",
        is_authenticated=True,
        roles=["pos_terminal"],
        request_id="req-sku-002",
    )
    req = InterpretationRequest(
        transcript="give me SKU 002",
        idempotency_key="idem-sku-002",
    )
    resp = run_async(interpret_voice(req, security_ctx=ctx))

    assert len(resp.items) == 1
    item = resp.items[0]
    assert item.sku == "002"
    assert item.variant_name == "160g"
    assert item.product_name == "Washing Soap"


def test_three_packets_of_160g():
    """'three packets of 160 gram washing soap' -> quantity=3, unit='packet', package_size='160g'."""
    parsed = QuantityParser.parse("three packets of 160 gram washing soap")
    assert parsed.quantity == 3.0
    assert parsed.unit == "packet"
    assert parsed.package_size == "160g"
    assert "washing soap" in parsed.remaining_text


def test_two_variants_in_one_utterance():
    """'Two 160 g packets and three 250 g packets of washing soap'."""
    ctx = TenantSecurityContext(
        tenant_id="tenant_default",
        client_id="test_client",
        is_authenticated=True,
        roles=["pos_terminal"],
        request_id="req-two-vars",
    )
    req = InterpretationRequest(
        transcript="Two 160g packets of washing soap and three 250g packets of washing soap",
        idempotency_key="idem-two-vars",
    )
    resp = run_async(interpret_voice(req, security_ctx=ctx))

    assert len(resp.items) == 2
    item1 = next(it for it in resp.items if it.package_size == "160g")
    assert item1.quantity == 2.0
    assert item1.sku == "002"

    item2 = next(it for it in resp.items if it.package_size == "250g")
    assert item2.quantity == 3.0
    assert item2.sku == "WS-250"


def test_one_dozen_eggs():
    """'one dozen eggs' -> quantity: 12.0, product: 'Egg'."""
    parsed = QuantityParser.parse("one dozen eggs")
    assert parsed.quantity == 12.0
    assert "eggs" in parsed.remaining_text

    ctx = TenantSecurityContext(
        tenant_id="tenant_default",
        client_id="test_client",
        is_authenticated=True,
        roles=["pos_terminal"],
        request_id="req-dozen-adv",
    )
    req = InterpretationRequest(
        transcript="one dozen eggs",
        idempotency_key="idem-dozen-adv",
    )
    resp = run_async(interpret_voice(req, security_ctx=ctx))

    assert len(resp.items) == 1
    assert resp.items[0].product_name == "Egg"
    assert resp.items[0].quantity == 12.0
    assert resp.items[0].status == ItemStatus.VERIFIED


def test_two_pieces_of_egg_masala():
    """'two pieces of Egg Masala' -> quantity: 2.0, unit: 'piece', product: 'Egg Masala' (NOT 'Egg')."""
    parsed = QuantityParser.parse("two pieces of Egg Masala")
    assert parsed.quantity == 2.0
    assert parsed.unit == "piece"
    assert parsed.remaining_text.strip() == "Egg Masala"

    ctx = TenantSecurityContext(
        tenant_id="tenant_default",
        client_id="test_client",
        is_authenticated=True,
        roles=["pos_terminal"],
        request_id="req-masala-adv",
    )
    req = InterpretationRequest(
        transcript="two pieces of Egg Masala",
        idempotency_key="idem-masala-adv",
    )
    resp = run_async(interpret_voice(req, security_ctx=ctx))

    assert len(resp.items) == 1
    assert resp.items[0].product_name == "Egg Masala"
    assert resp.items[0].product_name != "Egg"
    assert resp.items[0].quantity == 2.0


def test_contradictory_quantities():
    """'two or maybe three packets of washing soap' -> ambiguous quantity, must flag for clarification."""
    parsed = QuantityParser.parse("two or maybe three packets of washing soap")
    assert parsed.is_ambiguous is True
    assert "multiple quantities" in parsed.clarification_reason.lower()


def test_zero_and_negative_quantities():
    """Zero or negative quantities must be rejected."""
    parsed_zero = QuantityParser.parse("0 packets of soap")
    assert parsed_zero.is_ambiguous is True
    assert "invalid" in parsed_zero.clarification_reason.lower()

    parsed_neg = QuantityParser.parse("-5 soaps")
    assert parsed_neg.is_ambiguous is True


def test_exceeding_max_retail_quantity():
    """Quantity above DEFAULT_MAX_QUANTITY (500) must trigger clarification/warning."""
    parsed = QuantityParser.parse("999 packets of washing soap")
    assert parsed.is_ambiguous is True
    assert "exceeds" in parsed.clarification_reason.lower()
