"""Multilingual number parser supporting English, Malayalam, and Tamil spoken numerals.

Handles numeric digits, decimal fractions, spoken digit sequences, and compound number words.
"""

from typing import Dict, List, Optional, Tuple
import re

DIGIT_WORD_MAP: Dict[str, str] = {
    # English digits
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    # Malayalam digits / numbers
    "പൂജ്യം": "0", "ഒന്ന്": "1", "രണ്ട്": "2", "മൂന്ന്": "3", "നാല്": "4",
    "അഞ്ച്": "5", "ആറ്": "6", "ഏഴ്": "7", "എട്ട്": "8", "ഒമ്പത്": "9",
    # Malayalam transliterated
    "poojyam": "0", "onnu": "1", "randu": "2", "moonu": "3", "moonn": "3",
    "nalu": "4", "naalu": "4", "anju": "5", "aaru": "6", "ezhu": "7",
    "ettu": "8", "ompathu": "9",
    # Tamil digits / numbers
    "பூஜ்ஜியம்": "0", "ஒன்று": "1", "இரண்டு": "2", "மூன்று": "3", "நான்கு": "4",
    "ஐந்து": "5", "ஆறு": "6", "ஏழு": "7", "எட்டு": "8", "ஒன்பது": "9",
    # Tamil transliterated
    "poojiyam": "0", "ondru": "1", "rendu": "2", "irandu": "2",
    "moondru": "3", "naangu": "4", "aindhu": "5", "anji": "5", "onbadhu": "9",
}

MAGNITUDE_MAP: Dict[str, float] = {
    # English
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000,
    # English fractions
    "quarter": 0.25, "half": 0.5,
    # Malayalam tens & hundreds
    "പത്ത്": 10, "പതിനൊന്ന്": 11, "പന്ത്രണ്ട്": 12, "പതിമൂന്ന്": 13, "പതിനാല്": 14,
    "പതിനഞ്ച്": 15, "പതിനാറ്": 16, "പതിനേഴ്": 17, "പതിനെട്ട്": 18, "പത്തൊമ്പത്": 19,
    "ഇരുപത്": 20, "മുപ്പത്": 30, "നാല്പത്": 40, "അമ്പത്": 50, "അറുപത്": 60,
    "എഴുപത്": 70, "എൺപത്": 80, "തൊണ്ണൂറ്": 90, "നൂറ്": 100, "ആയിരം": 1000,
    # Malayalam fractions
    "കാൽ": 0.25, "അര": 0.5, "മുക്കാൽ": 0.75,
    "ഒന്നര": 1.5, "രണ്ടര": 2.5, "മൂന്നര": 3.5, "നാലര": 4.5,
    # Malayalam transliterated
    "pathu": 10, "irupathu": 20, "muppathu": 30, "nooru": 100,
    "kaal": 0.25, "ara": 0.5, "mukkal": 0.75, "onnara": 1.5, "randara": 2.5,
    # Tamil tens & hundreds
    "பத்து": 10, "பதினொன்று": 11, "பன்னிரண்டு": 12, "பதின்மூன்று": 13, "பதினான்கு": 14,
    "பதினைந்து": 15, "பதினாறு": 16, "பதினேழு": 17, "பதினெட்டு": 18, "பத்தொன்பது": 19,
    "இருபது": 20, "முப்பது": 30, "நாற்பது": 40, "ஐம்பது": 50, "அறுபது": 60,
    "எழுபது": 70, "எண்பது": 80, "தொண்ணூறு": 90, "நூறு": 100, "ஆயிரம்": 1000,
    # Tamil fractions
    "அரை": 0.5, "முக்கால்": 0.75, "ஒன்றரை": 1.5, "இரண்டரை": 2.5,
    # Tamil transliterated
    "irubadhu": 20, "muppadhu": 30, "arai": 0.5, "ondrarai": 1.5, "rendarai": 2.5,
}


class NumberParser:
    """Parses spoken number words, digit sequences, and fractions across EN, ML, and TA."""

    @staticmethod
    def parse_digit_sequence(tokens: List[str]) -> Optional[str]:
        """Converts sequences of spoken digits (e.g., ['zero', 'zero', 'two'] or ['0', '0', '2'])

        into an exact string preserving leading zeros.
        Returns None if not all tokens are single digits.
        """
        digits: List[str] = []
        for t in tokens:
            cleaned = t.lower().strip()
            if cleaned in DIGIT_WORD_MAP:
                digits.append(DIGIT_WORD_MAP[cleaned])
            elif cleaned.isdigit() and len(cleaned) == 1:
                digits.append(cleaned)
            else:
                return None
        return "".join(digits) if digits else None

    @classmethod
    def parse_single_token(cls, token: str) -> Optional[float]:
        """Attempts to parse a single word or numeral into a numeric float."""
        clean = token.lower().strip()
        # Direct float or integer string
        if re.match(r"^\d+(\.\d+)?$", clean):
            try:
                return float(clean)
            except ValueError:
                return None

        # Direct digit word (0-9)
        if clean in DIGIT_WORD_MAP:
            return float(DIGIT_WORD_MAP[clean])

        # Named number or fraction
        if clean in MAGNITUDE_MAP:
            return float(MAGNITUDE_MAP[clean])

        return None

    @classmethod
    def parse_compound_number(cls, tokens: List[str]) -> Optional[float]:
        """Parses a sequence of words representing a compound number (e.g.

        ['twenty', 'five'] -> 25.0
        ['two', 'and', 'a', 'half'] -> 2.5
        ['one', 'hundred', 'fifty'] -> 150.0
        """
        if not tokens:
            return None

        # Check for fractional compound phrases like "two and a half", "രണ്ടര"
        phrase = " ".join([t.lower() for t in tokens])
        if phrase in MAGNITUDE_MAP:
            return float(MAGNITUDE_MAP[phrase])

        # Check for "X and a half" pattern
        half_match = re.match(r"^(.+?)\s+(and\s+a\s+half|and\s+half)$", phrase)
        if half_match:
            base_tokens = half_match.group(1).split()
            base_val = cls.parse_compound_number(base_tokens)
            if base_val is not None:
                return base_val + 0.5

        # Single token fast path
        if len(tokens) == 1:
            return cls.parse_single_token(tokens[0])

        current_val = 0.0
        running_sum = 0.0

        for token in tokens:
            t_lower = token.lower()
            val = cls.parse_single_token(t_lower)
            if val is None:
                return None

            if val == 1000:
                current_val = (current_val if current_val > 0 else 1.0) * 1000
                running_sum += current_val
                current_val = 0.0
            elif val == 100:
                current_val = (current_val if current_val > 0 else 1.0) * 100
            else:
                current_val += val

        total = running_sum + current_val
        return round(total, 4)
