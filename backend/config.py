"""
Runtime configuration, read once from environment variables.

See README.md ("Environment variables") for the full list.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _env_list(name: str) -> list[str]:
    raw = os.getenv(name, "")
    return [item.strip().rstrip("/") for item in raw.split(",") if item.strip()]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class Settings:
    def __init__(self) -> None:
        self.env = os.getenv("APP_ENV", "development").strip().lower()
        self.is_production = self.env == "production"

        # Storage: everything lives under DATA_DIR (mount a volume here)
        self.data_dir = str(Path(os.getenv("DATA_DIR", BASE_DIR / "data")).expanduser().resolve())
        self.upload_dir = os.path.join(self.data_dir, "uploads")
        self.output_dir = os.path.join(self.data_dir, "outputs")
        self.db_path = os.path.join(self.data_dir, "history.db")

        # Limits & privacy
        self.max_upload_mb = _env_float("MAX_UPLOAD_MB", 10)
        self.max_upload_bytes = int(self.max_upload_mb * 1024 * 1024)
        self.retention_hours = _env_float("RETENTION_HOURS", 24)
        self.cleanup_interval_minutes = max(_env_float("CLEANUP_INTERVAL_MINUTES", 15), 1)

        # CORS: explicit origins; localhost dev origins are added outside production
        origins = _env_list("ALLOWED_ORIGINS")
        if not self.is_production:
            origins += [o for o in _DEV_ORIGINS if o not in origins]
        self.allowed_origins = origins
        self.allowed_origin_regex = os.getenv("ALLOWED_ORIGIN_REGEX") or None

        # Server
        self.port = int(os.getenv("PORT", "8000"))

    def ensure_dirs(self) -> None:
        for path in (self.data_dir, self.upload_dir, self.output_dir):
            os.makedirs(path, exist_ok=True)


settings = Settings()
