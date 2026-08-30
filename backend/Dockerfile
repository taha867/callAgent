FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app
WORKDIR /app

ARG REQUIREMENTS=requirements/dev.txt
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r ${REQUIREMENTS}
# Phase 3 — privacy/'s Presidio NER pass needs the model, not just the presidio-analyzer
# package (see backend/README.md's Phase 3 note).
RUN python -m spacy download en_core_web_sm

COPY . .
RUN useradd -m app && chown -R app /app
# Phase 2 — voice's model-cache volumes (docker-compose.yml's hf_cache/piper_cache) mount
# over these paths. A named volume that's empty on first mount copies in whatever the
# image already has there, ownership included — pre-creating them as `app`-owned here is
# what lets the `app` user (below) actually write into the volume instead of hitting a
# permission error against the root-owned directory Docker would otherwise create.
RUN mkdir -p /home/app/.cache/huggingface /home/app/.cache/piper && chown -R app /home/app/.cache
USER app

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
