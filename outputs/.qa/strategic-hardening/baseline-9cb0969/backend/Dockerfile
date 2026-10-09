FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml ./
COPY alembic.ini ./
COPY gunicorn.conf.py ./
COPY alembic ./alembic
COPY app ./app
COPY tests ./tests
COPY config ./config

RUN mkdir -p /app/storage/documents \
    && useradd --system --create-home --home-dir /app appuser \
    && chown -R appuser /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "app.main:app", "-c", "gunicorn.conf.py"]
