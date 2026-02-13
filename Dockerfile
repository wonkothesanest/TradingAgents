FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY tradingagents/ ./tradingagents/
COPY trading_api/ ./trading_api/
COPY cli/ ./cli/
COPY main.py ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Create directories for volumes
RUN mkdir -p /app/results /app/tradingagents/dataflows/data_cache

# Expose API port (not used by worker, but harmless)
EXPOSE 8000

# Default command (API server) - worker overrides this
CMD ["uvicorn", "trading_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
