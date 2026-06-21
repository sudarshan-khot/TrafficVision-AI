"""
OCR post-processing utilities for Indian number plate text.

Requirements: 2.5
"""
from __future__ import annotations

import re

# Indian vehicle registration format: e.g. MH12DE1433
_PLATE_PATTERN = re.compile(
    r"^[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}$"
)


def clean_plate_text(raw: str) -> str | None:
    """
    Validate and normalise raw OCR output to a standard Indian plate string.

    Parameters
    ----------
    raw:
        Raw text returned by PaddleOCR.

    Returns
    -------
    str | None
        Normalised plate text (uppercase, no spaces) or ``None`` when no valid
        Indian plate pattern is found.
    """
    if not raw:
        return None

    # Strip whitespace and common separators, then uppercase.
    normalised = re.sub(r"[\s\-_]", "", raw.strip().upper())
    if not normalised:
        return None

    # Try the full string first, then search for an embedded match.
    if _PLATE_PATTERN.match(normalised):
        return normalised

    embedded = re.search(
        r"[A-Z]{2}[0-9]{1,2}[A-Z]{1,3}[0-9]{4}",
        normalised,
    )
    if embedded and _PLATE_PATTERN.match(embedded.group(0)):
        return embedded.group(0)

    return None
