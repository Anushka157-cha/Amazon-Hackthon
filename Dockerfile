# Multi-stage Dockerfile for HomeGuard (FastAPI + MCP + Fire TV Leanback App)
# Optimized for AWS App Runner, ECS, or Container Deployment

# --- Stage 1: Build Fire TV App (React + Vite) ---
FROM node:20-alpine AS frontend-builder
WORKDIR /app/tv-app

COPY tv-app/package*.json ./
RUN npm ci

COPY tv-app/ ./
RUN npm run build

# --- Stage 2: Python Backend & MCP Runtime ---
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOMEGUARD_HOST=0.0.0.0 \
    HOMEGUARD_PORT=8000 \
    PORT=8000

WORKDIR /app

# Install build dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and static assets
COPY homeguard/ ./homeguard/
COPY static/ ./static/
COPY demo/ ./demo/
COPY pyproject.toml ./

# Copy built frontend from Stage 1
COPY --from=frontend-builder /app/tv-app/dist ./tv-app/dist

# Expose port for AWS App Runner
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/api/status || exit 1

# Start unified server
CMD ["python", "-m", "homeguard.dashboard"]
