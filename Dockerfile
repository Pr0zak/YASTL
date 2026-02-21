# Frontend build stage
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Backend stage
FROM python:3.12-slim

# Install system dependencies for trimesh rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application code and install (with STEP file support)
COPY pyproject.toml .
COPY app/ app/
RUN pip install --no-cache-dir ".[step]"

# Copy built frontend from the frontend stage
COPY --from=frontend /app/app/static/dist ./app/static/dist

# Create data directories
RUN mkdir -p /data/thumbnails

# Volume mount points
VOLUME ["/data", "/models"]

# Environment defaults
ENV YASTL_MODEL_LIBRARY_DB=/data/library.db
ENV YASTL_MODEL_LIBRARY_THUMBNAIL_PATH=/data/thumbnails

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
