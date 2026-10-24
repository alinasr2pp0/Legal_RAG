import sys
from pathlib import Path

# Ensure the project's src directory is on the import path for test modules that import `api`.
_src_dir = Path(__file__).resolve().parents[1] / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

# Re-export the FastAPI application and related symbols.
from src.api import main as main

__all__ = ["main"]
