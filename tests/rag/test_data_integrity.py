"""Regression tests on the committed dataset (data/serving + data/interim). They guard the
defects found in the data audit; they do NOT prove legal correctness (see MANIFEST.json and
needs_manual_review.txt for what still needs a lawyer)."""
import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVING = ROOT / "data/serving/chunks.json"
MANIFEST = ROOT / "data/serving/MANIFEST.json"
CLEAN = ROOT / "data/serving/articles_clean.json"  # committed copy: runs in CI too
PROCESSED = ROOT / "data/processed/chunks.json"

pytestmark = pytest.mark.skipif(not CLEAN.exists(), reason="dataset not generated")


@pytest.fixture(scope="module")
def articles():
    return {a["number"]: a for a in json.loads(CLEAN.read_text(encoding="utf-8"))}


@pytest.fixture(scope="module")
def chunks():
    return json.loads(SERVING.read_text(encoding="utf-8"))


def _num(c):
    m = c.get("metadata", c)
    return m.get("article_number", m.get("number"))


def test_all_articles_present_and_contiguous(articles):
    assert sorted(articles) == list(range(1, 1150))


def test_manifest_hashes_match_committed_files():
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert man["chunks_sha256"] == hashlib.sha256(SERVING.read_bytes()).hexdigest()
    assert man["articles_sha256"] == hashlib.sha256(CLEAN.read_bytes()).hexdigest()


@pytest.mark.skipif(not PROCESSED.exists(), reason="data/processed not generated (DVC output)")
def test_processed_equals_serving():
    assert PROCESSED.read_bytes() == SERVING.read_bytes()


def test_every_article_has_a_chunk_and_no_orphans(articles, chunks):
    covered = {_num(c) for c in chunks}
    assert covered == set(articles)


def test_no_marker_fragments_or_stray_latin(articles):
    marker = re.compile(r"(?<!ال)(?<!لل)(?<!\w)م\s*ا\s*د\s*ة\s*\d{1,4}")
    for n, a in articles.items():
        assert not marker.search(a["text"]), n
        assert not re.search(r"\s[A-Za-z]{2,}[.,]?$", a["text"]), n


def test_page_continuations_652_651():
    a = {x["number"]: x for x in json.loads(CLEAN.read_text(encoding="utf-8"))}
    assert a[652]["text"].strip() and not a[652]["text"].lstrip().startswith("ما دة")
    assert a[651]["text_en"] and a[652]["text_en"]


def test_article_601_marker_recovered(articles):
    assert articles[601]["text"].lstrip().startswith("(1")
    assert "موت المؤجر" in articles[601]["text"]
    assert "موت المؤجر" not in articles[600]["text"]


def test_article_54_date_not_reversed(articles):
    assert "1964" in articles[54]["text"] and "4691" not in articles[54]["text"]


def test_1021_1022_relocation_and_incomplete_flag(articles):
    assert articles[1022].get("text_incomplete") is True
    assert articles[1021].get("text_incomplete") in (False, None)
    assert "(2" in articles[1022]["text"] and "(2" not in articles[1021]["text"]


def test_incomplete_article_chunk_carries_marker(chunks):
    c = [x for x in chunks if _num(x) == 1022]
    assert c and "غير متوفرة في المصدر" in c[0]["text"]


def test_aqar_font_swap_repaired(articles):
    assert not [n for n, a in articles.items() if "العاقر" in a["text"]]
    assert "العقار المرتفق" in articles[1021]["text"]


def test_paragraph_numbers_normalised(articles):
    bad = re.compile(r"\)\s*\d{1,2}\s*\(|\(\s*\)\s*\d")
    assert not [n for n, a in articles.items() if bad.search(a["text"])]
    assert articles[45]["text"].startswith("(1) لا يكون أهلا")


def test_islamic_word_repaired(articles):
    assert "إسالم" not in " ".join(a["text"] for a in articles.values())
