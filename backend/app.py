"""
Bank Statement PDF → Excel Converter – FastAPI backend
======================================================

Single ASGI entrypoint: ``uvicorn app:app --host 0.0.0.0 --port $PORT``
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings  # noqa: E402
from database.db import init_db  # noqa: E402
from routes.download import router as download_router  # noqa: E402
from routes.history import router as history_router  # noqa: E402
from routes.upload import router as upload_router  # noqa: E402
from utils.storage import cleanup_expired  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("app")


async def _cleanup_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(cleanup_expired)
        except Exception:  # noqa: BLE001
            logger.exception("Retention cleanup failed")
        await asyncio.sleep(settings.cleanup_interval_minutes * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    init_db()
    cleanup_task = asyncio.create_task(_cleanup_loop())
    logger.info(
        "API ready (env=%s, retention=%sh, max upload=%sMB)",
        settings.env, settings.retention_hours, settings.max_upload_mb,
    )
    yield
    cleanup_task.cancel()
    with suppress(asyncio.CancelledError):
        await cleanup_task


app = FastAPI(
    title="Bank Statement PDF to Excel API",
    description="Extracts transactions from bank statement PDFs into Excel.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    """Reject oversized uploads before the body is read (Content-Length)."""
    if request.method == "POST" and request.url.path == "/api/upload":
        length = request.headers.get("content-length")
        # small allowance for multipart framing
        if length and length.isdigit() and int(length) > settings.max_upload_bytes + 64 * 1024:
            return JSONResponse(
                status_code=413,
                content={"detail": {"error": "File too large", "message": f"Maximum file size is {settings.max_upload_mb:g} MB."}},
            )
    return await call_next(request)


app.include_router(upload_router)
app.include_router(download_router)
app.include_router(history_router)


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "PDF to Excel Converter API",
        "max_upload_mb": settings.max_upload_mb,
        "retention_hours": settings.retention_hours,
    }


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=settings.port, reload=not settings.is_production)
