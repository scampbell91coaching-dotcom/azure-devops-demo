FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8090

RUN groupadd --gid 10001 portal \
    && useradd --uid 10001 --gid 10001 --create-home portal

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates ./templates
COPY static ./static
RUN mkdir -p /app/data && chown -R portal:portal /app

USER 10001:10001

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=2)"

CMD ["gunicorn", "--bind", "0.0.0.0:8090", "--workers", "2", "--threads", "4", "--timeout", "30", "app:app"]
