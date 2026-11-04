"""Strict SKU matching preserving leading zeros with tenant isolation and conflict detection."""

import re
from typing import List, Optional, Tuple
from pydantic import BaseModel

from app.core.logging import logger
from app.services.catalogue.interface import CatalogueProduct, CatalogueProductVariant, CatalogueProvider
from app.services.voice.number_parser import NumberParser

SKU_TRIGGER_RE = re.compile(
    r"\b(?:sku|item\s+code|code|എസ്\s*കെ\s*യു|കുറിയീട്)\s+([a-zA-Z0-9\-_]+(?:\s+[a-zA-Z0-9\-_]+){0,3})",
    re.IGNORECASE
)


class SkuMatchResult(BaseModel):
    extracted_sku: Optional[str] = None
    matched_product: Optional[CatalogueProduct] = None
    matched_variant: Optional[CatalogueProductVariant] = None
    is_conflict: bool = False
    conflict_reason: Optional[str] = None
    clean_text: str = ""


class SkuMatcher:
    """Exact SKU identification with leading-zero preservation and tenant verification."""

    @staticmethod
    def extract_spoken_sku(text: str) -> Tuple[Optional[str], str]:
        """Looks for explicit SKU markers (e.g. 'SKU zero zero two', 'code 002').

        Returns (extracted_sku_str, text_with_sku_removed).
        """
        match = SKU_TRIGGER_RE.search(text)
        if not match:
            return (None, text)

        raw_sku_part = match.group(1).strip()
        tokens = raw_sku_part.split()

        # Check if the tokens after "sku" are digit words like "zero zero two"
        digit_seq = NumberParser.parse_digit_sequence(tokens)
        if digit_seq is not None:
            extracted_sku = digit_seq
        else:
            # First token is the candidate SKU
            extracted_sku = tokens[0]

        # Remove the full SKU marker from the text
        clean_text = SKU_TRIGGER_RE.sub(" ", text).strip()
        clean_text = re.sub(r"\s+", " ", clean_text)
        return (extracted_sku, clean_text)

    @classmethod
    async def match_sku(
        cls,
        text: str,
        tenant_id: str,
        catalogue_provider: CatalogueProvider,
        claimed_product_name: Optional[str] = None,
    ) -> SkuMatchResult:
        """Performs tenant-scoped exact SKU lookup.

        Guarantees:
        - Exact matching only.
        - Preserves leading zeros (e.g. '002').
        - Never uses fuzzy matching.
        - Confirms SKU belongs to the authenticated tenant.
        - Detects conflict if claimed product name contradicts the SKU's product.
        """
        extracted_sku, clean_text = cls.extract_spoken_sku(text)
        if not extracted_sku:
            return SkuMatchResult(extracted_sku=None, clean_text=clean_text)

        # Look up SKU in tenant catalogue
        lookup_result = await catalogue_provider.get_product_by_sku(tenant_id, extracted_sku)
        if not lookup_result:
            return SkuMatchResult(
                extracted_sku=extracted_sku,
                is_conflict=False,
                conflict_reason=f"SKU '{extracted_sku}' not found in tenant catalogue",
                clean_text=clean_text
            )

        product, variant = lookup_result

        # Cross-tenant check
        if product.tenant_id != tenant_id:
            logger.error(f"Tenant isolation breach attempt: SKU {extracted_sku} from {product.tenant_id} accessed by {tenant_id}")
            return SkuMatchResult(
                extracted_sku=extracted_sku,
                is_conflict=True,
                conflict_reason="Cross-tenant SKU violation",
                clean_text=clean_text
            )

        # Disagreement check between spoken product name and SKU
        if claimed_product_name:
            prod_name_lower = product.canonical_name.lower()
            claimed_lower = claimed_product_name.lower().strip()
            # If claimed product name is distinctly different from the SKU product
            if claimed_lower and claimed_lower not in prod_name_lower and prod_name_lower not in claimed_lower:
                return SkuMatchResult(
                    extracted_sku=extracted_sku,
                    matched_product=product,
                    matched_variant=variant,
                    is_conflict=True,
                    conflict_reason=f"Disagreement: Spoken product '{claimed_product_name}' contradicts SKU '{extracted_sku}' ({product.canonical_name})",
                    clean_text=clean_text
                )

        return SkuMatchResult(
            extracted_sku=extracted_sku,
            matched_product=product,
            matched_variant=variant,
            is_conflict=False,
            clean_text=clean_text
        )
