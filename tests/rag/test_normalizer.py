from rag.ingestion.normalizer import ArabicNormalizer


def test_light_normalization_strips_tashkeel():
    normalizer = ArabicNormalizer()
    text = "الْمَادَّةُ"
    result = normalizer.light(text)
    assert "ّ" not in result
    assert "َ" not in result


def test_light_normalization_converts_digits():
    normalizer = ArabicNormalizer()
    assert normalizer.light("١٦٣") == "163"


def test_aggressive_unifies_alef_variants():
    normalizer = ArabicNormalizer()
    result = normalizer.aggressive("إذا أراد آدم")
    assert "إ" not in result
    assert "أ" not in result
    assert "آ" not in result
