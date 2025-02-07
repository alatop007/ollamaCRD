# Stage 1: Builder
FROM python:3.9-slim AS builder

# Set working directory
WORKDIR /app

# Install build dependencies and clean up in the same layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage Docker cache
COPY requirements.txt .

# Install dependencies into a virtual environment
RUN python -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY controller.py .

# Stage 2: Final Image
FROM python:3.9-slim

# Create non-root user for security
RUN useradd -m -u 1000 appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
WORKDIR /app
COPY --from=builder /app/controller.py .

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER appuser

# Set entrypoint
ENTRYPOINT ["/opt/venv/bin/python", "-m", "kopf", "run", "--standalone"]
CMD ["controller.py"]
