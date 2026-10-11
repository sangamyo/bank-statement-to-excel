# Backend image for Railway (or any container host)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production \
    DATA_DIR=/data \
    PORT=8000

WORKDIR /app

# Set INSTALL_EXTRAS=true to include the optional camelot/opencv fallback.
ARG INSTALL_EXTRAS=false
COPY requirements.txt requirements-extra.txt ./
RUN if [ "$INSTALL_EXTRAS" = "true" ]; then \
        pip install -r requirements-extra.txt; \
    else \
        pip install -r requirements.txt; \
    fi

COPY . .

RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data
USER appuser

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
