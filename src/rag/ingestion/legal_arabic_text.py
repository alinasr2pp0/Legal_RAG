"""
Egyptian Legal Arabic text normalisation and tokenisation.

Designed for:
- Egyptian Arabic + Modern Standard Arabic
- Legal RAG / BM25 / hybrid retrieval
- Query rewriting and multi-query retrieval
- Legal article / law-number extraction
- Conservative normalisation that preserves legal meaning

Pure Python - no external dependencies.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# 1) Unicode / Arabic normalisation
# ---------------------------------------------------------------------------

_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
_CONTROL_CHARS = re.compile(r"[\u200B-\u200F\u202A-\u202E\u2060-\u206F]")
_MULTI_SPACE = re.compile(r"\s+")
_MULTI_PUNCT = re.compile(r"([!?؟،؛,:;.])\1+")

# Keep Arabic letters, English words, numbers, and common legal punctuation.
_TOKEN = re.compile(
    r"[a-zA-Z]+(?:[-_][a-zA-Z0-9]+)*"
    r"|[0-9]+(?:[./-][0-9]+)*"
    r"|[\u0621-\u063A\u0641-\u064A]+"
)

_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)

# IMPORTANT:
# Unlike the original file, we DO NOT:
# - remove hamza (ء)
# - convert ة -> ه
# - remove ئ / ؤ
#
# Those transformations can damage legal terminology.
_ARABIC_CHAR_MAP = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ـ": "",
    }
)


def normalize(text: str) -> str:
    """
    Conservative Arabic/English normalisation.

    Preserves legally meaningful letters such as:
    ء / ة / ئ / ؤ

    Normalises:
    - Unicode compatibility forms
    - diacritics
    - Arabic/Persian digits -> ASCII
    - Alef variants
    - tatweel
    - whitespace
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text).lower()
    text = _CONTROL_CHARS.sub("", text)
    text = _ARABIC_DIACRITICS.sub("", text)
    text = text.translate(_DIGITS)
    text = text.translate(_ARABIC_CHAR_MAP)
    text = _MULTI_PUNCT.sub(r"\1", text)
    text = _MULTI_SPACE.sub(" ", text)

    return text.strip()


# ---------------------------------------------------------------------------
# 2) Egyptian Arabic -> legal/standard canonical vocabulary
# ---------------------------------------------------------------------------
#
# Keep this map deliberately conservative.
# Do NOT map words when the mapping can change legal meaning.
#

_RAW_DIALECT_MAP: dict[str, str] = {
    # Questions / colloquial forms
    "ايه": "ماذا",
    "اي": "أي",
    "ليه": "لماذا",
    "ازاي": "كيف",
    "امتى": "متى",
    "فين": "أين",
    "مين": "من",
    "عايز": "يريد",
    "عاوز": "يريد",
    "مش": "ليس",
    "مفيش": "لا يوجد",
    "مافيش": "لا يوجد",

    # Common legal colloquial expressions
    "اتخانق": "تشاجر",
    "خناقة": "مشاجرة",
    "ضربني": "اعتدى",
    "اتضربت": "اعتداء",
    "اتحبس": "حبس",
    "اتمسك": "قبض",
    "اتقبض عليه": "قبض عليه",
    "اتطرد": "فصل",
    "طردني": "فصلني",
    "اترفدت": "فصلت",
    "رفد": "فصل",
    "اتحبست": "حبس",
    "حبسوني": "حبس",

    # Employment
    "شغلي": "عملي",
    "شغله": "عمل",
    "الشغل": "العمل",
    "مرتب": "أجر",
    "مرتبي": "أجري",
    "فلوس": "مال",
    "اجازة": "إجازة",
    "اجازه": "إجازة",
    "اتأمن": "تأمين",
    "التأمينات": "التأمينات",

    # Contracts / obligations
    "اتفاق": "عقد",
    "متفقين": "متعاقدين",
    "فسخ": "فسخ",
    "يلغي": "إلغاء",
    "كنسل": "إلغاء",
    "كنسلت": "إلغاء",
    "دفعت": "دفع",
    "بدفع": "دفع",
    "سددت": "سداد",

    # Property / tenancy
    "إيجار": "إيجار",
    "ايجار": "إيجار",
    "المؤجر": "المؤجر",
    "صاحب البيت": "المؤجر",
    "المستأجر": "المستأجر",

    # Common legal terms in English / Arabizi-like usage
    "contract": "عقد",
    "labor": "عمل",
    "employment": "عمل",
    "employee": "عامل",
    "employer": "صاحب العمل",
    "criminal": "جنائي",
    "civil": "مدني",
    "court": "محكمة",
    "appeal": "استئناف",
    "law": "قانون",
    "article": "مادة",
}


