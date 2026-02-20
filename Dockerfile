FROM python:3.12-slim

# Install system dependencies for trimesh rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application code
COPY app/ app/

# Create data directories
RUN mkdir -p /data/thumbnails

# Volume mount points
VOLUME ["/data", "/models"]

# Environment defaults
ENV YASTL_MODEL_LIBRARY_DB=/data/library.db
ENV YASTL_MODEL_LIBRARY_SCAN_PATH=/models
ENV YASTL_MODEL_LIBRARY_THUMBNAIL_PATH=/data/thumbnails

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
