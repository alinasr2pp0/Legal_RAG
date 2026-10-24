"""Context building: turn the final evidence chunks into the labelled block the LLM reads."""

from __future__ import annotations

from core.models import ScoredChunk


def label(c: ScoredChunk) -> str:
    if c.chunk.metadata.get("source") == "case":
        return f"مستند القضية: {c.chunk.metadata.get('doc')} ص{c.chunk.metadata.get('page')}"
    number = c.chunk.metadata.get("number")
    if not number:
        return "مصدر ويب (غير رسمي)"
    repealed = " - ملغاة" if c.chunk.metadata.get("is_repealed") else ""
    return f"مادة {number}{repealed}"


def build_context_block(contexts: list[ScoredChunk]) -> str:
    return "\n\n".join(f"[{label(c)}] {c.chunk.text}" for c in contexts)


def build_user_prompt(
    question: str, contexts: list[ScoredChunk], feedback: str | None = None
) -> str:
    prompt = f"النصوص المرجعية:\n{build_context_block(contexts)}\n\nالسؤال: {question}"
    if feedback:
        prompt += f"\n\nملاحظات المراجع على المسودة السابقة (صحّحها): {feedback}"
    return prompt
