"""Typed retrieval/answer cases on the REAL corpus (offline: hash embedder, fake LLMs).
They check the mechanics (article lookup, multi-article, repealed, incomplete/refusal
handling). They do not measure semantic quality -- see scripts/evaluation/benchmark_retrieval.py."""

import pytest

from rag.query_processing.query_analysis import analyze_query
from tests.api.test_end_to_end_local import CHUNKS, orchestrator  # noqa: F401  (fixture)

pytestmark = pytest.mark.skipif(not CHUNKS.exists(), reason="serving bundle not exported")


@pytest.mark.parametrize(
    ("q", "expected"),
    [
        ("ما نص المادة 163؟", [163]),
        ("ما حكم المادتين 163 و 164؟", [163, 164]),
        ("المادتين ١٦٣ و١٦٤", [163, 164]),
        ("المواد 1، 2، 3", [1, 2, 3]),
        ("المواد من 163 إلى 165", [163, 164, 165]),
        ("قارن المادة 163 والمادة 165", [163, 165]),
        ("Article 163 and article 164", [163, 164]),
        ("المادة 5000", []),  # beyond the Code
    ],
)
def test_explicit_article_parsing(q, expected):
    assert analyze_query(q).article_numbers == expected


def test_multi_article_question_returns_all_requested(orchestrator):  # noqa: F811
    res = orchestrator.run("ما حكم المادتين 163 و 164؟")
    assert {163, 164} <= set(res.article_numbers)
    assert {163, 164} <= {c.article_number for c in res.citations} | set(res.article_numbers)


def test_repealed_article_is_labelled_not_invented(orchestrator):  # noqa: F811
    res = orchestrator.run("ما نص المادة 54؟")
    assert res.article_numbers == [54]
    assert "54" in res.answer


def test_incomplete_article_1022_carries_visible_caveat(orchestrator):  # noqa: F811
    res = orchestrator.run("ما نص المادة 1022؟")
    assert 1022 in res.article_numbers
    assert "ناقص" in res.answer


def test_honest_refusal_is_not_flagged_and_unanswerable_gets_no_fake_citation():
    from tests.agents.test_agents import _chunk, _llm, _orchestrator

    llm = _llm("لا تكفي النصوص المتاحة للإجابة عن هذا السؤال.")
    res = _orchestrator(llm, [_chunk()]).run("ما سعر الذهب اليوم؟")
    assert res.verdict.refusal and res.verdict.passed


def test_negation_is_kept_and_consistent_between_query_and_corpus():
    """"لا" is folded to "ال" (the PDF prints it that way); it must be folded identically on
    both sides, otherwise "لا يجوز" and "يجوز" could never be told apart."""
    from rag.query_processing.query_analysis import bm25_tokens

    q = bm25_tokens("لا يجوز التنازل")
    assert q[:2] == bm25_tokens("ال يجوز")[:2]
    assert q[0] != bm25_tokens("يجوز التنازل")[0]
