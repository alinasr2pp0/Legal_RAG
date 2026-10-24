"""Repairs for systematic text-extraction artifacts of the source PDF.

Found by inspecting the parsed output (not assumed):

1. **Lam-alef ligature order.** The PDF stores the ligature "لا" so that it is
   extracted as "ال" (and "لأ"/"لإ"/"لآ" as "أل"/"إل"/"آل").  Example:
   "الالتزام" comes out as "االلتزام", "الأرض" as "األرض".  That silently
   breaks lexical (BM25) matching against correctly spelled user queries.
2. **Reversed digit runs.** Multi-digit numbers inside Arabic text come out
   reversed ("المادة 362" is really article 263, "سنة 3881" is 1883).  That
   corrupts every in-text cross-reference.

The lam-alef repair is deliberately *rule based and conservative*: it only
rewrites patterns that cannot be a genuine Arabic spelling.  Genuinely
ambiguous spellings (e.g. "عمال" = عمال vs عملا) are left untouched.
"""

from __future__ import annotations

import re

MAX_ARTICLE_NUMBER = 1149  # the Egyptian Civil Code has articles 1..1149

_AR = "ء-ي"
# Optional single-letter prefix (و ف ب ك) before the article.
_PREFIX = "[وفبك]?"

# Word-initial: ا + (لأ|لإ|لآ|لا ligature extracted swapped) -> ال + (أ|إ|آ|ا)
_INITIAL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # "الال..." can only come from "اللا..." (article + word starting with لا).
    # Must run BEFORE the "اال" rule, whose output also contains "الال".
    (re.compile(rf"(?<![{_AR}])({_PREFIX})الال"), r"\1اللا"),
    (re.compile(rf"(?<![{_AR}])({_PREFIX})اإل"), r"\1الإ"),
    (re.compile(rf"(?<![{_AR}])({_PREFIX})األ"), r"\1الأ"),
    (re.compile(rf"(?<![{_AR}])({_PREFIX})اآل"), r"\1الآ"),
    (re.compile(rf"(?<![{_AR}])({_PREFIX})اال"), r"\1الا"),
    # preposition ل + article + ا-word: "للا..." extracted as "لال..."
    (re.compile(rf"(?<![{_AR}])لال"), "للا"),
    # preposition ل + article + hamza-word: "للأ.." extracted as "لأل.."
    (re.compile(rf"(?<![{_AR}])لأل"), "للأ"),
    (re.compile(rf"(?<![{_AR}])لإل"), "للإ"),
    (re.compile(rf"(?<![{_AR}])لآل"), "للآ"),
    # Anywhere inside a word these sequences cannot be genuine spellings
    # (double alef / alef+hamza-lam): they are swapped lam-alef ligatures, e.g.
    # "الحاالت" -> "الحالات", "مستشارااللجنة".
    (re.compile("اال"), "الا"),
    (re.compile("اإل"), "الإ"),
    (re.compile("األ"), "الأ"),
    (re.compile("اآل"), "الآ"),
    # "إلا" (except) is never validly spelled "إال"
    (re.compile(rf"(?<![{_AR}])([وف]?)إال(?![{_AR}])"), r"\1إلا"),
    # Standalone negation/particles: a bare "ال" is the word "لا" (no/not) --
    # the definite article never stands alone. Critical: it flips legal meaning
    # ("ال يجوز" = "لا يجوز").
    (re.compile(rf"(?<![{_AR}])([وفب]?)ال(?![{_AR}])"), r"\1لا"),
    (re.compile(rf"(?<![{_AR}])([وف]?)أال(?![{_AR}])"), r"\1ألا"),
    (re.compile(rf"(?<![{_AR}])لئال(?![{_AR}])"), "لئلا"),
)

