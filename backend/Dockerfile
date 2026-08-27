FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app
WORKDIR /app

ARG REQUIREMENTS=requirements/dev.txt
COPY requirements/ requirements/
RUN pip install --no-cache-dir -r ${REQUIREMENTS}

COPY . .
RUN useradd -m app && chown -R app /app
USER app

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
