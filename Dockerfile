FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt && useradd --create-home --uid 10001 appuser
COPY --chown=appuser:appuser src ./src
COPY --chown=appuser:appuser data/lab/stage_h ./data/lab/stage_h
COPY --chown=appuser:appuser data/lab/models ./data/lab/models
COPY scripts/perception_bundle.py ./scripts/perception_bundle.py
COPY deploy/artifacts/perception-mini-val.zip ./deploy/artifacts/perception-mini-val.zip
# Small verified outputs for all 81 mini_val frames; no online inference/DB seed.
RUN python scripts/perception_bundle.py install && chown -R appuser:appuser data/lab/cache
COPY scripts/native_demo_bundle.py ./scripts/native_demo_bundle.py
COPY deploy/artifacts/native-ppo-demo.zip ./deploy/artifacts/native-ppo-demo.zip
# Frozen policy evidence and paired20 playback only. No CARLA, Torch or LLM call.
RUN python scripts/native_demo_bundle.py && chown -R appuser:appuser data eval
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import os, urllib.request; p = os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{p}/health')"
CMD ["sh", "-c", "uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
