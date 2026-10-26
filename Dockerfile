# Multi-stage / secure production Dockerfile for Flock Energy Urja Meter Ops API
FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies in a clean layer
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create an unprivileged non-root user for security
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/false appuser

# Copy application source code and OpenAPI specification
COPY app/ ./app/
COPY openapi.json ./
COPY .env.example ./

# Set ownership to unprivileged user
RUN chown -R appuser:appgroup /app
USER appuser

# Expose standard application port
EXPOSE 8000

# Health check to ensure service readiness
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

# Launch production server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
