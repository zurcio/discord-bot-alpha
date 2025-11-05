# Use a slim Python image
FROM python:3.11-slim

# Create app directory
WORKDIR /app

# Install system deps if needed (none for now)
# RUN apt-get update && apt-get install -y --no-install-recommends ... && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for better layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Ensure runtime dir exists (mounted in production)
RUN mkdir -p /app/runtime

# Environment
ENV PYTHONUNBUFFERED=1 \
    RUNTIME_DATA_DIR=/app/runtime

# Default command
CMD ["python", "bot.py"]
