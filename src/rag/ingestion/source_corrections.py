"""Documented, evidence-based corrections for defects of THIS specific PDF.

Every entry is explicit, guarded by a precondition (it refuses to apply, loudly, if the parsed text
is not what the evidence was based on) and recorded in
``data/interim/source_corrections_applied.json``
so legal text never changes silently. Nothing here writes legal text from memory: corrections only
MOVE text that is already in the PDF, and what the PDF lacks stays flagged as incomplete.
"""

from __future__ import annotations

import re
from typing import Any

from core.models import Article

# Cleaned English of Article 1022 re-read from the PDF (pp. 147-148). The extractor interleaved two
# line fragments ("cost, he has always" / "carrying out these works at his own") and cut the first
# line; the words below are exactly the PDF's own English, reordered.
_EN_1022 = (
    "In the absence of an agreement to the contrary, the cost of the necessary works for the use "
    "and preservation of the servitude must be borne by the owner of the dominant tenement. "
    "If the owner of the servient tenement is responsible for carrying out these works at his own "
    "cost, he has always the right to free himself of this burden by abandoning the servient "
    "tenement wholly or in part to the owner of the dominant property. If the works also benefit "
    "the owner of the servient tenement, the cost of upkeep falls on the two parties in proportion "
    "to the profit derived by each of them."
)
_PARA_2 = re.compile(r"\(\s*2\s*[()]")


class CorrectionError(RuntimeError):
    """A precondition of a documented correction no longer holds (source or parser changed)."""


def _relocate_1021_1022(by_number: dict[int, Article]) -> dict[str, Any]:
    a1021, a1022 = by_number[1021], by_number[1022]
    if a1022.text.strip():
        raise CorrectionError("SC-1021-1022: Article 1022 already has Arabic text; review the rule")
    m = _PARA_2.search(a1021.text)
    if not m or "التخلي" not in a1021.text[m.start():] or "نفقة الصيانة" not in a1021.text:
        raise CorrectionError("SC-1021-1022: expected paragraphs (2),(3) not found in Article 1021")
    keep, moved = a1021.text[: m.start()].rstrip(), a1021.text[m.start():].strip()
    a1021.text = keep
    a1022.text = moved
    a1022.text_en = _EN_1022
    a1022.text_incomplete = True  # paragraph (1) of the Arabic text is absent from the PDF
    return {
        "id": "SC-1021-1022",
        "articles": [1021, 1022],
        "action": "moved Arabic paragraphs (2)-(3) from the Article 1021 block to Article 1022; "
                  "Article 1022 marked text_incomplete (Arabic paragraph (1) is not in the PDF)",
        "evidence": "PDF pp.147-148: the English translation of Article 1021 has one paragraph "
                    "(servient owner not obliged to carry out works) while the Arabic block under "
                    "its marker has three; the English of Article 1022 contains the sentences that "
                    "match Arabic paragraphs (2) (free himself by abandoning the servient "
                    "tenement) and (3) (cost of upkeep shared in proportion to benefit). The "
                    "Arabic sentence matching English paragraph (1) of 1022 is absent.",
        "needs_review": "Fill Article 1022 paragraph (1) from an official Arabic edition and "
                        "confirm this relocation against it.",
    }


def apply_source_corrections(articles: list[Article]) -> list[dict[str, Any]]:
    by_number = {a.number: a for a in articles}
    return [_relocate_1021_1022(by_number)]
