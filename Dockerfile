FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system build dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libxml2-dev \
        libxslt1-dev \
        libffi-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy root requirements first (for Docker layer caching)
COPY requirements.txt .

# Install CPU-only PyTorch first (prevents downloading heavy 2.5GB CUDA packages)
# then install remaining requirements smoothly
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir app-store-scraper --no-deps

# Copy the rest of the application
COPY . .

# Make the engine package importable from /app
ENV PYTHONPATH=/app

# Railway sets $PORT dynamically; default to 8000 for local runs
EXPOSE 8000

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
