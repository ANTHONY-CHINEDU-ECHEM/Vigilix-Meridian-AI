# Multi stage build: interface, then the Python service that serves it.
FROM node:20-slim AS web
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 VIGILIX_DATA_DIR=/app/data
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY vigilix ./vigilix
COPY scripts ./scripts
RUN pip install --no-cache-dir -e .
COPY --from=web /app/frontend/dist ./frontend/dist
# Build data and models at image build time unless a prebuilt data volume is mounted.
ARG BUILD_DATA=1
RUN if [ "$BUILD_DATA" = "1" ]; then python scripts/download_data.py && python scripts/build_kb.py && python scripts/build_index.py && python scripts/train_models.py && python scripts/run_evaluation.py; fi
EXPOSE 8000
HEALTHCHECK CMD curl -fs http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "vigilix.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
