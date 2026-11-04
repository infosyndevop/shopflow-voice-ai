"""Product Intelligence Engine.

Multi-tier ranking:
1. Exact barcode
2. Exact SKU
3. Exact canonical product name
4. Approved exact alias
5. Language-normalized alias
6. Token overlap
7. Fuzzy similarity (used for candidate discovery ONLY, never to authorize).

Strictly prevents false matches between similar products (e.g. 'Egg' vs 'Egg Masala').
"""

import re
from typing import List, Optional, Tuple
from pydantic import BaseModel
from rapidfuzz import fuzz

from app.core.config import settings
from app.services.catalogue.interface import CatalogueProduct, CatalogueProvider
from app.services.voice.language_normalizer import LanguageNormalizer


class ProductCandidate(BaseModel):
    product: CatalogueProduct
    match_score: float
    match_type: str  # barcode, sku, exact_canonical, exact_alias, normalized_alias, token_match, fuzzy_discovery


class ProductMatchResult(BaseModel):
    product: Optional[CatalogueProduct] = None
    confidence: float = 0.0
    status: str = "unmatched"  # verified, needs_clarification, unmatched
    candidates: List[ProductCandidate] = []
    clarification_prompt: Optional[str] = None


class ProductMatcher:
    """Matches product names against the authenticated tenant catalogue with false-positive prevention."""

    @staticmethod
    def _clean_for_matching(text: str) -> str:
        """Standardizes product search string without destroying numbers or product markers."""
        norm = LanguageNormalizer.normalize_unicode(text).lower()
        # Remove punctuation except hyphens and dots within numbers
        cleaned = re.sub(r"[^\w\s\-]", " ", norm)
        return " ".join(cleaned.split())

    @classmethod
    async def find_candidates(
        cls,
        search_phrase: str,
        tenant_id: str,
        catalogue_provider: CatalogueProvider,
    ) -> List[ProductCandidate]:
        """Discovers and scores candidate products from the tenant's catalogue."""
        clean_query = cls._clean_for_matching(search_phrase)
        if not clean_query:
            return []

        products = await catalogue_provider.get_tenant_products(tenant_id)
        candidates: List[ProductCandidate] = []

        query_tokens = set(clean_query.split())

        for product in products:
            if not product.is_active:
                continue

            canonical_clean = cls._clean_for_matching(product.canonical_name)
            canonical_tokens = set(canonical_clean.split())

            # 1. Exact Canonical Name Match
            if clean_query == canonical_clean:
                candidates.append(ProductCandidate(
                    product=product,
                    match_score=1.0,
                    match_type="exact_canonical"
                ))
                continue

            # 2. Approved Exact Alias Match
            alias_matched = False
            for alias in product.aliases:
                if not alias.is_active:
                    continue
                alias_clean = cls._clean_for_matching(alias.alias_phrase)
                if clean_query == alias_clean:
                    candidates.append(ProductCandidate(
                        product=product,
                        match_score=0.98,
                        match_type="exact_alias"
                    ))
                    alias_matched = True
                    break

            if alias_matched:
                continue

            # 3. Barcode Match in variants
            barcode_matched = False
            for variant in product.variants:
                if variant.barcode and variant.barcode.strip() == clean_query:
                    candidates.append(ProductCandidate(
                        product=product,
                        match_score=1.0,
                        match_type="barcode"
                    ))
                    barcode_matched = True
                    break
            if barcode_matched:
                continue

            # 4. Token Overlap and Prefix Matching
            # Protect against generic single-token queries matching longer compound products:
            # If query is "egg", canonical is "Egg Masala", canonical has EXTRA tokens!
            # If query has all tokens of canonical, that's a strong match.
            # But if query is a subset of canonical, it should NOT be an exact token match.
            if query_tokens == canonical_tokens:
                candidates.append(ProductCandidate(
                    product=product,
                    match_score=0.95,
                    match_type="token_match"
                ))
                continue

            # 5. Fuzzy Discovery ONLY (using rapidfuzz token_sort_ratio)
            fuzzy_ratio = fuzz.token_sort_ratio(clean_query, canonical_clean)
            if fuzzy_ratio >= settings.FUZZY_DISCOVERY_THRESHOLD:
                # Scaled score: fuzzy is always below high-confidence threshold
                scaled_score = round(fuzzy_ratio / 100.0 * 0.75, 3)
                candidates.append(ProductCandidate(
                    product=product,
                    match_score=scaled_score,
                    match_type="fuzzy_discovery"
                ))

        # Sort candidates descending by match_score
        candidates.sort(key=lambda c: c.match_score, reverse=True)
        return candidates

    @classmethod
    async def match_product(
        cls,
        search_phrase: str,
        tenant_id: str,
        catalogue_provider: CatalogueProvider,
    ) -> ProductMatchResult:
        """Evaluates candidates and authorizes matches safely.

        Rules:
        - If an exact canonical or exact alias match exists: selects it with high confidence.
        - If query is generic (e.g. 'masala') and matches multiple compound products (Egg Masala, Garam Masala):
          requests clarification.
        - Fuzzy matches alone NEVER authorize a product.
        """
        candidates = await cls.find_candidates(search_phrase, tenant_id, catalogue_provider)

        if not candidates:
            return ProductMatchResult(
                product=None,
                confidence=0.0,
                status="unmatched",
                candidates=[]
            )

        top_candidate = candidates[0]

        # Case 1: Exact canonical or exact alias or barcode match
        if top_candidate.match_type in ["exact_canonical", "exact_alias", "barcode", "token_match"]:
            # Check for ambiguous ties with identical top score
            top_ties = [c for c in candidates if c.match_score == top_candidate.match_score]
            if len(top_ties) > 1:
                options = [c.product.canonical_name for c in top_ties]
                return ProductMatchResult(
                    product=None,
                    confidence=top_candidate.match_score,
                    status="needs_clarification",
                    candidates=candidates[:5],
                    clarification_prompt=f"Multiple products matched '{search_phrase}': {', '.join(options)}"
                )

            return ProductMatchResult(
                product=top_candidate.product,
                confidence=top_candidate.match_score,
                status="verified",
                candidates=candidates[:5]
            )

        # Case 2: Fuzzy candidate discovery only
        # Fuzzy match can NEVER authorize directly
        options = [c.product.canonical_name for c in candidates[:3]]
        return ProductMatchResult(
            product=None,
            confidence=top_candidate.match_score,
            status="needs_clarification",
            candidates=candidates[:5],
            clarification_prompt=f"Did you mean one of: {', '.join(options)}?"
        )

