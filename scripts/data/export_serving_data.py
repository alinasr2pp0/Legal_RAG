"""Copy the DVC-produced chunk corpus into data/serving/ and write MANIFEST.json
(sha256 of the dataset, counts, missing/incomplete articles, corrections applied) so the
serving corpus, the vector index and the PDF can be tied to one dataset version.

    dvc repro && python scripts/data/export_serving_data.py && git add data/serving
"""
import hashlib
import json
import shutil
from pathlib import Path

SRC = Path("data/processed/chunks.json")
DST = Path("data/serving/chunks.json")
ARTICLES_DST = Path("data/serving/articles_clean.json")  # committed so CI can run the data guards
MANIFEST = Path("data/serving/MANIFEST.json")
CLEAN = Path("data/interim/articles_clean.json")
REPORT = Path("data/interim/validation_report.json")
CORR = Path("data/interim/source_corrections_applied.json")
PDFS = sorted(Path("data/raw").glob("*.pdf"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(pdf: Path | None = None) -> dict:
    pdfs = [pdf] if pdf else PDFS
    chunks = json.loads(DST.read_text(encoding="utf-8"))
    articles = json.loads(ARTICLES_DST.read_text(encoding="utf-8"))
    report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    return {
        "chunks_sha256": sha256(DST),
        "articles_sha256": sha256(ARTICLES_DST),
        "source_pdf_sha256": sha256(pdfs[0]) if pdfs else None,
        "n_articles": len(articles),
        "n_chunks": len(chunks),
        "n_repealed": sum(1 for a in articles if a.get("is_repealed")),
        "text_missing_articles": [
            a["number"] for a in articles if not a["text"].strip() and not a.get("is_repealed")
        ],
        "text_incomplete_articles": [a["number"] for a in articles if a.get("text_incomplete")],
        "validation": {k: report.get(k) for k in ("total", "valid", "missing_numbers")},
        "source_corrections": json.loads(CORR.read_text(encoding="utf-8")) if CORR.exists() else None,
    }


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", type=Path, help="source PDF (default: data/raw/*.pdf)")
    args = ap.parse_args()
    DST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(SRC, DST)
    shutil.copyfile(CLEAN, ARTICLES_DST)
    MANIFEST.write_text(
        json.dumps(build_manifest(args.pdf), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{SRC} -> {DST} ({DST.stat().st_size / 1024:.0f} KiB) + {ARTICLES_DST}; manifest -> {MANIFEST}")
