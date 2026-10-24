"""Input guardrails: mask personal data before it reaches the LLM, the
cache, the traces or the logs.  Pure regex, no dependencies."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    # Egyptian national ID: 14 digits starting with 2 or 3 (century digit)
    ("national_id", re.compile(r"(?<!\d)[23]\d{13}(?!\d)")),
    # Egyptian mobile numbers (010/011/012/015, optional +20 / 0020)
    ("phone", re.compile(r"(?<!\d)(?:\+20|0020)?0?1[0125]\d{8}(?!\d)")),
    # payment card numbers: 13-19 digits, optionally grouped by space/dash
    ("card", re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")),
)


@dataclass
class RedactionResult:
    text: str
    found: list[str] = field(default_factory=list)

    @property
    def redacted(self) -> bool:
        return bool(self.found)


def redact_pii(text: str) -> RedactionResult:
    """Replace PII with ``[<kind>]`` placeholders. Article numbers (<=4
    digits) can never match any pattern."""
    working = text.translate(_ARABIC_DIGITS)
    found: list[str] = []
    for kind, pattern in _PATTERNS:
        def _mask(_m: re.Match[str], kind: str = kind) -> str:
            found.append(kind)
            return f"[{kind}]"

        working = pattern.sub(_mask, working)
    if not found:
        return RedactionResult(text=text)
    return RedactionResult(text=working, found=found)


_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore\s+(all\s+|any\s+)?(previous|prior|above)\s+(instructions|rules|prompts?)",
        r"disregard\s+(the\s+)?(system|previous)\s+(prompt|instructions)",
        r"(reveal|show|print)\s+(your\s+|the\s+)?(system\s+prompt|instructions)",
        r"you\s+are\s+now\s+(dan|an?\s+unrestricted)",
        r"(تجاهل|تناسى|انس)\w*\s+(كل\s+|جميع\s+)?(التعليمات|الأوامر|الاوامر)",
        r"(اكشف|اعرض|اطبع)\s+(لي\s+)?(التعليمات|البرومبت)\s*(السابقة|الخاصة|الداخلية)?",
        r"(prompt|برومبت)\s*(النظام|الداخلي)",
    )
)

INJECTION_REFUSAL = (
    "لا أستطيع تنفيذ هذا الطلب. أنا مساعد للإجابة عن أسئلة القانون المدني "
    "المصري فقط؛ اطرح سؤالك القانوني وسأجيب من نصوص المواد."
)


def detect_injection(text: str) -> bool:
    """Heuristic prompt-injection / jailbreak detector (cheap, no LLM call)."""
    return any(p.search(text) for p in _INJECTION_PATTERNS)
