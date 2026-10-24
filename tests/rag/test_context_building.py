from core.models import Chunk, ScoredChunk
from rag.context_building.builder import build_context_block, build_user_prompt, label


def _item(metadata: dict, text: str = "نص المصدر") -> ScoredChunk:
    return ScoredChunk(
        chunk=Chunk(chunk_id="t", text=text, article_ids=["article_163"], metadata=metadata),
        score=1.0,
    )


def test_label_distinguishes_repealed_article_and_web_source():
    assert label(_item({"number": 54, "is_repealed": True})) == "مادة 54 - ملغاة"
    assert label(_item({"source": "web"})) == "مصدر ويب (غير رسمي)"


def test_case_context_is_labelled_and_adds_reviewer_feedback():
    case_item = _item({"source": "case", "doc": "contract.pdf", "page": 2})
    assert "[مستند القضية: contract.pdf ص2] نص المصدر" in build_context_block([case_item])
    prompt = build_user_prompt("ما أثر العقد؟", [case_item], feedback="أضف الاستشهاد")
    assert "ملاحظات المراجع" in prompt


def test_empty_evidence_does_not_invent_context_text():
    assert build_context_block([]) == ""
