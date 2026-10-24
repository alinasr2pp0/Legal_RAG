# -*- coding: utf-8 -*-
"""
Utility for lightweight Arabic text normalization.
- Removes diacritics (tashkeel, tanween, shadda, etc.)
- Translates Arabic‑Indic digits to ASCII
- Collapses multiple spaces
"""

import re

# Regex for Arabic diacritics (including tashkeel and tatweel)
_ARABIC_DIACRITICS = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0670\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED]")

# Translation table for Arabic‑Indic digits
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_arabic(text: str) -> str:
    """Normalize Arabic text for consistent embedding/retrieval.

    Steps:
    1. Remove diacritics.
    2. Translate Arabic‑Indic digits to ASCII.
    3. Collapse whitespace and strip.
    """
    text = _ARABIC_DIACRITICS.sub("", text)
    text = text.translate(_AR_DIGITS)
    # Collapse multiple spaces/tabs/newlines into a single space
    text = re.sub(r"\s+", " ", text).strip()
    return text
