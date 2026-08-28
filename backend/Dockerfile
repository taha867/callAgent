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
USER app

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
