"""Quantity, Unit, Package-Size, and Price-Reference Parser.

Strictly isolates:
- Order quantity (e.g. 3 packets)
- Package size (e.g. 160g)
- Price references (e.g. 10 rupees)
- Numeric product brands (e.g. 20-20 Butter Cookies)
"""

import re
from typing import List, Optional, Tuple
from pydantic import BaseModel
from app.core.config import settings
from app.services.voice.number_parser import NumberParser

PRICE_MARKERS = {
    "rupee", "rupees", "rs", "inr", "രൂപ", "ரூபாய்", "ruba", "rooba", "roopya"
}

STANDARD_UNITS = {
    "piece", "packet", "box", "kg", "g", "litre", "ml"
}

# Regex to detect price patterns: e.g. "10 rupees", "ten rs", "50 രൂപ"
PRICE_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?|[a-zA-Z\u0D00-\u0D7F\u0B80-\u0BFF]+)\s*(?:rupees|rupee|rs|രൂപ|ரூபாய்|ruba|rooba)\b",
    re.IGNORECASE
)

# Regex to detect package size expressions: e.g. "160 gram", "100g", "1 kg", "500 ml", "1 litre"
PACKAGE_SIZE_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(kg|g|gram|grams|gm|ml|milli|litre|liter|ltr|ലിറ്റർ|ഗ്രാം|கிலோ|கிராம்)\b",
    re.IGNORECASE
)

# Known numeric brand patterns to protect from quantity stripping
KNOWN_NUMERIC_BRANDS = [
    re.compile(r"\b20[- ]20\b", re.IGNORECASE),
    re.compile(r"\b50[- ]50\b", re.IGNORECASE),
    re.compile(r"\b7[- ]up\b", re.IGNORECASE),
    re.compile(r"\b3[- ]roses\b", re.IGNORECASE),
]


class ParsedQuantityResult(BaseModel):
    quantity: Optional[float] = None
    unit: Optional[str] = None
    package_size: Optional[str] = None
    price_reference: Optional[float] = None
    remaining_text: str = ""
    is_ambiguous: bool = False
    clarification_reason: Optional[str] = None


