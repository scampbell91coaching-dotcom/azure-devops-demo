FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8090

RUN groupadd --gid 10001 portal \
    && useradd \
        --uid 10001 \
        --gid 10001 \
        --no-log-init \
        --create-home \
        --home-dir /home/portal \
        --shell /usr/sbin/nologin \
        portal

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --requirement requirements.txt

COPY --chown=10001:10001 app.py ./
COPY --chown=10001:10001 portal ./portal
COPY --chown=10001:10001 migrations ./migrations
COPY --chown=10001:10001 templates ./templates
COPY --chown=10001:10001 static ./static
COPY --chown=10001:10001 content ./content
COPY --chown=10001:10001 data ./data

RUN mkdir -p /app/data \
    && chown 10001:10001 /app/data

USER 10001:10001

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=2)"]

CMD ["gunicorn", "--bind", "0.0.0.0:8090", "--workers", "1", "--threads", "8", "--timeout", "30", "--access-logfile", "-", "--error-logfile", "-", "app:app"]
