import sys
from pathlib import Path
import importlib

# Ensure the project's src directory is on the import path.
_src_dir = Path(__file__).resolve().parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

# Import the actual core package from src.core and expose its contents.
_core_pkg = importlib.import_module("src.core")
# Make this shim behave like the real package.
__path__ = _core_pkg.__path__  # type: ignore
globals().update(_core_pkg.__dict__)
