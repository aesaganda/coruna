# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

LABEL maintainer="bhideki" \
      description="iOS Orchestrator (Coruna CVE-2024-23222) - Web Server & C2 Console"

# Python runtime settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install libcap2-bin to allow non-root binding to privileged ports (<1024)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libcap2-bin && \
    rm -rf /var/lib/apt/lists/* && \
    setcap 'cap_net_bind_service=+ep' /usr/local/bin/python3.11

# Create non-root application user
RUN groupadd -g 10001 coruna && \
    useradd -u 10001 -g coruna -s /bin/bash -m coruna

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . /app

# Set ownership and permissions
RUN chown -R coruna:coruna /app && \
    chmod +x /app/docker-entrypoint.sh

USER coruna

# Default exposed ports: Web Exploit Server (80) & C2 Listener (8080)
EXPOSE 80 8080

# Healthcheck verifying HTTP exploit server readiness
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import os, urllib.request; port = os.environ.get('WEB_SERVER_PORT', '80'); urllib.request.urlopen(f'http://127.0.0.1:{port}/coruna/group.html')" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python3", "main.py"]
