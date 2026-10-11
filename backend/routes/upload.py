"""
Upload route.

Accepts a PDF, stores it as ``<DATA_DIR>/uploads/<id>.pdf``, records a
"processing" history row owned by the caller's X-Client-Id, and converts it in
a background task. The uploaded PDF is deleted as soon as conversion finishes.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from config import settings
from database.db import insert_history, update_history
from services.parser_service import process
from utils.logger import get_logger
from utils.storage import client_id

logger = get_logger("upload")

router = APIRouter(prefix="/api", tags=["Upload"])

_CHUNK = 1024 * 1024


def _format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _display_name(filename: str) -> str:
    """Strip path parts and invisible/control characters from a user filename."""
    name = os.path.basename(filename.replace("\\", "/"))
    name = "".join(c for c in name if c.isprintable() and c not in "‎‏‪‫‬‭‮﻿")
    return name.strip()[:200] or "statement.pdf"


def _background_process(file_id: str, pdf_path: str, original_filename: str) -> None:
    try:
        excel_path, df = process(pdf_path, file_id, original_filename, output_dir=settings.output_dir)
        update_history(file_id=file_id, status="success", converted_file_path=excel_path)
        logger.info("Conversion successful: %s; rows=%d", file_id, len(df))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Processing failed for %s: %s", file_id, type(exc).__name__)
        message = str(exc) if isinstance(exc, ValueError) else "The PDF could not be converted."
        update_history(file_id=file_id, status="failed", error_message=message)
    finally:
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except OSError:
            pass


@router.post("/upload")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    owner: Optional[str] = Depends(client_id),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail={"error": "Invalid file type", "message": "Only PDF files are accepted."})

    settings.ensure_dirs()
    file_id = str(uuid.uuid4())
    display_name = _display_name(file.filename)
    pdf_path = os.path.join(settings.upload_dir, f"{file_id}.pdf")

    size = 0
    first_bytes = b""
    try:
        with open(pdf_path, "wb") as out:
            while chunk := await file.read(_CHUNK):
                if not first_bytes:
                    first_bytes = chunk[:5]
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail={"error": "File too large", "message": f"Maximum file size is {settings.max_upload_mb:g} MB."},
                    )
                out.write(chunk)
        if size == 0 or not first_bytes.startswith(b"%PDF"):
            raise HTTPException(status_code=400, detail={"error": "Invalid file", "message": "The file is not a valid PDF."})
    except HTTPException:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        raise
    finally:
        await file.close()

    file_size = _format_file_size(size)
    insert_history(
        file_id=file_id,
        file_name=display_name,
        file_size=file_size,
        original_file_path=pdf_path,
        status="processing",
        owner=owner,
    )
    background_tasks.add_task(_background_process, file_id, pdf_path, display_name)

    return JSONResponse(status_code=200, content={
        "message": "File uploaded successfully. Conversion in progress.",
        "file": {
            "id": file_id,
            "fileName": display_name,
            "date": datetime.utcnow().isoformat(),
            "status": "processing",
            "fileSize": file_size,
        },
    })
