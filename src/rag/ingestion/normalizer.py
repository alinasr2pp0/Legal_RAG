"""Arabic text normalization for legal text: unify hamza/alef forms, strip
tashkeel, normalize digits and whitespace — without altering legal meaning."""

from __future__ import annotations

import re

_TASHKEEL_RE = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0670\u06D6-\u06ED]")
_TATWEEL_RE = re.compile(r"\u0640")
_MULTI_SPACE_RE = re.compile(r"\s+")
# The bilingual PDF stores paragraph numbers right-to-left, so extraction yields ")1 (",
# "(1 (", "( )1 (" or "(1 .)" for "(1)". Safe to rewrite: a lone number in garbled brackets.
_PARA_NUMBER_RE = re.compile(r"\(\s*\)\s*(\d{1,2})\s*\(|[()]\s*(\d{1,2})\s*[.]?\s*[()]")

_ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_EXTENDED_ARABIC_INDIC_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

_ALEF_VARIANTS_RE = re.compile(r"[إأآا]")
_YAA_VARIANTS_RE = re.compile(r"ى")
_TAA_MARBUTA_RE = re.compile(r"ة")


class ArabicNormalizer:
    """Normalization is applied in two tiers: `light` (safe for legal text,
    preserves meaning) and `aggressive` (for embeddings/BM25 matching only —
    never use aggressive output for the text shown to the user)."""

    def light(self, text: str) -> str:
        text = _TASHKEEL_RE.sub("", text)
        text = _TATWEEL_RE.sub("", text)
        text = text.translate(_ARABIC_INDIC_DIGITS)
        text = text.translate(_EXTENDED_ARABIC_INDIC_DIGITS)
        text = _MULTI_SPACE_RE.sub(" ", text)
        text = _PARA_NUMBER_RE.sub(lambda m: f" ({m.group(1) or m.group(2)}) ", text)
        return _MULTI_SPACE_RE.sub(" ", text).strip()

    def aggressive(self, text: str) -> str:
        text = self.light(text)
        text = _ALEF_VARIANTS_RE.sub("ا", text)
        text = _YAA_VARIANTS_RE.sub("ي", text)
        text = _TAA_MARBUTA_RE.sub("ه", text)
        return text
