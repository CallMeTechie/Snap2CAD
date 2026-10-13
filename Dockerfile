# syntax=docker/dockerfile:1
# Snap2CAD – Web-App und CAD-Sandbox (ein Image, zwei Dienste; siehe docker-compose.yml)

# --- three.js und Schriften einbinden ------------------------------------------
FROM node:22-bookworm-slim AS vendor
WORKDIR /w
COPY web/package.json web/package-lock.json ./
RUN npm ci --omit=dev --no-audit --no-fund
COPY web/scripts/vendor.sh scripts/vendor.sh
RUN mkdir -p static && sh scripts/vendor.sh

# --- Laufzeit ------------------------------------------------------------------
FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/data \
    RUNS_DIR=/runs \
    APP_UID=10001 \
    SANDBOX_UID=10100

RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 libxrender1 libx11-6 libxext6 \
 && rm -rf /var/lib/apt/lists/*

COPY web/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Benutzer: app (Web) und ein Kennungsbereich fuer Sandbox-Laeufe (ohne Login, ohne Home)
RUN groupadd -g 10001 app && useradd -u 10001 -g 10001 -M -d /nonexistent -s /usr/sbin/nologin app \
 && mkdir -p /data /runs && chown 10001:10001 /data /runs && chmod 0700 /data && chmod 0711 /runs

WORKDIR /app
COPY core ./core
COPY generator ./generator
COPY tools ./tools
COPY PROMPT.md README.md LICENSE* ./
COPY web/app ./web/app
COPY web/static ./web/static
COPY --from=vendor /w/static/vendor ./web/static/vendor
RUN python -m compileall -q /app/core /app/web/app \
 && python -c "import build123d, trimesh, shapely, cv2, reportlab, pypdfium2" \
 && chmod -R a+rX /app

# Version zuletzt setzen, damit ein neuer Tag den Build-Cache nicht entwertet
ARG SNAP2CAD_VERSION=0.1.0
ENV SNAP2CAD_VERSION=${SNAP2CAD_VERSION}

WORKDIR /app/web
EXPOSE 8000
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-server-header"]
