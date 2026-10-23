FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements/ requirements/
ARG REQUIREMENTS_FILE=requirements/production.txt
RUN pip install --no-cache-dir -r ${REQUIREMENTS_FILE}

COPY . .

RUN adduser --disabled-password --no-create-home appuser && \
    mkdir -p /app/staticfiles /app/media && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# ASGI server so that HTTP *and* WebSocket (notifications) both work.
CMD ["uvicorn", "config.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "3"]
