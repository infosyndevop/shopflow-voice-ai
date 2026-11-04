"""Tests for quantity, package-size, price-reference, and multilingual number parsing."""

import pytest
from app.services.voice.number_parser import NumberParser
from app.services.voice.quantity_parser import QuantityParser


def test_english_number_words():
    assert NumberParser.parse_compound_number(["two"]) == 2.0
    assert NumberParser.parse_compound_number(["twenty", "five"]) == 25.0
    assert NumberParser.parse_compound_number(["one", "hundred", "fifty"]) == 150.0
    assert NumberParser.parse_compound_number(["two", "and", "a", "half"]) == 2.5


def test_malayalam_number_words():
    # Native Malayalam Unicode
    assert NumberParser.parse_compound_number(["രണ്ട്"]) == 2.0
    assert NumberParser.parse_compound_number(["മൂന്ന്"]) == 3.0
    assert NumberParser.parse_compound_number(["പത്ത്"]) == 10.0
    assert NumberParser.parse_compound_number(["രണ്ടര"]) == 2.5

    # Transliterated Malayalam
    assert NumberParser.parse_compound_number(["randu"]) == 2.0
    assert NumberParser.parse_compound_number(["moonu"]) == 3.0
    assert NumberParser.parse_compound_number(["pathu"]) == 10.0
    assert NumberParser.parse_compound_number(["randara"]) == 2.5


def test_tamil_number_words():
    # Native Tamil Unicode
    assert NumberParser.parse_compound_number(["இரண்டு"]) == 2.0
    assert NumberParser.parse_compound_number(["மூன்று"]) == 3.0
    assert NumberParser.parse_compound_number(["பத்து"]) == 10.0
    assert NumberParser.parse_compound_number(["இரண்டரை"]) == 2.5

    # Transliterated Tamil
    assert NumberParser.parse_compound_number(["rendu"]) == 2.0
    assert NumberParser.parse_compound_number(["moondru"]) == 3.0


def test_spoken_digit_sequence():
    seq1 = NumberParser.parse_digit_sequence(["zero", "zero", "two"])
    assert seq1 == "002"

    seq2 = NumberParser.parse_digit_sequence(["പൂജ്യം", "പൂജ്യം", "രണ്ട്"])
    assert seq2 == "002"

    seq3 = NumberParser.parse_digit_sequence(["0", "0", "7"])
    assert seq3 == "007"


def test_quantity_extraction_basic():
    res = QuantityParser.parse("Two soaps")
    assert res.quantity == 2.0
    assert res.remaining_text == "soaps"
    assert not res.is_ambiguous


def test_quantity_with_package_size_and_unit():
    # "Three packets of 160 gram soap" -> Quantity = 3 packets, Package size = 160g
    res = QuantityParser.parse("Three packets of 160 gram soap")
    assert res.quantity == 3.0
    assert res.unit == "packet"
    assert res.package_size == "160g"
    assert "soap" in res.remaining_text


def test_price_reference_not_confused_with_quantity():
    # "Ten rupees biscuit" -> Price reference = 10, Quantity is NOT 10!
    res = QuantityParser.parse("Ten rupees biscuit")
    assert res.price_reference == 10.0
    assert res.quantity is None
    assert "biscuit" in res.remaining_text


def test_numeric_brand_preserved_not_stripped_as_quantity():
    # "20-20 Butter Cookies" -> 20-20 is part of brand, not quantity!
    res = QuantityParser.parse("20-20 Butter Cookies")
    assert res.quantity is None
    assert "20-20" in res.remaining_text or "20 20" in res.remaining_text

    # With explicit quantity: "Two 20-20 Butter Cookies"
    res2 = QuantityParser.parse("Two 20-20 Butter Cookies")
    assert res2.quantity == 2.0
    assert "20-20" in res2.remaining_text or "20 20" in res2.remaining_text


def test_ambiguous_multiple_quantities_rejected():
    # "give me two or three soaps"
    res = QuantityParser.parse("give me two or three soaps")
    assert res.is_ambiguous is True
    assert res.quantity is None
    assert "Ambiguous" in (res.clarification_reason or "")


def test_zero_or_negative_quantities_rejected():
    res1 = QuantityParser.parse("zero soaps")
    assert res1.is_ambiguous is True

    res2 = QuantityParser.parse("-5 soaps")
    assert res2.is_ambiguous is True
