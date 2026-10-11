"""
History & Dashboard routes, scoped to the caller's X-Client-Id.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from database.db import delete_history, get_all_history, get_history_by_id, get_stats
from utils.storage import client_id, remove_record_files

router = APIRouter(prefix="/api", tags=["History"])


def _format_record(record: dict) -> dict:
    result = {
        "id": record["id"],
        "fileName": record["file_name"],
        "date": datetime.fromisoformat(record["created_at"]).strftime("%b %d, %Y"),
        "status": record["status"],
        "fileSize": record["file_size"],
    }
    if record["status"] == "success":
        result["downloadUrl"] = f"/api/download/{record['id']}"
    if record["status"] == "failed" and record.get("error_message"):
        result["error"] = record["error_message"]
    return result


@router.get("/history")
async def list_history(owner: Optional[str] = Depends(client_id)):
    return JSONResponse(status_code=200, content=[_format_record(r) for r in get_all_history(owner)])


@router.get("/history/{file_id}")
async def get_single_history(file_id: str, owner: Optional[str] = Depends(client_id)):
    record = get_history_by_id(file_id, owner)
    if not record:
        raise HTTPException(status_code=404, detail={"error": "Not found", "message": f"No conversion found with ID: {file_id}"})
    return JSONResponse(status_code=200, content=_format_record(record))


@router.delete("/history/{file_id}")
async def remove_history(file_id: str, owner: Optional[str] = Depends(client_id)):
    record = delete_history(file_id, owner)
    if not record:
        raise HTTPException(status_code=404, detail={"error": "Not found", "message": f"No conversion found with ID: {file_id}"})
    remove_record_files(record)
    return JSONResponse(status_code=200, content={"message": "Record deleted successfully."})


@router.get("/stats")
async def dashboard_stats(owner: Optional[str] = Depends(client_id)):
    return JSONResponse(status_code=200, content=get_stats(owner))
