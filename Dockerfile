# ========================================
# AI Agent SDK - Production Dockerfile
# ========================================

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY agent/ ./agent/
COPY tools/ ./tools/
COPY rag/ ./rag/
COPY llm/ ./llm/
COPY memory/ ./memory/
COPY logging/ ./logging/
COPY config/ ./config/

# Create non-root user
RUN useradd -m -u 1000 agent && \
    chown -R agent:agent /app

USER agent

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
