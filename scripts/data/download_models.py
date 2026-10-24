"""Download every local model ONCE (needs internet), so the project can then run
fully offline (LOCAL_ONLY=true, HF_OFFLINE=true).

Usage:
    python scripts/data/download_models.py                 # the embedding model only
Ollama (the LLM) is separate:  ollama pull qwen2.5:3b
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from core.config import settings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-embedding", action="store_true")
    args = ap.parse_args()

    os.environ["HF_HOME"] = str(Path(settings.models_dir) / "hf")
    from huggingface_hub import snapshot_download

    targets: list[str] = []
    if not args.no_embedding:
        targets.append(settings.local_embedding_model)
    for repo in targets:
        print(f"Downloading {repo} -> {os.environ['HF_HOME']}")
        snapshot_download(repo_id=repo)
    print("Done. Now set HF_OFFLINE=true (LOCAL_ONLY=true implies it).")


if __name__ == "__main__":
    main()