class QuantityParser:
    """Extracts verified quantities, package sizes, and price references without false positives."""

    @classmethod
    def parse(cls, input_phrase: str) -> ParsedQuantityResult:
        """Parses an input speech segment or phrase.

        Ensures numeric brand names (like '20-20') are protected and price references
        are not confused with quantity.
        """
        text = input_phrase.strip()
        if not text:
            return ParsedQuantityResult(remaining_text="", is_ambiguous=True, clarification_reason="Empty input")

        # Step 1: Protect numeric product names by placeholder
        brand_placeholders = {}
        for idx, pattern in enumerate(KNOWN_NUMERIC_BRANDS):
            match = pattern.search(text)
            if match:
                placeholder = f"__BRAND_NUMERIC_{idx}__"
                brand_placeholders[placeholder] = match.group(0)
                text = pattern.sub(placeholder, text)

        # Step 2: Extract and isolate price references (e.g. "10 rupees biscuit")
        price_ref: Optional[float] = None
        price_match = PRICE_PATTERN.search(text)
        if price_match:
            price_val_token = price_match.group(1)
            parsed_price = NumberParser.parse_compound_number(price_val_token.split())
            if parsed_price is not None and parsed_price > 0:
                price_ref = parsed_price
            # Strip the price reference from text so it is not parsed as order quantity
            text = PRICE_PATTERN.sub(" ", text).strip()

        # Step 3: Extract package size (e.g. "160 gram", "100g")
        package_size_str: Optional[str] = None
        pkg_match = PACKAGE_SIZE_PATTERN.search(text)
        if pkg_match:
            pkg_val = pkg_match.group(1)
            pkg_unit = pkg_match.group(2).lower()
            # Normalize unit
            if pkg_unit in ["kg", "കിലോ"]:
                standard_pkg_unit = "kg"
            elif pkg_unit in ["g", "gram", "grams", "gm", "ഗ്രാം", "கிராம்"]:
                standard_pkg_unit = "g"
            elif pkg_unit in ["ml", "milli", "മില്ലി", "மில்லி"]:
                standard_pkg_unit = "ml"
            elif pkg_unit in ["litre", "liter", "ltr", "ലിറ്റർ", "லிட்டர்"]:
                standard_pkg_unit = "L"
            else:
                standard_pkg_unit = pkg_unit

            package_size_str = f"{pkg_val}{standard_pkg_unit}"
            # Remove the package size from the text
            text = PACKAGE_SIZE_PATTERN.sub(" ", text).strip()
            # Also clean up "of" if phrase was "packets of 160 gram"
            text = re.sub(r"\bof\b", " ", text, flags=re.IGNORECASE)

        # Step 4: Extract order quantity and unit
        tokens = text.split()
        quantity: Optional[float] = None
        unit: Optional[str] = None
        remaining_tokens: List[str] = []

        i = 0
        while i < len(tokens):
            token = tokens[i]

            # Check if this token starts a quantity number
            # Try 1 or 2 tokens for compound numbers (e.g. "two and a half", "twenty five", "രണ്ടര")
            num_candidate = None
            consumed_tokens = 0

            # Check 3 tokens: e.g. "two and a half" -> handled by number parser
            if i + 3 <= len(tokens):
                candidate_3 = NumberParser.parse_compound_number(tokens[i:i+3])
                if candidate_3 is not None and candidate_3 > 0:
                    num_candidate = candidate_3
                    consumed_tokens = 3

            # Check 2 tokens: e.g. "twenty five", "രണ്ട് പാക്കറ്റ്"
            if num_candidate is None and i + 2 <= len(tokens):
                candidate_2 = NumberParser.parse_compound_number(tokens[i:i+2])
                if candidate_2 is not None and candidate_2 > 0:
                    num_candidate = candidate_2
                    consumed_tokens = 2

            # Check 1 token: e.g. "three", "3", "ഒന്ന്"
            if num_candidate is None:
                candidate_1 = NumberParser.parse_compound_number([token])
                if candidate_1 is not None and candidate_1 > 0:
                    num_candidate = candidate_1
                    consumed_tokens = 1

            if num_candidate is not None and quantity is None:
                # We found our order quantity candidate
                quantity = num_candidate
                i += consumed_tokens

                # Check if the next token is an explicit unit (packet, piece, kg, box, etc.)
                if i < len(tokens):
                    next_token_lower = tokens[i].lower()
                    if next_token_lower in ["packet", "packets", "pkt", "പാക്കറ്റ്", "பாக்கெட்"]:
                        unit = "packet"
                        i += 1
                    elif next_token_lower in ["piece", "pieces", "pcs", "pc", "എണ്ണം", "பீஸ்"]:
                        unit = "piece"
                        i += 1
                    elif next_token_lower in ["kg", "kilo", "kilogram", "കിലോ"]:
                        unit = "kg"
                        i += 1
                    elif next_token_lower in ["box", "boxes", "പെട്ടി", "பெட்டி"]:
                        unit = "box"
                        i += 1
                    elif next_token_lower in ["litre", "liter", "ltr", "ലിറ്റർ"]:
                        unit = "litre"
                        i += 1
                    elif next_token_lower in ["g", "gram", "gm", "ഗ്രാം"]:
                        unit = "g"
                        i += 1
                continue
            elif num_candidate is not None and quantity is not None:
                # A second quantity candidate was found! This is ambiguous.
                # e.g., "give me two or maybe three soaps"
                remaining_tokens.append(token)
                i += 1
                return ParsedQuantityResult(
                    quantity=None,
                    unit=unit,
                    package_size=package_size_str,
                    price_reference=price_ref,
                    remaining_text=" ".join(tokens),
                    is_ambiguous=True,
                    clarification_reason=f"Ambiguous or conflicting multiple quantities detected in speech"
                )
            else:
                remaining_tokens.append(token)
                i += 1

        # Reconstruct remaining phrase and restore protected brand names
        remaining_str = " ".join(remaining_tokens)
        for placeholder, original_brand in brand_placeholders.items():
            remaining_str = remaining_str.replace(placeholder, original_brand)

        # Clean excess spaces
        remaining_str = re.sub(r"\s+", " ", remaining_str).strip()

        # Validation rules:
        # Rule: Quantity cannot be <= 0
        if quantity is not None and quantity <= 0:
            return ParsedQuantityResult(
                quantity=None,
                unit=unit,
                package_size=package_size_str,
                price_reference=price_ref,
                remaining_text=remaining_str,
                is_ambiguous=True,
                clarification_reason="Negative or zero quantities are invalid"
            )

        # Rule: Quantity limit check
        if quantity is not None and quantity > settings.DEFAULT_MAX_QUANTITY:
            return ParsedQuantityResult(
                quantity=quantity,
                unit=unit,
                package_size=package_size_str,
                price_reference=price_ref,
                remaining_text=remaining_str,
                is_ambiguous=True,
                clarification_reason=f"Quantity {quantity} exceeds safe retail limit ({settings.DEFAULT_MAX_QUANTITY})"
            )

        # Rule: Round decimal places to configured limit
        if quantity is not None:
            quantity = round(quantity, settings.MAX_DECIMAL_PLACES)

        return ParsedQuantityResult(
            quantity=quantity,
            unit=unit,
            package_size=package_size_str,
            price_reference=price_ref,
            remaining_text=remaining_str,
            is_ambiguous=False
        )
