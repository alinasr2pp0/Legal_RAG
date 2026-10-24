from unittest.mock import MagicMock

from agents.orchestrator import NO_EVIDENCE_ANSWER, Orchestrator
from agents.retriever import Evidence, RetrieverAgent
from agents.writer import WriterAgent, cited_articles
from core.models import Chunk, Citation, RagAnswer, ScoredChunk
from rag.query_processing.query_analysis import analyze_query
from rag.validation.critic import CriticAgent
from tools.search_documents import SearchResult

TEXT = "كل خطأ سبب ضررا للغير يلزم من ارتكبه بالتعويض"


def _chunk(number: int = 163, text: str = TEXT) -> ScoredChunk:
    return ScoredChunk(
        chunk=Chunk(chunk_id=f"article_{number}_p0", text=text,
                    article_ids=[f"article_{number}"], metadata={"number": number}),
        score=1.0,
    )


def _evidence(chunks: list[ScoredChunk], q: str = "ما حكم الخطأ؟") -> Evidence:
    return Evidence(analysis=analyze_query(q), chunks=chunks)


def _llm(*answers: str) -> MagicMock:
    llm = MagicMock()
    llm.generate.side_effect = [
        RagAnswer(
            question="q", answer=a, contexts=[TEXT],
            citations=[Citation(article_id="article_163", article_number=163, snippet="x"),
                       Citation(article_id="article_164", article_number=164, snippet="y")],
        )
        for a in answers
    ]
    return llm


def _orchestrator(llm: MagicMock, chunks: list[ScoredChunk], max_rev: int = 1) -> Orchestrator:
    search = MagicMock(return_value=SearchResult(
        analysis=analyze_query("ما حكم الخطأ؟"), chunks=chunks, candidates=len(chunks)))
    return Orchestrator(RetrieverAgent(search, None), WriterAgent(llm), CriticAgent(), max_rev)


def test_cited_articles_parses_arabic_and_english():
    assert cited_articles("وفقا للمادة ١٦٣ و مادة 164 and Article 165") == [163, 164, 165]


def test_critic_accepts_grounded_cited_answer():
    from agents.writer import Draft

    ev = _evidence([_chunk()])
    v = CriticAgent().run(Draft("وفقا للمادة 163 كل خطأ سبب ضررا للغير يلزم بالتعويض", [], []), ev)
    assert v.passed and v.grounding > 0.7


def test_critic_flags_missing_and_phantom_citation_and_ungrounded():
    from agents.writer import Draft

    ev = _evidence([_chunk()])
    assert "no_citation" in CriticAgent().run(Draft("يلزم بالتعويض عن الضرر", [], []), ev).issues
    assert "phantom_citation" in CriticAgent().run(
        Draft("وفقا للمادة 999 يلزم بالتعويض", [], []), ev).issues
    assert "low_grounding" in CriticAgent().run(
        Draft("المادة 163 تنظم الشركات التجارية والأوراق المالية والبورصة والتحكيم", [], []), ev
    ).issues


def test_critic_accepts_honest_refusal():
    from agents.writer import Draft

    v = CriticAgent().run(Draft("النصوص المرفقة لا تكفي للإجابة", [], []), _evidence([_chunk()]))
    assert v.passed and v.refusal


def test_orchestrator_revises_once_then_passes():
    llm = _llm("يلزم بالتعويض", "وفقا للمادة 163 كل خطأ سبب ضررا للغير يلزم بالتعويض")
    result = _orchestrator(llm, [_chunk()]).run("ما حكم الخطأ؟")
    assert result.revisions == 1 and result.verdict.passed
    assert llm.generate.call_count == 2
    assert llm.generate.call_args.args[2]  # feedback forwarded to the writer
    assert [c.article_number for c in result.citations] == [163]  # only what was cited


def test_orchestrator_stops_after_max_revisions():
    llm = _llm("بدون استشهاد", "ما زال بدون استشهاد")
    result = _orchestrator(llm, [_chunk()], max_rev=1).run("ما حكم الخطأ؟")
    assert result.revisions == 1 and not result.verdict.passed


def test_orchestrator_no_evidence_skips_llm():
    llm = _llm()
    result = _orchestrator(llm, []).run("سؤال")
    assert result.answer == NO_EVIDENCE_ANSWER and llm.generate.call_count == 0


def test_orchestrator_redacts_pii_before_retrieval():
    llm = _llm("وفقا للمادة 163 كل خطأ سبب ضررا للغير")
    orch = _orchestrator(llm, [_chunk()])
    result = orch.run("موبايلي 01012345678 ما حكم الخطأ؟")
    assert result.pii_found == ["phone"]
    assert "01012345678" not in result.question
    sent = orch.retriever.search_tool.call_args.args[0]
    assert "01012345678" not in sent


def test_retriever_agent_web_fallback_only_when_available():
    search = MagicMock(return_value=SearchResult(
        analysis=analyze_query("سؤال"), chunks=[], candidates=0))
    web = MagicMock()
    web.available = True
    web.return_value = [_chunk(0, "نتيجة ويب")]
    ev = RetrieverAgent(search, web).run("سؤال")
    assert ev.used_web and len(ev.chunks) == 1

    web.available = False
    assert RetrieverAgent(search, web).run("سؤال").empty


def test_critic_long_answer_cannot_hide_behind_refusal_phrase():
    from agents.writer import Draft

    ev = _evidence([_chunk()])
    long_bad = "لا يوجد نص صريح. " + (
        "المادة 163 تنظم الشركات التجارية والأوراق المالية والبورصة " * 12
    )
    v = CriticAgent().run(Draft(long_bad, [], []), ev)
    assert not v.refusal and not v.passed


def test_critic_refusal_may_not_cite_phantom_article():
    from agents.writer import Draft

    draft = Draft("لا توجد معلومات كافية في المادة 999", [], [])
    v = CriticAgent().run(draft, _evidence([_chunk()]))
    assert "phantom_citation" in v.issues and not v.passed


def test_orchestrator_phantom_citation_falls_back_to_verbatim_evidence():
    orch = _orchestrator(_llm("وفقا للمادة 999 يلزم بالتعويض"), [_chunk()], max_rev=0)
    res = orch.run("ما حكم الخطأ؟")
    assert res.verdict and not res.verdict.passed
    assert "999" not in res.answer and TEXT in res.answer
    assert [c.article_number for c in res.citations] == [163]


def test_orchestrator_unverified_answer_carries_visible_caveat():
    orch = _orchestrator(_llm("يلزم بالتعويض عن الضرر دون ذكر مادة"), [_chunk()], max_rev=0)
    res = orch.run("ما حكم الخطأ؟")
    assert not res.verdict.passed and "يلزم بالتعويض" in res.answer


def test_orchestrator_missing_text_article_is_not_answered():
    from agents.orchestrator import TEXT_UNAVAILABLE_ANSWER

    c = _chunk(500, "[نص المادة غير متوفر في المصدر]")
    c.chunk.metadata["text_missing"] = True
    llm = _llm("should never be called")
    res = _orchestrator(llm, [c]).run("ما حكم الخطأ؟")
    assert res.answer == TEXT_UNAVAILABLE_ANSWER and res.verdict is None
    llm.generate.assert_not_called()


def test_orchestrator_incomplete_article_adds_caveat_when_cited():
    c = _chunk(163)
    c.chunk.metadata["text_incomplete"] = True
    llm = _llm("وفقا للمادة 163 كل خطأ سبب ضررا للغير يلزم بالتعويض")
    res = _orchestrator(llm, [c]).run("ما حكم الخطأ؟")
    assert "ناقص" in res.answer
