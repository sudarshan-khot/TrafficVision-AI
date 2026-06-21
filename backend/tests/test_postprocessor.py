"""Tests for OCR postprocessor."""
from __future__ import annotations

from app.ocr.postprocessor import clean_plate_text


class TestCleanPlateText:
    def test_valid_plate(self):
        assert clean_plate_text("MH12DE1433") == "MH12DE1433"

    def test_normalises_spaces_and_case(self):
        assert clean_plate_text("mh 12 de 1433") == "MH12DE1433"

    def test_invalid_plate_returns_none(self):
        assert clean_plate_text("NOTAPLATE") is None

    def test_empty_string_returns_none(self):
        assert clean_plate_text("") is None
