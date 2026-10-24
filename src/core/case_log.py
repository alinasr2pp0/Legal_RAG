'''Module for keeping an in‑memory log of answers generated for each case.

The log is intentionally simple – it lives only for the lifetime of the
process (like the existing ``case_store``) and is cleared when the server
restarts. Each entry records the question, the generated answer and a
timestamp so that the UI can display a history of interactions.
'''  # noqa: D205

import time
from collections import defaultdict
from typing import List, Tuple

from .models import AskResponse, AskRequest

# Mapping case_id -> list of (timestamp, AskResponse)
_case_answer_log: defaultdict[str, List[Tuple[float, AskResponse]]] = defaultdict(list)


def log_case_answer(case_id: str, response: AskResponse) -> None:
    """Add an answer to the per‑case log.

    ``case_id`` must be a non‑empty string. The function appends a tuple of
    ``(time.time(), response)`` to the list for that case.
    """
    _case_answer_log[case_id].append((time.time(), response))


def get_case_answers(case_id: str) -> List[dict]:
    """Return the logged answers for *case_id* as a list of dictionaries.

    Each dict contains ``timestamp`` (float seconds since epoch) and the
    fields of :class:`AskResponse` (converted via ``model_dump``). The list is
    ordered chronologically (oldest first).
    """
    return [
        {"timestamp": ts, **resp.model_dump()}
        for ts, resp in _case_answer_log.get(case_id, [])
    ]
