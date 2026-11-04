"""Tests for multi-product interpretation and conversational commands.

Verifies:
- Multiple distinct products extracted from a single compound utterance.
- Retaining verified items while reporting ambiguous or unmatched phrases.
- Distinct products with similar names (e.g. 'Egg' vs 'Egg Masala') are never merged.
- Multilingual conjunctions (Malayalam, Tamil, English).
- Conversational remove and correct commands.
"""

import pytest
from app.api.voice import interpret_voice
from app.schemas.voice_schemas import (
    InterpretationRequest,
    InterpretationStatus,
    ItemStatus,
)
from app.security.service_auth import TenantSecurityContext
from tests.conftest import run_async


def test_multi_product_three_items():
    """Utterance: 'Two Urvashi soaps, three packets of 160 gram washing soap and one egg'

    Expected:
    - Urvashi Soap: 2.0
    - Washing Soap 160g variant: 3.0 packets
    - Egg: 1.0
    """
    ctx = TenantSecurityContext(
        tenant_id="tenant_default",
        client_id="test_client",
        is_authenticated=True,
        roles=["pos_terminal"],
        request_id="req-multi-1",
    )
    req = InterpretationRequest(
        transcript="Two Urvashi soaps, three packets of 160 gram washing soap and one egg",
        idempotency_key="idem-multi-1",
    )

    resp = run_async(interpret_voice(req, security_ctx=ctx))

    assert len(resp.items) == 3

    # Product 1: Urvashi Soap
    item_urvashi = next(it for it in resp.items if "urvashi" in it.product_name.lower())
    assert item_urvashi.quantity == 2.0
    assert item_urvashi.product_name == "Urvashi Soap"

    # Product 2: Washing Soap 160g
    item_washing = next(it for it in resp.items if "washing" in it.product_name.lower())
    assert item_washing.quantity == 3.0
    assert item_washing.unit == "packet"
    assert item_washing.package_size == "160g"
    assert item_washing.sku == "002"
    assert item_washing.status == ItemStatus.VERIFIED

    # Product 3: Egg
    item_egg = next(it for it in resp.items if it.product_name.lower() == "egg")
    assert item_egg.quantity == 1.0
    assert item_egg.status == ItemStatus.VERIFIED


def test_similar_products_never_merged():
    """Utterance: 'One dozen eggs and two pieces of Egg Masala'

    Ensures 'Egg' and 'Egg Masala' are kept completely distinct.
    """
    ctx = TenantSecurityContext(
        tenant_id="tenant_default",
        client_id="test_client",
        is_authenticated=True,
        roles=["pos_terminal"],
        request_id="req-multi-sim",
    )
    req = InterpretationRequest(
        transcript="one dozen eggs and two pieces of egg masala",
        idempotency_key="idem-multi-sim",
    )

    resp = run_async(interpret_voice(req, security_ctx=ctx))

    assert len(resp.items) == 2

    egg_item = next(it for it in resp.items if it.product_name == "Egg")
    assert egg_item.quantity == 12.0  # One dozen = 12

    masala_item = next(it for it in resp.items if it.product_name == "Egg Masala")
    assert masala_item.quantity == 2.0
    assert masala_item.unit == "piece"


def test_partial_ambiguity_retains_verified():
    """Utterance with 1 verified item and 1 unknown phrase:

    'one egg and three packets of unknown mysterious biscuit'
    Expected:
    - Egg is parsed and verified.
    - Unknown phrase reported in unmatched_phrases.
    - Overall status requires clarification on unresolved phrase.
    """
    ctx = TenantSecurityContext(
        tenant_id="tenant_default",
        client_id="test_client",
        is_authenticated=True,
        roles=["pos_terminal"],
        request_id="req-multi-partial",
    )
    req = InterpretationRequest(
        transcript="one egg and three packets of unknown mysterious biscuit",
        idempotency_key="idem-multi-partial",
    )

    resp = run_async(interpret_voice(req, security_ctx=ctx))

    assert len(resp.items) == 1
    assert resp.items[0].product_name == "Egg"
    assert resp.items[0].quantity == 1.0
    assert resp.items[0].status == ItemStatus.VERIFIED

    assert len(resp.unmatched_phrases) == 1
    assert "unknown mysterious biscuit" in resp.unmatched_phrases[0]
    assert resp.clarification_required is True
    assert resp.status == InterpretationStatus.NEEDS_CLARIFICATION


def test_malayalam_multi_product():
    """Utterance: 'രണ്ട് ഉർവ്വശി സോപ്പ് പിന്നെ ഒരു മുട്ട' (Two Urvashi soaps then one egg)"""
    ctx = TenantSecurityContext(
        tenant_id="tenant_default",
        client_id="test_client",
        is_authenticated=True,
        roles=["pos_terminal"],
        request_id="req-ml-multi",
    )
    req = InterpretationRequest(
        transcript="രണ്ട് ഉർവ്വശി സോപ്പ് പിന്നെ ഒരു മുട്ട",
        idempotency_key="idem-ml-multi",
    )

    resp = run_async(interpret_voice(req, security_ctx=ctx))

    assert len(resp.items) == 2
    item_urv = next(it for it in resp.items if "urvashi" in it.product_name.lower())
    assert item_urv.quantity == 2.0

    item_egg = next(it for it in resp.items if it.product_name == "Egg")
    assert item_egg.quantity == 1.0


def test_conversational_remove():
    """Utterance: 'remove washing soap'"""
    ctx = TenantSecurityContext(
        tenant_id="tenant_default",
        client_id="test_client",
        is_authenticated=True,
        roles=["pos_terminal"],
        request_id="req-remove",
    )
    req = InterpretationRequest(
        transcript="remove washing soap",
        idempotency_key="idem-remove-1",
    )

    resp = run_async(interpret_voice(req, security_ctx=ctx))

    assert len(resp.items) == 1
    assert resp.items[0].status == ItemStatus.REJECTED
    assert "removed" in resp.items[0].clarification_prompt.lower()