# Residual mid-word cases that no pattern can decide ("عمال" = عمال or عملا?)
# but whose reading in a legal text is unambiguous. Base form -> repaired form;
# an optional prefix (و ف ب ك ل ال لل وال بال ...) is accepted.
_WORD_FIXES: dict[str, str] = {
    "ثالث": "ثلاث", "ثالثة": "ثلاثة", "ثالثين": "ثلاثين", "خالل": "خلال",
    "إخالل": "إخلال", "هؤالء": "هؤلاء", "بطالن": "بطلان", "باطال": "باطلا",
    "مسئوال": "مسئولا", "مسؤوال": "مسؤولا", "قابال": "قابلا", "منقوال": "منقولا",
    "منقوالت": "منقولات", "إعالن": "إعلان", "أجال": "أجلا", "مستحيال": "مستحيلا",
    "عادال": "عادلا", "أهال": "أهلا", "ماال": "مالا", "استغالل": "استغلال",
    "أصال": "أصلا", "كامال": "كاملا", "داخال": "داخلا", "استعماال": "استعمالا",
    "وكيال": "وكيلا", "مقبوال": "مقبولا", "أوال": "أولا", "إصالح": "إصلاح",
    "عمالئه": "عملائه", "عمالء": "عملاء", "استهالك": "استهلاك", "عدال": "عدلا",
    "ألحكام": "لأحكام", "ألصوله": "لأصوله", "ألرض": "لأرض", "ألشخاص": "لأشخاص",
    "ألوضاع": "لأوضاع", "إسالم": "إسلام", "إسالمية": "إسلامية",
}
_NO_ARTICLE = {"ثالث", "ثالثة", "ثالثين", "ألحكام", "ألصوله", "ألرض", "ألشخاص", "ألوضاع"}
_FIX_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (
        re.compile(
            rf"(?<![{_AR}])((?:وال|بال|فال|كال|لل|ال)?|[وفبكل]?)"
            rf"{re.escape(base)}(?![{_AR}])"
            if base not in _NO_ARTICLE
            else rf"(?<![{_AR}])([وفبكل]?){re.escape(base)}(?![{_AR}])"
        ),
        rf"\g<1>{fixed}",
    )
    for base, fixed in _WORD_FIXES.items()
)

_DIGITS = re.compile(r"(?<![\d.])\d{2,}(?![\d])")
_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def fix_lam_alef(text: str) -> str:
    for pattern, repl in _INITIAL_RULES:
        text = pattern.sub(repl, text)
    for pattern, repl in _FIX_PATTERNS:
        text = pattern.sub(repl, text)
    return text


_DATE = re.compile(r"(?<!\d)\.?(\d{4})/(\d{1,2})/(\d{1,2})(?!\d)")


def _flip_date(m: re.Match[str]) -> str:
    year, month, day = m.group(1)[::-1], m.group(2)[::-1], m.group(3)[::-1]
    return f" {day}/{month}/{year}" if 1800 <= int(year) <= 2100 else m.group()


_ARTICLE_REF = re.compile(r"((?:المادة|المادتين|المواد|مادة|من|إلى|الى|و)\s*)(\d{2,4})")


def fix_reversed_numbers(text: str) -> str:
    """Reverse every multi-digit run, except a ``المادة N`` reference whose
    reversed form would be an impossible article number while the original
    is valid (guards against numbers that were *not* reversed)."""

    def _flip(match: re.Match[str]) -> str:
        digits = match.group()
        return digits[::-1]

    def _guarded_ref(match: re.Match[str]) -> str:
        prefix, digits = match.group(1), match.group(2)
        flipped = digits[::-1]
        if int(flipped) > MAX_ARTICLE_NUMBER >= int(digits) and prefix.strip().startswith("ال"):
            return match.group()
        return prefix + flipped

    text = text.translate(_ARABIC_INDIC)  # same reversal applies to Arabic-Indic digits
    # Dates print as "year/month/day" with every number reversed ("4691/3/21" -> 12/3/1964).
    text = _DATE.sub(lambda m: "\x00" + _flip_date(m) + "\x01", text)
    # Article-style references first (with the guard), then remaining runs.
    marked = _ARTICLE_REF.sub(
        lambda m: m.group() if "\x00" in m.group() else "\x00" + _guarded_ref(m) + "\x01", text
    )
    parts = re.split(r"(\x00.*?\x01)", marked)
    out: list[str] = []
    for part in parts:
        if part.startswith("\x00"):
            out.append(part[1:-1])
        else:
            out.append(_DIGITS.sub(_flip, part))
    return "".join(out)


_AQAR = re.compile(r"\bالعاقر(?=\b|ين|ان)")


def _fix_aqar(text: str) -> str:
    """The PDF font maps "العقار" (the property) to "العاقر" (the barren) in the easement
    chapter (Articles 1021-1065; found by audit). "العاقر" has no legal use in the Code, and
    the English text of those articles says "estate/property"."""
    return _AQAR.sub("العقار", text)


def repair_arabic_text(text: str, *, fix_numbers: bool = True) -> str:
    """Apply all PDF-artifact repairs to Arabic article text."""
    text = fix_lam_alef(text)
    text = _fix_aqar(text)
    if fix_numbers:
        text = fix_reversed_numbers(text)
    # the next article's paragraph marker "(" is printed at the end of this one
    return re.sub(r"\s*\(\s*$", "", text)
