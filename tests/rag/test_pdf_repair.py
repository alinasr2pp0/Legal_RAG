from rag.ingestion.pdf_repair import (
    fix_lam_alef,
    fix_reversed_numbers,
    repair_arabic_text,
)


def test_lam_alef_initial_forms():
    assert fix_lam_alef("االلتزام اإليجار األرض االتفاق") == "الالتزام الإيجار الأرض الاتفاق"


def test_lam_alef_with_prefixes_and_lam_lam():
    assert fix_lam_alef("بااللتزام لاللتزام لألحكام") == "بالالتزام للالتزام للأحكام"
    assert fix_lam_alef("الالزمة") == "اللازمة"


def test_standalone_negation_is_restored():
    # "ال يجوز" (extracted) is "لا يجوز": the legal meaning must not be lost
    assert fix_lam_alef("ال يجوز وال يلزم فال") == "لا يجوز ولا يلزم فلا"
    assert fix_lam_alef("وإال") == "وإلا"


def test_definite_article_untouched():
    assert fix_lam_alef("الكتاب والمال والعقد") == "الكتاب والمال والعقد"


def test_reversed_numbers():
    assert fix_reversed_numbers("المواد من 45 إلى 08 سنة 3881") == "المواد من 54 إلى 80 سنة 1883"
    assert fix_reversed_numbers("وفقا للمادة 362.") == "وفقا للمادة 263."


def test_single_digits_untouched():
    assert fix_reversed_numbers("(2 ( الفقرة 3") == "(2 ( الفقرة 3"


def test_article_reference_guard_keeps_valid_unreversed():
    # reversed would be 9111 (> 1149) while 1119 is valid -> keep
    assert fix_reversed_numbers("في المادة 1119 ،") == "في المادة 1119 ،"


def test_repair_pipeline_example():
    text = "ال يجوز التنازل عن االلتزام وفقا للمادة 362"
    assert repair_arabic_text(text) == "لا يجوز التنازل عن الالتزام وفقا للمادة 263"


def test_midword_swapped_ligatures_and_dictionary():
    assert fix_lam_alef("الحاالت وعدم اإلخالل") == "الحالات وعدم الإخلال"
    assert fix_lam_alef("بانقضاء ثالث سنوات") == "بانقضاء ثلاث سنوات"
    # "the third" keeps its article form and is untouched
    assert fix_lam_alef("الفصل الثالث") == "الفصل الثالث"
