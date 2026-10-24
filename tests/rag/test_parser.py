"""Parser v2 on a synthetic page that reproduces the real PDF layouts:
marker (reversed Arabic-Indic digits) / "Article N" heading before or after the
Arabic text / missing marker / repealed range / missing Arabic text."""
from rag.ingestion.parser import CivilCodePdfParser

PAGE = """مادة 99
قبل باب تمهيدي: هذا قرار الإصدار وليس مادة
باب تمهيدي
 ( مادة
١(
نص عربي للمادة الاولى يتناول الاحكام العامة .
Article 1
First article english text here.
 مادة
٢
Article 2
نص عربي للمادة الثانية يتناول القواعد .
Second article english text here.
الفصل الثاني الاشخاص
 مادة
٣
نص عربي للمادة الثالثة تتحدث عن الحقوق .
Article 3
Third article english text here.
Article 4
Fourth english with no arabic text at all.
 مادة
٥
نص عربي للمادة الخامسة تتحدث عن الالتزامات .
Article 5
Fifth article english text here.
 مادة
٦
نص عربي للمادة السادسة يتناول الواجبات .
Article 6
Sixth article english text here.
Articles 7-8 have been repealed by Presidential Decree.
 مادة
٩
نص عربي للمادة التاسعة .
Article 9
Ninth article english text here.
"""


def _parse():
    return {a.number: a for a in CivilCodePdfParser().parse_text([PAGE])}


def test_all_numbers_present_and_decree_before_code_start_ignored():
    arts = _parse()
    assert sorted(arts) == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    assert "قرار الإصدار" not in arts[1].text


def test_text_and_english_assigned_to_right_article():
    arts = _parse()
    assert "الاولى" in arts[1].text and arts[1].text_en == "First article english text here."
    assert "الثانية" in arts[2].text and "Second" in (arts[2].text_en or "")
    assert "الثالثة" in arts[3].text and "Third" in (arts[3].text_en or "")
    assert "الخامسة" in arts[5].text and "Fifth" in (arts[5].text_en or "")


def test_article_with_missing_arabic_is_kept_with_english_only():
    arts = _parse()
    assert arts[4].text == "" and "Fourth" in (arts[4].text_en or "")


def test_repealed_range_flagged_not_dropped():
    arts = _parse()
    assert arts[7].is_repealed and arts[8].is_repealed
    assert not arts[6].is_repealed and not arts[9].is_repealed
    assert "ملغاة" in arts[8].text


def test_trailing_chapter_heading_moves_to_next_article():
    arts = _parse()
    assert "الفصل الثاني" not in arts[2].text
    assert arts[3].chapter and arts[3].chapter.startswith("الفصل الثاني")
