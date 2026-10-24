from rag.ingestion import legal_arabic_text as lat
from rag.query_processing.query_analysis import analyze_query


def test_arabic_article_reference_with_arabic_indic_digits():
    assert analyze_query("ما نص المادة ١٦٣؟").article_numbers == [163]


def test_english_article_reference():
    assert analyze_query("What does Article 148 say?").article_numbers == [148]


def test_small_range_expands_and_invalid_numbers_dropped():
    a = analyze_query("اشرح المواد من 163 إلى 165 والمادة 5000")
    assert a.article_numbers == [163, 164, 165]


def test_no_reference_in_plain_question():
    a = analyze_query("ما هي شروط صحة العقد؟")
    assert a.article_numbers == [] and a.language == "ar"
    assert "عقد" in a.bm25_tokens


def test_dialect_marker_and_mapping():
    a = analyze_query("عايز افهم الايجار")
    assert a.egyptian_dialect
    assert "يريد" in a.bm25_tokens


def test_negation_survives_bm25_tokenization():
    assert "لا" in lat.tokenize_for_bm25("لا يجوز التنازل")


def test_embedding_text_is_readable_not_stemmed():
    assert lat.prepare_for_embedding("الإِيجار") == "الايجار"
