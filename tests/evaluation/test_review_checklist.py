import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "make_review_checklist",
    Path(__file__).resolve().parents[2] / "scripts" / "data" / "make_review_checklist.py",
)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)

ARTICLES = [
    {"number": str(i), "is_repealed": i % 7 == 0, "text_en": "x", "page_number": i // 10 + 1}
    for i in range(1, 101)
]


def test_checklist_is_reproducible_and_skips_repealed():
    manifest = {
        "source_pdf_sha256": "abc",
        "text_missing_articles": [],
        "text_incomplete_articles": [1022],
    }
    a = mod.build(ARTICLES, manifest, seed=1, n=10)
    assert a == mod.build(ARTICLES, manifest, seed=1, n=10)
    rows = [r for r in a.splitlines() if r.startswith("| ") and "[ ]" in r]
    assert len(rows) == 10
    assert all(int(r.split("|")[1]) % 7 for r in rows)
    assert "pending human review" in a and "[x]" not in a


def test_preflight_accepts_local_model_folder(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "check_local_stack",
        Path(__file__).resolve().parents[2] / "scripts" / "ops" / "check_local_stack.py",
    )
    stack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stack)
    folder = tmp_path / "multilingual-e5-small"
    folder.mkdir()
    assert not stack._hf_cached(str(folder))  # empty folder is not a model
    (folder / "modules.json").write_text("[]")
    assert stack._hf_cached(str(folder))
