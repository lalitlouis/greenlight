# GREENLIGHT web app on Cloud Run. Replay works with zero credentials; live runs
# use the env vars supplied at deploy time. Scales to zero — idle costs nothing.
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
# Base-image pip is too old to parse newest wheel metadata (aiohttp resolution
# failed with "versions: none") — upgrade before resolving.
RUN pip install --no-cache-dir --upgrade pip "setuptools>=83.0.0" wheel && pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY web ./web
COPY schemas ./schemas
COPY fixtures ./fixtures
COPY runs ./runs

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

# Run as a non-root user; the app writes only under /app/runs/uploads.
RUN useradd --create-home appuser && chown -R appuser /app/runs
USER appuser

# Cloud Run injects PORT. Single worker: SSE broadcast state is in-process.
CMD exec uvicorn greenlight.server:app --host 0.0.0.0 --port ${PORT:-8080}
