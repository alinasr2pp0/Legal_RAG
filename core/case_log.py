# Shim module to expose the real case_log implementation from src.core
# This allows imports like `from core.case_log import get_case_answers` to work
# without modifying all existing code.

from src.core.case_log import *  # noqa: F403,F401
