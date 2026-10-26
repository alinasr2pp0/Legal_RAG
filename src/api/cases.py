"""Case workspace endpoints: create a case, upload text documents, list/delete them.

Upload is a raw body (not multipart) with the file name in ``X-Filename``
(URL-encoded), so no extra dependency is needed.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.case_store import Case, CaseError, case_store
from core.config import settings
from rag.ingestion.case_extract import (
    SUPPORTED_EXT,
    ExtractionError,
    extract,
)

router = APIRouter(prefix="/cases", tags=["cases"])


class CaseCreate(BaseModel):
    name: str = Field(default="", max_length=80)


def _require_enabled() -> None:
    if not settings.case_upload_enabled:
        raise HTTPException(status_code=404, detail="ميزة مستندات القضية معطّلة")


def _view(case: Case) -> dict[str, Any]:
    return {
        "id": case.case_id,
        "name": case.name,
        "docs": [
            {
                "id": d.doc_id, "filename": d.filename, "chars": d.chars, "pages": d.pages,
                "skipped": d.skipped_injection,
            }
            for d in case.docs.values()
        ],
    }


@router.get("/capabilities")
def capabilities() -> dict[str, Any]:
    return {
        "enabled": settings.case_upload_enabled,
        "extensions": sorted(SUPPORTED_EXT),
        "max_file_mb": settings.case_max_file_mb,
        "max_docs": settings.case_max_docs,
        "ttl_hours": settings.case_ttl_hours,
    }


@router.post("", status_code=201)
def create_case(body: CaseCreate) -> dict[str, Any]:
    _require_enabled()
    return _view(case_store.create(body.name))


@router.get("/{case_id}")
def get_case(case_id: str) -> dict[str, Any]:
    _require_enabled()
    try:
        return _view(case_store.get(case_id))
    except CaseError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc


@router.post("/{case_id}/documents", status_code=201)
async def upload_document(case_id: str, request: Request) -> dict[str, Any]:
    _require_enabled()
    filename = unquote(request.headers.get("x-filename", "")).strip().replace("\\", "/")
    filename = filename.rsplit("/", 1)[-1]
    if not filename:
        raise HTTPException(status_code=422, detail="اسم الملف مطلوب (X-Filename)")
    limit = settings.case_max_file_mb * 1024 * 1024
    too_big = HTTPException(
        status_code=413, detail=f"الحد الأقصى للملف {settings.case_max_file_mb}MB"
    )
    declared = int(request.headers.get("content-length") or 0)
    if declared > limit:
        raise too_big
    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data) > limit:
            raise too_big
    from starlette.concurrency import run_in_threadpool

    try:
        case_store.get(case_id)
        extracted = await run_in_threadpool(extract, filename, bytes(data))
        doc = case_store.add_document(case_id, filename, extracted)
    except (CaseError, ExtractionError) as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return {
        "id": doc.doc_id, "filename": doc.filename, "chars": doc.chars, "pages": doc.pages,
        "skipped": doc.skipped_injection,
    }


@router.delete("/{case_id}/documents/{doc_id}", status_code=204)
def delete_document(case_id: str, doc_id: str) -> Response:
    try:
        case_store.remove_document(case_id, doc_id)
    except CaseError as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from exc
    return Response(status_code=204)




@router.delete("/{case_id}", status_code=204)
def delete_case(case_id: str) -> Response:
    case_store.delete(case_id)
    return Response(status_code=204)


