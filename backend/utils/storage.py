"""
Per-browser ownership and file lifecycle helpers.

* ``client_id`` – FastAPI dependency reading the X-Client-Id header (a random
  UUID the frontend keeps in localStorage). Records are scoped to it.
* ``remove_record_files`` – deletes the PDF/xlsx that belong to a record.
* ``cleanup_expired`` – removes records + files older than RETENTION_HOURS and
  sweeps orphaned files left behind by crashes.
"""

from __future__ import annotations

import os
import re
import time
from datetime import timedelta
from typing import Optional

from fastapi import Header

from config import settings
from database.db import pop_expired
from utils.logger import get_logger

logger = get_logger("storage")

_CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def client_id(x_client_id: Optional[str] = Header(default=None)) -> Optional[str]:
    """Return a validated client id, or None (anonymous bucket)."""
    if x_client_id and _CLIENT_ID_RE.match(x_client_id.strip()):
        return x_client_id.strip()
    return None


def _safe_remove(path: Optional[str]) -> None:
    """Remove a file, but only if it lives inside DATA_DIR."""
    if not path:
        return
    try:
        real = os.path.realpath(path)
        if os.path.commonpath([real, settings.data_dir]) != settings.data_dir:
            return
        if os.path.isfile(real):
            os.remove(real)
    except (OSError, ValueError):
        pass


def remove_record_files(record: dict) -> None:
    _safe_remove(record.get("original_file_path"))
    _safe_remove(record.get("converted_file_path"))


def cleanup_expired() -> int:
    """Delete records and files older than the retention period.

    Returns the number of records removed. RETENTION_HOURS <= 0 disables it.
    """
    if settings.retention_hours <= 0:
        return 0

    max_age = timedelta(hours=settings.retention_hours)
    expired = pop_expired(max_age)
    for record in expired:
        remove_record_files(record)

    # Orphan sweep (files whose record vanished, crashed jobs, ...)
    cutoff = time.time() - max_age.total_seconds()
    for folder in (settings.upload_dir, settings.output_dir):
        try:
            for name in os.listdir(folder):
                path = os.path.join(folder, name)
                if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                    _safe_remove(path)
        except FileNotFoundError:
            continue

    if expired:
        logger.info("Retention cleanup: removed %d expired conversion(s)", len(expired))
    return len(expired)
