"""Confidence Assessment Engine.

Computes separate heuristic confidence metrics across:
- Speech recognition quality
- Product identity confidence
- Variant resolution confidence
- Quantity parsing confidence
- Overall semantic consistency

Note: Confidence scores are explicit heuristics based on discrete match evidence
(exact token, verified alias, unambiguous variant, validated quantity range),
rather than black-box probabilities.
"""

from typing import Optional
from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas.voice_schemas import InterpretationStatus, ItemStatus


class ConfidenceMetrics(BaseModel):
    speech_confidence: float = Field(ge=0.0, le=1.0)
    product_confidence: float = Field(ge=0.0, le=1.0)
    variant_confidence: float = Field(ge=0.0, le=1.0)
    quantity_confidence: float = Field(ge=0.0, le=1.0)
    overall_confidence: float = Field(ge=0.0, le=1.0)
    status: ItemStatus
    rejection_reason: Optional[str] = None


class ConfidenceEngine:
    """Evaluates multi-dimensional confidence and assigns deterministic verification statuses."""

    @classmethod
    def evaluate_item(
        cls,
        speech_quality: float,
        product_score: float,
        variant_matched: bool,
        has_multiple_variants: bool,
        quantity: Optional[float],
        quantity_ambiguous: bool,
        has_sku_conflict: bool,
        is_tenant_verified: bool,
        rejection_reason: Optional[str] = None,
    ) -> ConfidenceMetrics:
        """Evaluates an item interpretation deterministically:

        - If tenant unverified or hard rejection reason: REJECTED (0.0).
        - If SKU conflict or quantity ambiguous or variant unclear: NEEDS_CLARIFICATION.
        - If exact product + valid quantity + clear variant: VERIFIED.
        """
        if not is_tenant_verified:
            return ConfidenceMetrics(
                speech_confidence=speech_quality,
                product_confidence=0.0,
                variant_confidence=0.0,
                quantity_confidence=0.0,
                overall_confidence=0.0,
                status=ItemStatus.REJECTED,
                rejection_reason="Tenant context is not verified",
            )

        # SKU conflict -> Medium confidence -> needs_clarification
        if has_sku_conflict:
            return ConfidenceMetrics(
                speech_confidence=speech_quality,
                product_confidence=product_score,
                variant_confidence=0.5,
                quantity_confidence=0.98 if (quantity and not quantity_ambiguous) else 0.0,
                overall_confidence=round(product_score * 0.5, 3),
                status=ItemStatus.NEEDS_CLARIFICATION,
                rejection_reason=rejection_reason or "Disagreement between product name and spoken SKU",
            )

        if rejection_reason:
            return ConfidenceMetrics(
                speech_confidence=speech_quality,
                product_confidence=product_score,
                variant_confidence=0.0,
                quantity_confidence=0.0,
                overall_confidence=0.0,
                status=ItemStatus.REJECTED,
                rejection_reason=rejection_reason,
            )

        # Quantity confidence
        if quantity_ambiguous or quantity is None or quantity <= 0:
            quantity_conf = 0.0
        else:
            quantity_conf = 0.98

        # Variant confidence
        if not has_multiple_variants:
            variant_conf = 1.0
        elif variant_matched:
            variant_conf = 0.95
        else:
            variant_conf = 0.30

        # Overall heuristic calculation
        overall = round(
            (speech_quality * 0.15)
            + (product_score * 0.45)
            + (variant_conf * 0.20)
            + (quantity_conf * 0.20),
            3
        )

        # Decision boundaries:
        # 1. Any conflict, ambiguity, or variant uncertainty -> needs_clarification
        if has_sku_conflict:
            return ConfidenceMetrics(
                speech_confidence=speech_quality,
                product_confidence=product_score,
                variant_confidence=variant_conf,
                quantity_confidence=quantity_conf,
                overall_confidence=overall,
                status=ItemStatus.NEEDS_CLARIFICATION,
                rejection_reason="Disagreement between product name and spoken SKU",
            )

        if quantity_ambiguous:
            return ConfidenceMetrics(
                speech_confidence=speech_quality,
                product_confidence=product_score,
                variant_confidence=variant_conf,
                quantity_confidence=0.0,
                overall_confidence=overall,
                status=ItemStatus.NEEDS_CLARIFICATION,
                rejection_reason="Ambiguous or conflicting quantity",
            )

        if has_multiple_variants and not variant_matched:
            return ConfidenceMetrics(
                speech_confidence=speech_quality,
                product_confidence=product_score,
                variant_confidence=variant_conf,
                quantity_confidence=quantity_conf,
                overall_confidence=overall,
                status=ItemStatus.NEEDS_CLARIFICATION,
                rejection_reason="Product variant not specified",
            )

        if product_score < settings.HIGH_CONFIDENCE_THRESHOLD:
            # Low or medium candidate match
            status = ItemStatus.NEEDS_CLARIFICATION if product_score >= settings.MEDIUM_CONFIDENCE_THRESHOLD else ItemStatus.UNMATCHED
            return ConfidenceMetrics(
                speech_confidence=speech_quality,
                product_confidence=product_score,
                variant_confidence=variant_conf,
                quantity_confidence=quantity_conf,
                overall_confidence=overall,
                status=status,
                rejection_reason="Product confidence below high confidence threshold",
            )

        # High confidence verified item
        return ConfidenceMetrics(
            speech_confidence=speech_quality,
            product_confidence=product_score,
            variant_confidence=variant_conf,
            quantity_confidence=quantity_conf,
            overall_confidence=overall,
            status=ItemStatus.VERIFIED,
        )

    @classmethod
    def derive_overall_status(cls, item_statuses: list[ItemStatus]) -> InterpretationStatus:
        """Derives the aggregate status of an interpretation request."""
        if not item_statuses:
            return InterpretationStatus.UNMATCHED

        if any(s == ItemStatus.REJECTED for s in item_statuses):
            return InterpretationStatus.REJECTED

        if any(s == ItemStatus.NEEDS_CLARIFICATION for s in item_statuses):
            return InterpretationStatus.NEEDS_CLARIFICATION

        if any(s == ItemStatus.UNMATCHED for s in item_statuses):
            return InterpretationStatus.UNMATCHED

        if all(s == ItemStatus.VERIFIED for s in item_statuses):
            return InterpretationStatus.VERIFIED

        return InterpretationStatus.NEEDS_CLARIFICATION
