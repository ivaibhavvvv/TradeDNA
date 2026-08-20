# ============================================================
# TradeDNA API Production Multi-Stage Dockerfile
# ============================================================

# Stage 1: Build Dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Production Minimal Runtime
FROM python:3.12-slim AS runner

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root application user
RUN groupadd -g 10001 tradedna && \
    useradd -u 10001 -g tradedna -s /bin/bash -m tradedna

# Copy installed python wheels/packages from builder
COPY --from=builder /root/.local /home/tradedna/.local
ENV PATH=/home/tradedna/.local/bin:$PATH

# Copy application source code
COPY --chown=tradedna:tradedna . .

# Set environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENVIRONMENT=production \
    PORT=8000

USER tradedna

EXPOSE 8000

# Container healthcheck against liveness endpoint
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

STOPSIGNAL SIGTERM

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--lifespan", "on"]
