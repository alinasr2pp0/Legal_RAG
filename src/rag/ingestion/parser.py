"""Extract structured Article objects from the Egyptian Civil Code PDF.

REAL-DATA NOTES (found by testing against the actual uploaded PDF):
- Bilingual edition. Every article block starts with an Arabic marker
  "مادة N" whose Arabic-Indic digits are extracted REVERSED ("٠٢١" is 120),
  followed (before or after the Arabic text, depending on the page) by the
  English heading "Article N", the Arabic text and the English translation.
- v2 segments the document by the monotone chain of Arabic markers (1,2,3...;
  jumps are only allowed across announced repealed ranges or tiny gaps), so an
  English heading that is mis-ordered/typo'd ("Article1022") can no longer
  drop or mis-assign an article. v1 anchored on the English heading only and
  missed articles 120, 888, 1022, 1110, 1115 and left 13 Arabic texts empty.
- An article whose marker is missing is recovered from the extra
  Arabic/English run pair inside the previous article's segment.
- Repealed ranges are announced in-text, e.g. "Article 54 \n* Articles
  54-80 have been repealed by Presidential Decree." or "المواد من ٩٨٣ إلى
  ٧١٤ ملغاة / Articles 389-417 repealed". These ranges must be flagged
  (is_repealed=True), never silently dropped, per the handbook spec.
- Book/Chapter headers appear bilingually, e.g. "الباب السادس" / "Chapter
  VI", "الكتاب الثاني" / "BOOK II" — tracked sequentially while scanning.

This is a pragmatic heuristic for this specific bilingual layout, not a
general-purpose Arabic legal PDF parser -- re-validate against any PDF
with a different layout before trusting article counts blindly.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

import fitz  # PyMuPDF

from core.models import Article

# Arabic marker "مادة N" (digits reversed by RTL extraction). The lookbehind
# skips in-text cross references such as "للمادة 263" ("المادة").
# The PDF font sometimes splits the word or its number ("ما دة ٢٥٦", "م ادة ١٠٦", "مادة ٠٦ ١"),
# which made 15 articles lose their marker; tolerate single gaps (the monotone chain below
# rejects any false positive).
_MARKER_RE = re.compile(
    r"(?<!ال)(?<!لل)(?<!\w)م\s*ا\s*د\s*ة\s*[\(\s]*([٠-٩]+(?:[ \t]+[٠-٩]+)?)"
)
_CODE_START_RE = re.compile(r"باب\s+تمهيدي")
_ANCHOR_LINE_RE = re.compile(r"^\s*Article\s*\d+\s*$")
_HEADING_LINE_RE = re.compile(r"^(?:الكتاب|الباب|الفصل|الفرع|القسم)\s")
_REPEAL_LINE_RE = re.compile(r"ألغي|ملغ")
_SUBTITLE_RE = re.compile(r"^(?:\d+|[٠-٩]+)\s*[-–]")
_CHAPTER_IN_LINE_RE = re.compile(r"الفصل\s.+")
_TRAILING_HEADING_RE = re.compile(
    r"(?:(?<=[.)])\s+|\s{2,})((?:الكتاب|الباب|الفصل|الفرع|القسم)\s.{0,110})$"
)
_TRAILING_SUBTITLE_RE = re.compile(r"\s(?:\d+|[٠-٩]+)\s*[-–]\s*\S[^.]{0,60}$")
_AR_TO_LATIN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
_MAX_MARKER_GAP = 2  # tolerated unmarked articles between two markers

# Repealed-range announcements, e.g. "Articles 54-80 have been repealed",
# "Articles 389-417 repealed".
_REPEALED_RANGE_RE = re.compile(
    r"Articles?\s+(\d+)\s*[-–]\s*(\d+)\s*(?:have been\s+)?repealed", re.IGNORECASE
)

# Bilingual hierarchy headers (Book / Chapter / Part).
_BOOK_RE = re.compile(r"^\s*BOOK\s+(.+)$", re.IGNORECASE)
_CHAPTER_RE = re.compile(r"^\s*Chapter\s+(.+)$", re.IGNORECASE)
_ARABIC_BOOK_RE = re.compile(r"^\s*الكتاب\s+(.+)$")
_ARABIC_PART_RE = re.compile(r"^\s*الباب\s+(.+)$")
_ARABIC_CHAPTER_RE = re.compile(r"^\s*الفصل\s+(.+)$")

# Matches runs of Arabic-script characters (letters, presentation forms,
# Arabic-Indic digits) plus the spacing/punctuation between them.
_ARABIC_RUN_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF"
    r"\s\d.,:;()\-]+"
)


def _is_arabic_line(line: str) -> bool:
    arabic_chars = sum(1 for ch in line if "\u0600" <= ch <= "\u06FF")
    return arabic_chars > 0 and arabic_chars >= len(line) * 0.3


def _is_latin_line(line: str) -> bool:
    latin_chars = sum(1 for ch in line if ch.isascii() and ch.isalpha())
    return latin_chars >= max(3, len(line) * 0.3)


class BasePdfParser(ABC):
    """Interface so the parser backend (PyMuPDF, pdfplumber, etc.) is swappable."""

    @abstractmethod
    def parse(self, pdf_path: str | Path) -> list[Article]: ...


def _line_class(line: str) -> str:
    if _is_arabic_line(line):
        return "A"
    if _is_latin_line(line):
        return "L"
    return "N"  # neutral: "( 1 (" etc.


def _split_runs(segment: str) -> list[tuple[str, str]]:
    """Split one marker segment into ordered (class, text) runs. Lines inside a
    run are joined with "\\n" (heading detection needs them). An "Article N"
    heading line ends the current run, so two consecutive English translations
    (an article whose Arabic text is missing) stay separate runs."""
    raw_lines = [ln.strip() for ln in segment.splitlines() if ln.strip()]
    lines: list[str | None] = [None if _ANCHOR_LINE_RE.match(ln) else ln for ln in raw_lines]
    classes: list[str] = [_line_class(ln) if ln is not None else "B" for ln in lines]
    # resolve neutral lines from the next non-neutral line, else treat as Arabic
    for i in range(len(classes) - 1, -1, -1):
        if classes[i] == "N":
            nxt = next((c for c in classes[i + 1 :] if c not in ("N", "B")), None)
            classes[i] = nxt or "A"
    runs: list[tuple[str, str]] = []
    broken = False
    for ln, cls in zip(lines, classes, strict=True):
        if ln is None:
            broken = True
            continue
        if runs and runs[-1][0] == cls and not broken:
            runs[-1] = (cls, runs[-1][1] + "\n" + ln)
        else:
            runs.append((cls, ln))
        broken = False
    return runs


_EN_HEAD_RE = re.compile(r"^\s*A?\s*rticle\s*\d+\s*", re.IGNORECASE)


def _clean_english(text: str) -> str:
    text = " ".join(text.split())
    return _EN_HEAD_RE.sub("", text).strip()


class CivilCodePdfParser(BasePdfParser):
    """PyMuPDF-based parser for this bilingual edition of the Egyptian Civil
    Code. See module docstring for the segmentation strategy."""

    def parse(self, pdf_path: str | Path) -> list[Article]:
        pdf_path = Path(pdf_path)
        doc = fitz.open(pdf_path)
        pages = [doc[i].get_text("text") for i in range(len(doc))]
        doc.close()
        return self.parse_text(pages, source_file=pdf_path.name)

    # -- text-level core (unit-testable without a PDF) -------------------
    def parse_text(self, pages: list[str], source_file: str = "civil_code.pdf") -> list[Article]:
        page_starts: list[int] = []
        offset = 0
        for page_text in pages:
            page_starts.append(offset)
            offset += len(page_text) + 1
        full_text = "\n".join(pages)

        repealed_numbers: set[int] = set()
        repeal_ranges: list[tuple[int, int, str]] = []
        for m in _REPEALED_RANGE_RE.finditer(full_text):
            lo, hi = int(m.group(1)), int(m.group(2))
            repealed_numbers.update(range(lo, hi + 1))
            repeal_ranges.append((lo, hi, " ".join(m.group(0).split())))

        markers = self._marker_chain(full_text, repealed_numbers)
        hierarchy_lookup = self._hierarchy(full_text)

        extracted: dict[int, dict[str, object]] = {}
        announcements: dict[int, list[str]] = {}
        current_chapter: str | None = None

        for idx, (start, end, number) in enumerate(markers):
            seg_end = markers[idx + 1][0] if idx + 1 < len(markers) else len(full_text)
            segment = full_text[end:seg_end]
            runs = _split_runs(segment)

            # drop repeal announcements (kept for the repealed article itself)
            ann: list[str] = []
            cleaned: list[tuple[str, str]] = []
            for cls, text in runs:
                if cls == "A" and _REPEAL_LINE_RE.search(text) and len(text) < 400:
                    ann.append(" ".join(text.split()))
                else:
                    cleaned.append((cls, text))
            runs = cleaned
            if ann:
                target = next(
                    (lo for lo, hi, _ in repeal_ranges if lo == number + 1 or hi == number - 1),
                    None,
                )
                announcements.setdefault(target if target else number, []).extend(ann)

            nxt_number = markers[idx + 1][2] if idx + 1 < len(markers) else number + 1
            unmarked = [
                n for n in range(number + 1, nxt_number) if n not in repealed_numbers
            ]
            pairs = self._pairs(runs)
            # first pair -> this article; further pairs -> unmarked successors
            group_numbers = [number, *unmarked]
            for j, n in enumerate(group_numbers):
                if j < len(pairs):
                    arabic, english = pairs[j]
                else:
                    arabic, english = "", ""
                if j == len(group_numbers) - 1 and len(pairs) > len(group_numbers):
                    # leftovers belong to the last article of the group
                    extra = pairs[len(group_numbers) :]
                    arabic = "\n".join([arabic, *[a for a, _ in extra]]).strip()
                    english = " ".join([english, *[e for _, e in extra]]).strip()
                arabic, chapter_heading, trailing_chapter = self._strip_headings(arabic)
                english = _clean_english(english)
                if chapter_heading:
                    current_chapter = chapter_heading
                extracted[n] = {
                    "arabic": arabic,
                    "english": english,
                    "pos": start,
                    "chapter": current_chapter,
                }
                # headings printed at the END of a block introduce the NEXT article
                if trailing_chapter:
                    current_chapter = trailing_chapter

        articles: list[Article] = []
        for n, info in sorted(extracted.items()):
            pos = int(info["pos"])  # type: ignore[call-overload]
            book, part = hierarchy_lookup(pos)
            page = 1
            for i, ps in enumerate(page_starts):
                if pos >= ps:
                    page = i + 1
            arabic_txt = str(info["arabic"])
            english_txt = str(info["english"])
            # a Latin word stranded at the end of the Arabic run ("... so." / "Wound Up") is
            # the tail of the English text that the PDF split across a line/page break
            stray = re.search(r"\s+([A-Za-z][A-Za-z .,;:'-]*)$", arabic_txt)
            if stray and english_txt.strip():
                english_txt = english_txt.rstrip() + " " + stray.group(1).strip()
                arabic_txt = arabic_txt[: stray.start()].rstrip()
            articles.append(
                Article(
                    article_id=f"article_{n}",
                    number=n,
                    text=arabic_txt,
                    text_en=english_txt or None,
                    book=book,
                    part=part,
                    chapter=info["chapter"],
                    is_repealed=n in repealed_numbers,
                    page_number=page,
                    source_file=source_file,
                )
            )

        # Repealed numbers: flag, never drop. Text = the official announcement
        # when the PDF has one next to the range, else a clear placeholder.
        have = {a.number for a in articles}
        for lo, hi, english_note in repeal_ranges:
            note_ar = " ".join(announcements.get(lo, [])).strip()
            for n in range(lo, hi + 1):
                if n in have:
                    continue
                text = note_ar if (n == lo and note_ar) else (
                    f"[ملغاة] المادة {n} ملغاة (ضمن المواد من {lo} إلى {hi})."
                )
                articles.append(
                    Article(
                        article_id=f"article_{n}",
                        number=n,
                        text=text,
                        text_en=f"[Repealed] {english_note}",
                        is_repealed=True,
                        source_file=source_file,
                    )
                )
        articles.sort(key=lambda a: a.number)
        return articles

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _marker_chain(full_text: str, repealed: set[int]) -> list[tuple[int, int, int]]:
        """Monotone chain of Arabic article markers (start, end, number)."""
        code_start = _CODE_START_RE.search(full_text)
        floor = code_start.start() if code_start else 0
        chain: list[tuple[int, int, int]] = []
        expected = 1
        for m in _MARKER_RE.finditer(full_text):
            if m.start() < floor:
                continue
            # each digit run is reversed on its own ("٠٦ ١" -> "60" + "1" = 601)
            value = int("".join(t.translate(_AR_TO_LATIN)[::-1] for t in m.group(1).split()))
            if value < expected:
                continue
            gap = range(expected, value)
            if value == expected or len(gap) <= _MAX_MARKER_GAP or all(k in repealed for k in gap):
                chain.append((m.start(), m.end(), value))
                expected = value + 1
        return chain

    @staticmethod
    def _pairs(runs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Group runs into (arabic, english) pairs: A [L] A [L] ..."""
        pairs: list[tuple[str, str]] = []
        for cls, text in runs:
            if cls == "A":
                if pairs and not pairs[-1][1] and not pairs[-1][0]:
                    pairs[-1] = (text, "")
                elif pairs and not pairs[-1][1]:
                    pairs[-1] = (pairs[-1][0] + "\n" + text, "")  # same article, split Arabic
                else:
                    pairs.append((text, ""))
            elif pairs and not pairs[-1][1]:
                pairs[-1] = (pairs[-1][0], text)
            else:
                # English with no Arabic before it: an article whose Arabic text is
                # absent from the source PDF (e.g. 1022) -> its own pair
                pairs.append(("", text))
        return CivilCodePdfParser._merge_page_continuations([p for p in pairs if p[0] or p[1]])

    @staticmethod
    def _merge_page_continuations(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """An article that crosses a page break yields a second (Arabic, English) pair that is
        only its continuation. Left alone it is mistaken for the NEXT (unmarked) article and
        shifts every following assignment (found: Article 651 lost its end and Article 652 got
        it). A new article's English always starts with a capital letter; a continuation starts
        in lower case after an unfinished sentence."""
        merged: list[tuple[str, str]] = []
        for arabic, english in pairs:
            # a page-break stray ("... to do" / "so.") can land at the end of the Arabic run
            tail = re.search(r"\s+([A-Za-z][A-Za-z .,;:'-]*)$", arabic)
            if tail and english.strip() and english.rstrip()[-1] not in ".?!;:":
                english = english.rstrip() + " " + tail.group(1).strip()
                arabic = arabic[: tail.start()]
            prev = merged[-1] if merged else None
            if (
                prev
                and prev[1].strip()
                and english.strip()[:1].islower()
                and prev[1].rstrip()[-1] not in ".?!;:"
            ):
                merged[-1] = ("\n".join(x for x in (prev[0], arabic) if x), prev[1] + " " + english)
            else:
                merged.append((arabic, english))
        return merged

    @staticmethod
    def _strip_headings(arabic: str) -> tuple[str, str | None, str | None]:
        """Remove structural heading lines ("الفصل الثالث ...", "١ - عنوان") from
        both ends of an article's Arabic text. Returns
        (clean_text, leading_chapter, trailing_chapter): headings that lead the
        block belong to this article; headings that trail it (the PDF prints the
        next chapter's title before the next marker) belong to the next one."""
        lines = [ln for ln in arabic.split("\n") if ln.strip()]
        leading: str | None = None
        trailing: str | None = None

        def is_heading(ln: str) -> bool:
            ln = ln.strip()
            if len(ln) >= 90:
                return False
            return bool(
                _HEADING_LINE_RE.match(ln) or _SUBTITLE_RE.match(ln) or " الفصل " in f" {ln} "
            )

        while len(lines) > 1 and _HEADING_LINE_RE.match(lines[0]) and len(lines[0]) < 90:
            head = lines.pop(0).strip()
            if head.startswith("الفصل"):
                leading = head
        pops = 0
        while len(lines) > 1 and pops < 3 and is_heading(lines[-1]):
            head = lines.pop().strip()
            pops += 1
            m = _CHAPTER_IN_LINE_RE.search(head)
            if m:
                trailing = m.group(0).strip()
        text = " ".join(ln.strip() for ln in lines)
        # The PDF often glues the next chapter's title to the last text line.
        m = _TRAILING_HEADING_RE.search(text)
        if m and len(text) - len(m.group(1)) > 20:
            head = m.group(1).strip().rstrip("( ")
            text = text[: m.start()].rstrip()
            if head.startswith("الفصل"):
                trailing = re.split(r"\s+(?:\d+|[٠-٩]+)\s*[-–]", head)[0].strip()
            text = _TRAILING_SUBTITLE_RE.sub("", text).rstrip()
        return text, leading, trailing

    @staticmethod
    def _hierarchy(full_text: str):  # type: ignore[no-untyped-def]
        hierarchy_at: list[tuple[int, str | None, str | None]] = []
        current_book: str | None = None
        current_part: str | None = None
        pos = 0
        for line in full_text.splitlines():
            line_stripped = line.strip()
            if bm := (_BOOK_RE.match(line_stripped) or _ARABIC_BOOK_RE.match(line_stripped)):
                current_book = bm.group(1).strip()
            elif pm := (
                _CHAPTER_RE.match(line_stripped)
                or _ARABIC_PART_RE.match(line_stripped)
                or _ARABIC_CHAPTER_RE.match(line_stripped)
            ):
                current_part = pm.group(1).strip()
            hierarchy_at.append((pos, current_book, current_part))
            pos += len(line) + 1

        def lookup(char_offset: int) -> tuple[str | None, str | None]:
            book, part = None, None
            for offset_at, b, p in hierarchy_at:
                if offset_at > char_offset:
                    break
                book, part = b, p
            return book, part

        return lookup
