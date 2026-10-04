FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt && useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser src ./src
COPY --chown=appuser:appuser data/lab/stage_h ./data/lab/stage_h
COPY --chown=appuser:appuser data/lab/models ./data/lab/models
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import os, urllib.request; p = os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{p}/health')"
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
