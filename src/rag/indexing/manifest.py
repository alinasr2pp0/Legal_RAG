"""Ties the vector index to one dataset version and one embedding model.

``build_index.py`` writes ``data/processed/index_manifest.json``; the API's readiness
check compares it with the corpus it serves and the embedder it loaded, so a stale or
mismatched index (the classic silent failure: new chunks, old vectors) is reported instead
of returning wrong passages.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

INDEX_MANIFEST = Path("data/processed/index_manifest.json")


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_id(model: str) -> str:
    """Last path segment, so ``D:\\AI-Models\\multilingual-e5-small`` and
    ``intfloat/multilingual-e5-small`` (the same weights) count as the same model."""
    return model.replace("\\", "/").rstrip("/").split("/")[-1]


def write_index_manifest(
    chunks_path: str | Path, *, embedder: str, model: str, dimension: int,
    num_chunks: int, index_name: str, path: Path = INDEX_MANIFEST,
) -> dict[str, object]:
    manifest: dict[str, object] = {
        "chunks_sha256": file_sha256(chunks_path),
        "num_chunks": num_chunks,
        "index_name": index_name,
        "embedder": embedder,
        "embedding_model": model_id(model),
        "embedding_dimension": dimension,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def index_problems(
    chunks_path: str | Path, *, model: str, dimension: int, indexed_count: int | None,
    n_chunks: int, path: Path = INDEX_MANIFEST,
) -> list[str]:
    """Reasons the index cannot be trusted for the corpus being served (empty == consistent)."""
    problems: list[str] = []
    if indexed_count is not None and indexed_count != n_chunks:
        problems.append(f"index has {indexed_count} vectors but the corpus has {n_chunks} chunks")
    if not path.exists():
        return problems  # legacy index: count check only; rebuild to get full verification
    m = json.loads(path.read_text(encoding="utf-8"))
    if m.get("chunks_sha256") != file_sha256(chunks_path):
        problems.append("index was built from a different chunk dataset (re-run build_index)")
    if m.get("embedding_model") and model_id(m["embedding_model"]) != model_id(model):
        problems.append(f"index embedded with {m['embedding_model']}, API uses {model_id(model)}")
    if m.get("embedding_dimension") and int(m["embedding_dimension"]) != dimension:
        problems.append(
            f"index dimension {m['embedding_dimension']} != embedder dimension {dimension}"
        )
    return problems