def _build_dialect_map() -> dict[str, str]:
    return {normalize(k): normalize(v) for k, v in _RAW_DIALECT_MAP.items()}


DIALECT_MAP = _build_dialect_map()


# ---------------------------------------------------------------------------
# 3) Legal stopwords
# ---------------------------------------------------------------------------
#
# Do not remove negation words such as "لا", "ليس", "لم", "لن".
# They can completely reverse legal meaning.
#

STOPWORDS = frozenset(
    """
    في من عن على إلى الى مع لدى عند بين خلال نحو حيث ثم أو او
    هذا هذه ذلك تلك الذي التي الذين اللاتي
    أنا انت أنت هو هي نحن هم
    كان كانت يكون تكون أصبح اصبح
    قد
    """.split()
)

# Words that should NEVER be removed in legal retrieval.
LEGAL_CRITICAL_WORDS = frozenset(
    """
    لا ليس لم لن غير دون إلا الا سوى ممن على
    يحق لايجوز يجوز يلزم يجب يحظر
    """.split()
)


# ---------------------------------------------------------------------------
# 4) Conservative stemming for BM25
# ---------------------------------------------------------------------------
#
# This is intentionally weaker than the original stemmer.
# Legal retrieval benefits more from preserving exact terms than from
# aggressive stemming.
#

_AR_PREFIXES = (
    "وال",
    "بال",
    "كال",
    "فال",
    "لل",
    "ال",
)

_AR_SUFFIXES = (
    "هما",
    "كما",
    "كم",
    "كن",
    "هم",
    "هن",
    "ها",
)

# Prefix/suffix stripping is only applied when the remaining token is long
# enough. We also avoid stemming tokens that look like legal identifiers.
_LEGAL_IDENTIFIER = re.compile(
    r"^(?:مادة|المادة|قانون|القانون|قرار|القرار|حكم|الحكم|لسنة|رقم|\d)"
)


def light_stem(token: str) -> str:
    """
    Conservative Arabic stemmer for lexical retrieval.

    It is NOT a linguistic root stemmer.
    Use it for BM25/keyword matching, not for displayed legal text.
    """
    if not token or token.isascii():
        if len(token) > 4 and token.endswith("s"):
            return token[:-1]
        return token

    if _LEGAL_IDENTIFIER.match(token):
        return token

    result = token

    for prefix in _AR_PREFIXES:
        # PROJECT FIX: remaining stem >= 3 (was 4). With 4, "العقد"/"الحق"/"الدين"
        # (3-letter roots, very common in law) were never stemmed, so "العقد" in a
        # query did not match "عقد"/"بالعقد" in the corpus.
        if result.startswith(prefix) and len(result) - len(prefix) >= 3:
            result = result[len(prefix):]
            break

    for suffix in _AR_SUFFIXES:
        if result.endswith(suffix) and len(result) - len(suffix) >= 4:
            result = result[: -len(suffix)]
            break

    return result


# ---------------------------------------------------------------------------
# 5) Tokenisation
# ---------------------------------------------------------------------------

def tokenize(
    text: str,
    *,
    drop_stopwords: bool = False,
    use_stemming: bool = False,
    apply_dialect_map: bool = True,
) -> list[str]:
    """
    Tokenise Arabic/English legal text.

    Defaults are deliberately conservative:
        drop_stopwords=False
        use_stemming=False

    For BM25 you can use:
        drop_stopwords=True, use_stemming=True

    For legal semantic retrieval, prefer:
        drop_stopwords=False, use_stemming=False
    """
    if not text:
        return []

    normalized = normalize(text)
    raw_tokens = _TOKEN.findall(normalized)

    tokens: list[str] = []

    for raw in raw_tokens:
        token = raw

        if apply_dialect_map:
            token = DIALECT_MAP.get(token, token)

        # Preserve critical legal negation even when stopword removal is on.
        if drop_stopwords:
            if token in STOPWORDS and token not in LEGAL_CRITICAL_WORDS:
                continue

        if use_stemming:
            token = light_stem(token)

        if len(token) < 2 and not token.isdigit():
            continue

        tokens.append(token)

    return tokens


def tokenize_for_bm25(text: str) -> list[str]:
    """Recommended lexical representation for BM25."""
    return tokenize(
        text,
        drop_stopwords=True,
        use_stemming=True,
        apply_dialect_map=True,
    )


def tokenize_for_semantic_search(text: str) -> list[str]:
    """Recommended token representation for diagnostics/debugging."""
    return tokenize(
        text,
        drop_stopwords=False,
        use_stemming=False,
        apply_dialect_map=True,
    )


