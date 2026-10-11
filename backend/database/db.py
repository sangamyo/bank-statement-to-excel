"""
SQLite database module for storing conversion history.

Every record carries an ``owner`` (the browser's X-Client-Id, or NULL for
requests without one). All read/delete helpers are scoped to an owner so one
visitor can never see or touch another visitor's conversions.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from config import settings


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    os.makedirs(os.path.dirname(settings.db_path), exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Initialize the database and create/migrate tables."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversion_history (
            id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            original_file_path TEXT,
            converted_file_path TEXT,
            file_size TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'processing',
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            owner TEXT
        )
    """)
    columns = {row["name"] for row in cursor.execute("PRAGMA table_info(conversion_history)")}
    if "owner" not in columns:
        cursor.execute("ALTER TABLE conversion_history ADD COLUMN owner TEXT")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_owner ON conversion_history(owner)")
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.utcnow().isoformat()


def insert_history(
    file_id: str,
    file_name: str,
    file_size: str,
    original_file_path: str,
    status: str = "processing",
    owner: Optional[str] = None,
) -> dict:
    """Insert a new conversion history record."""
    conn = get_connection()
    cursor = conn.cursor()
    now = _now()
    cursor.execute(
        """
        INSERT INTO conversion_history
            (id, file_name, original_file_path, file_size, status, created_at, updated_at, owner)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (file_id, file_name, original_file_path, file_size, status, now, now, owner),
    )
    conn.commit()
    record = dict(cursor.execute(
        "SELECT * FROM conversion_history WHERE id = ?", (file_id,)
    ).fetchone())
    conn.close()
    return record


def update_history(
    file_id: str,
    status: Optional[str] = None,
    converted_file_path: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Optional[dict]:
    """Update a conversion history record (internal, not owner-scoped)."""
    conn = get_connection()
    cursor = conn.cursor()

    updates = ["updated_at = ?"]
    values: list = [_now()]
    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if converted_file_path is not None:
        updates.append("converted_file_path = ?")
        values.append(converted_file_path)
    if error_message is not None:
        updates.append("error_message = ?")
        values.append(error_message)

    values.append(file_id)
    cursor.execute(f"UPDATE conversion_history SET {', '.join(updates)} WHERE id = ?", values)
    conn.commit()
    row = cursor.execute("SELECT * FROM conversion_history WHERE id = ?", (file_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_history(owner: Optional[str]) -> list[dict]:
    """All of one owner's records, most recent first."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM conversion_history WHERE owner IS ? ORDER BY created_at DESC",
        (owner,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_history_by_id(file_id: str, owner: Optional[str]) -> Optional[dict]:
    """One record, only if it belongs to ``owner``."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM conversion_history WHERE id = ? AND owner IS ?",
        (file_id, owner),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_stats(owner: Optional[str]) -> dict:
    """Conversion statistics for one owner's dashboard."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT status, created_at FROM conversion_history WHERE owner IS ?", (owner,)
    ).fetchall()
    conn.close()

    total = len(rows)
    success = sum(1 for r in rows if r["status"] == "success")
    failed = sum(1 for r in rows if r["status"] == "failed")
    processing = sum(1 for r in rows if r["status"] == "processing")
    today = datetime.utcnow().strftime("%Y-%m-%d")
    today_count = sum(1 for r in rows if str(r["created_at"]).startswith(today))
    success_rate = (success / total * 100) if total > 0 else 0

    return {
        "total_conversions": total,
        "success_count": success,
        "failed_count": failed,
        "processing_count": processing,
        "today_count": today_count,
        "success_rate": round(success_rate, 1),
    }


def delete_history(file_id: str, owner: Optional[str]) -> Optional[dict]:
    """Delete one owner's record. Returns the deleted record (for file cleanup)."""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM conversion_history WHERE id = ? AND owner IS ?",
        (file_id, owner),
    ).fetchone()
    if row:
        conn.execute("DELETE FROM conversion_history WHERE id = ?", (file_id,))
        conn.commit()
    conn.close()
    return dict(row) if row else None


def pop_expired(older_than: timedelta) -> list[dict]:
    """Delete and return every record created before now - ``older_than``."""
    cutoff = (datetime.utcnow() - older_than).isoformat()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM conversion_history WHERE created_at < ?", (cutoff,)
    ).fetchall()
    if rows:
        conn.execute("DELETE FROM conversion_history WHERE created_at < ?", (cutoff,))
        conn.commit()
    conn.close()
    return [dict(r) for r in rows]
