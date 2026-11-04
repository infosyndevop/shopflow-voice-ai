"""Language Normalization for multilingual South Indian retail environments.

Supports Malayalam (Unicode U+0D00..U+0D7F), Tamil (Unicode U+0B80..U+0BFF),
English, and mixed code-switching conversations.
Preserves digits, decimal points, hyphens, and numeric product names (e.g. "20-20", "002").
"""

import re
import unicodedata
from typing import Dict, List, Optional


# Common phonetic colloquialisms/suffixes in Malayalam/Tamil retail conversations
COLLOQUIAL_SUFFIX_RE = re.compile(
    r"\b([a-zA-Z\u0D00-\u0D7F\u0B80-\u0BFF]+)(?:-(?:um|aa|inte|ude|oda|ku|kku|il))\b",
    re.IGNORECASE
)

# Common colloquial unit variants
UNIT_MAP = {
    "kilo": "kg",
    "kilos": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "കിലോ": "kg",
    "கிலோ": "kg",
    "gram": "g",
    "grams": "g",
    "gm": "g",
    "ഗ്രാം": "g",
    "கிராம்": "g",
    "packet": "packet",
    "packets": "packet",
    "pkt": "packet",
    "പാക്കറ്റ്": "packet",
    "பாக்கெட்": "packet",
    "piece": "piece",
    "pieces": "piece",
    "pcs": "piece",
    "pc": "piece",
    "എണ്ണം": "piece",
    "பீஸ்": "piece",
    "litre": "litre",
    "litres": "litre",
    "liter": "litre",
    "liters": "litre",
    "ltr": "litre",
    "ലിറ്റർ": "litre",
    "லிட்டர்": "litre",
    "milli": "ml",
    "millilitre": "ml",
    "മില്ലി": "ml",
    "மில்லி": "ml",
    "box": "box",
    "boxes": "box",
    "പെട്ടി": "box",
    "பெட்டி": "box",
}


class LanguageNormalizer:
    """Deterministic normalizer for multilingual retail input."""

    @staticmethod
    def normalize_unicode(text: str) -> str:
        """Applies NFKC normalization and trims extra whitespace."""
        if not text:
            return ""
        # Normalizes Unicode (canonical decomposition followed by canonical composition)
        normalized = unicodedata.normalize("NFKC", text)
        # Collapse multiple whitespace to single space
        return " ".join(normalized.split())

    @staticmethod
    def clean_retail_text(text: str) -> str:
        """Sanitizes text while preserving alphanumeric characters, decimals, and product hyphens."""
        norm = LanguageNormalizer.normalize_unicode(text)
        # Preserve Unicode Malayalam, Tamil, English alphabets, numbers, hyphens, and dots in numbers
        # Remove unsupported symbols, control characters, or erratic quotes
        cleaned = re.sub(r"[^\w\s\.\-]", " ", norm, flags=re.UNICODE)
        # Ensure single spaces
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @classmethod
    def normalize(cls, raw_transcript: str, shop_aliases: Optional[Dict[str, str]] = None) -> str:
        """Normalizes transcript deterministically:

        1. Unicode normalization (NFKC).
        2. Preservation of numbers, leading zeros, and product markers (e.g. '20-20', '002').
        3. Collapsing whitespace.
        4. Matching and substituting approved shop-specific aliases without destroying product tokens.
        """
        if not raw_transcript:
            return ""

        cleaned = cls.clean_retail_text(raw_transcript)
        tokens = cleaned.split()
        normalized_tokens = []

        for token in tokens:
            lower_token = token.lower()
            # Standardize unit representations if token matches
            if lower_token in UNIT_MAP:
                normalized_tokens.append(UNIT_MAP[lower_token])
            else:
                normalized_tokens.append(token)

        normalized_str = " ".join(normalized_tokens)

        # Apply shop-specific exact alias substitutions if provided
        if shop_aliases:
            for alias_key, canonical in shop_aliases.items():
                pattern = re.compile(rf"\b{re.escape(alias_key)}\b", re.IGNORECASE)
                normalized_str = pattern.sub(canonical, normalized_str)

        return normalized_str