# ---------------------------------------------------------------------------
# 6) Legal citation extraction
# ---------------------------------------------------------------------------

# Examples:
#   المادة 123
#   مادة 123
#   المادة رقم 123
#   قانون رقم 14 لسنة 2025
#   القانون رقم 14 لسنة 2025
#   قانون 14 لسنة 2025

ARTICLE_RE = re.compile(
    r"(?:المادة|مادة)\s*(?:رقم\s*)?(\d+(?:\s*مكرر)?)",
    flags=re.IGNORECASE,
)

LAW_RE = re.compile(
    r"(?:القانون|قانون)\s*(?:رقم\s*)?(\d+)"
    r"(?:\s*(?:لسنة|سنة)\s*(\d{4}))?",
    flags=re.IGNORECASE,
)

DECREE_RE = re.compile(
    r"(?:القرار|قرار)\s*(?:رقم\s*)?(\d+)"
    r"(?:\s*(?:لسنة|سنة)\s*(\d{4}))?",
    flags=re.IGNORECASE,
)


def extract_legal_references(text: str) -> dict[str, list[dict[str, str]]]:
    """
    Extract explicit legal references from a query/document.

    Returns:
        {
            "articles": [{"article": "123"}],
            "laws": [{"number": "14", "year": "2025"}],
            "decrees": [{"number": "...", "year": "..."}],
        }
    """
    normalized = normalize(text)

    articles = [
        {"article": match.group(1).replace(" ", "")}
        for match in ARTICLE_RE.finditer(normalized)
    ]

    laws = [
        {
            "number": match.group(1),
            "year": match.group(2) or "",
        }
        for match in LAW_RE.finditer(normalized)
    ]

    decrees = [
        {
            "number": match.group(1),
            "year": match.group(2) or "",
        }
        for match in DECREE_RE.finditer(normalized)
    ]

    return {
        "articles": articles,
        "laws": laws,
        "decrees": decrees,
    }


# ---------------------------------------------------------------------------
# 7) Legal query profile
# ---------------------------------------------------------------------------

def detect_language(text: str) -> str:
    """
    Lightweight language detector.
    Returns: 'ar', 'en', 'mixed', or 'unknown'.
    """
    if not text:
        return "unknown"

    arabic = sum("\u0600" <= ch <= "\u06FF" for ch in text)
    latin = sum(("a" <= ch.lower() <= "z") for ch in text)

    if arabic and latin:
        return "mixed"
    if arabic:
        return "ar"
    if latin:
        return "en"
    return "unknown"


def has_arabic(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06FF" for ch in text or "")


def has_egyptian_markers(text: str) -> bool:
    """
    Heuristic only. It must NOT be used as a legal-domain classifier.
    """
    normalized = normalize(text)
    markers = (
        "عايز",
        "عاوز",
        "مش",
        "مفيش",
        "ازاي",
        "ليه",
        "امتى",
        "فين",
        "الفلوس",
        "الشغل",
        "مرتب",
        "اترفدت",
    )
    return any(marker in normalized for marker in markers)


def legal_query_profile(text: str) -> dict[str, object]:
    """
    Build lightweight features for the Orchestrator / Legal Router.

    This function does NOT decide the legal answer or legal domain.
    It only prepares retrieval features.
    """
    normalized = normalize(text)
    references = extract_legal_references(normalized)

    return {
        "normalized_query": normalized,
        "language": detect_language(text),
        "has_arabic": has_arabic(text),
        "egyptian_markers": has_egyptian_markers(text),
        "tokens": tokenize_for_semantic_search(text),
        "bm25_tokens": tokenize_for_bm25(text),
        "legal_references": references,
    }


# ---------------------------------------------------------------------------
# 8) Retrieval-safe text
# ---------------------------------------------------------------------------

def prepare_for_bm25(text: str) -> str:
    """Return a whitespace-separated lexical representation for BM25."""
    return " ".join(tokenize_for_bm25(text))


def prepare_for_embedding(text: str) -> str:
    """
    Return text suitable for embedding.

    IMPORTANT:
    Do not use aggressive stemming or stopword removal before embeddings.
    Embedding models should receive readable legal language.
    """
    return normalize(text)


__all__ = [
    "normalize",
    "tokenize",
    "tokenize_for_bm25",
    "tokenize_for_semantic_search",
    "prepare_for_bm25",
    "prepare_for_embedding",
    "extract_legal_references",
    "legal_query_profile",
    "detect_language",
    "has_arabic",
    "has_egyptian_markers",
    "light_stem",
    "DIALECT_MAP",
    "STOPWORDS",
    "LEGAL_CRITICAL_WORDS",
]
