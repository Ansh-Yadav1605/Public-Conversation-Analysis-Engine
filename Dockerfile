FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system build dependencies (needed by some Python packages)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy root requirements first (for Docker layer caching)
COPY requirements.txt .

# Upgrade pip and install all dependencies using python -m pip
# (avoids the 'pip: command not found' issue on slim images)
RUN python -m pip install --no-cache-dir --upgrade pip \
 && python -m pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Make the engine package importable from /app
ENV PYTHONPATH=/app

# Railway sets $PORT dynamically; default to 8000 for local runs
EXPOSE 8000

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
