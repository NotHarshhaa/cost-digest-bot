FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY bot/ ./bot/
COPY .env.example .env

# Create data directory for SQLite database
RUN mkdir -p data

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["python", "bot/digest.py"]

# Health check
HEALTHCHECK --interval=1h --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import bot; print('OK')" || exit 1
