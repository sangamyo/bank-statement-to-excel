"""
Download route: serves a generated Excel file to the client that owns it.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from database.db import get_history_by_id
from utils.storage import client_id

router = APIRouter(prefix="/api", tags=["Download"])


@router.get("/download/{file_id}")
async def download_file(file_id: str, owner: Optional[str] = Depends(client_id)):
    record = get_history_by_id(file_id, owner)

    if not record:
        raise HTTPException(status_code=404, detail={"error": "Not found", "message": f"No conversion found with ID: {file_id}"})

    if record["status"] == "processing":
        raise HTTPException(status_code=202, detail={"error": "Still processing", "message": "The file is still being converted. Please try again shortly."})

    if record["status"] == "failed":
        raise HTTPException(status_code=400, detail={"error": "Conversion failed", "message": record.get("error_message") or "The conversion failed."})

    file_path = record.get("converted_file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail={"error": "File not found", "message": "The converted file is no longer available."})

    download_name = os.path.splitext(record["file_name"])[0] + ".xlsx"
    return FileResponse(
        path=file_path,
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Cache-Control": "no-store"},
    )
