"""Product Variant Matcher.

Resolves product variants based on package size, SKU, or explicit variant names.
Never substitutes another variant automatically.
Requests clarification if variant cannot be unambiguously resolved.
"""

import re
from typing import List, Optional
from pydantic import BaseModel

from app.services.catalogue.interface import CatalogueProduct, CatalogueProductVariant


class VariantMatchResult(BaseModel):
    variant: Optional[CatalogueProductVariant] = None
    is_ambiguous: bool = False
    clarification_required: bool = False
    clarification_prompt: Optional[str] = None
    candidate_variants: List[str] = []


class VariantMatcher:
    """Matches product variants safely and detects ambiguous variant requests."""

    @staticmethod
    def _normalize_size_string(size_str: Optional[str]) -> Optional[str]:
        if not size_str:
            return None
        # Remove spaces, e.g. "160 g" -> "160g", "1 L" -> "1l"
        cleaned = re.sub(r"\s+", "", size_str.lower())
        cleaned = cleaned.replace("gm", "g").replace("gram", "g").replace("grams", "g")
        cleaned = cleaned.replace("liter", "l").replace("litre", "l")
        return cleaned

    @classmethod
    def match_variant(
        cls,
        product: CatalogueProduct,
        package_size: Optional[str] = None,
        sku: Optional[str] = None,
        spoken_text: Optional[str] = None,
    ) -> VariantMatchResult:
        """Determines the exact variant for a verified product.

        - If product has only 1 variant: returns that variant.
        - If SKU matches a specific variant: returns that variant.
        - If package_size matches: returns that variant.
        - If spoken_text explicitly mentions variant name (e.g. '160g', '500ml'): returns that variant.
        - If multiple variants exist and none or multiple match: flags clarification_required.
        """
        variants = [v for v in product.variants if v.is_active]
        if not variants:
            return VariantMatchResult(
                variant=None,
                is_ambiguous=True,
                clarification_required=True,
                clarification_prompt=f"No active variants found for product {product.canonical_name}",
            )

        # Single variant case: unambiguous
        if len(variants) == 1:
            return VariantMatchResult(variant=variants[0], is_ambiguous=False)

        # SKU matching case
        if sku:
            for v in variants:
                if v.sku and v.sku.strip() == sku.strip():
                    return VariantMatchResult(variant=v, is_ambiguous=False)

        # Package size matching case
        norm_requested_pkg = cls._normalize_size_string(package_size)
        if norm_requested_pkg:
            matched_by_pkg = []
            for v in variants:
                norm_v_pkg = cls._normalize_size_string(v.package_size or v.variant_name)
                if norm_v_pkg and norm_v_pkg == norm_requested_pkg:
                    matched_by_pkg.append(v)
            if len(matched_by_pkg) == 1:
                return VariantMatchResult(variant=matched_by_pkg[0], is_ambiguous=False)
            elif len(matched_by_pkg) > 1:
                return VariantMatchResult(
                    variant=None,
                    is_ambiguous=True,
                    clarification_required=True,
                    clarification_prompt=f"Multiple variants match package size {package_size}",
                    candidate_variants=[v.variant_name for v in matched_by_pkg]
                )

        # Spoken text keyword matching case
        if spoken_text:
            text_norm = cls._normalize_size_string(spoken_text) or ""
            text_matches = []
            for v in variants:
                v_name_norm = cls._normalize_size_string(v.variant_name) or ""
                v_pkg_norm = cls._normalize_size_string(v.package_size) or ""
                if (v_name_norm and v_name_norm in text_norm) or (v_pkg_norm and v_pkg_norm in text_norm):
                    text_matches.append(v)
            if len(text_matches) == 1:
                return VariantMatchResult(variant=text_matches[0], is_ambiguous=False)

        # If product has multiple variants and cannot resolve: NEVER substitute another variant!
        variant_names = [f"{v.variant_name} ({v.package_size or ''})".strip() for v in variants]
        return VariantMatchResult(
            variant=None,
            is_ambiguous=True,
            clarification_required=True,
            clarification_prompt=f"Please specify the variant for {product.canonical_name}. Available options: {', '.join(variant_names)}",
            candidate_variants=variant_names
        )

